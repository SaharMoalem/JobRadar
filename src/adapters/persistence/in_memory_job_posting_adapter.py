from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from src.domain.dedup_policy import (
    JobDuplicateLink,
    compute_identity_key,
    derive_canonical_id,
)
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState, JobLifecycleTransition, RetentionBatchResult
from src.domain.lifecycle_policy import next_state_on_observation, should_archive
from src.domain.normalization import NormalizationRejection
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.lifecycle_telemetry_port import LifecycleTelemetryPort


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryJobPostingAdapter(JobPostingRepositoryPort):
    def __init__(self, telemetry: LifecycleTelemetryPort | None = None) -> None:
        self._telemetry = telemetry
        self._postings: dict[str, JobPosting] = {}
        self._canonical_by_identity: dict[str, JobPosting] = {}
        self._canonical_by_source_external: dict[tuple[str, str], str] = {}
        self._duplicate_links: list[JobDuplicateLink] = []
        self._duplicate_link_keys: set[tuple[str, str, str]] = set()
        self._rejections: list[NormalizationRejection] = []
        self._transitions: list[JobLifecycleTransition] = []

    def save_posting(self, posting: JobPosting) -> JobPosting:
        identity_key = compute_identity_key(url=posting.url)
        source_external = (posting.career_source_id, posting.external_id)
        existing_by_identity = self._canonical_by_identity.get(identity_key)
        canonical_id_by_source = self._canonical_by_source_external.get(source_external)

        if canonical_id_by_source is not None:
            existing_by_source = self._postings[canonical_id_by_source]
            if existing_by_identity is None or existing_by_identity.id == existing_by_source.id:
                return self._update_canonical(posting, existing_by_source, identity_key)

        if existing_by_identity is not None:
            if (
                existing_by_identity.career_source_id == posting.career_source_id
                and existing_by_identity.external_id == posting.external_id
            ):
                return self._update_canonical(posting, existing_by_identity, identity_key)
            self._record_duplicate_link(existing_by_identity, posting, identity_key)
            return self._mark_reobserved(
                existing_by_identity,
                correlation_id=str(posting.source_metadata.get("correlation_id") or "unknown"),
            )

        canonical = self._as_canonical(posting, identity_key=identity_key)
        self._register_canonical(canonical, identity_key, source_external)
        self._record_lifecycle_transition(
            canonical,
            from_state=None,
            to_state=JobLifecycleState.NEW,
            reason="first_observed",
            correlation_id=str(posting.source_metadata.get("correlation_id") or "unknown"),
        )
        return canonical

    def save_rejection(self, rejection: NormalizationRejection) -> NormalizationRejection:
        self._rejections.append(rejection)
        return rejection

    def list_complete(self) -> list[JobPosting]:
        return [
            posting
            for posting in self._postings.values()
            if posting.completeness == JobPostingCompleteness.COMPLETE
            and posting.lifecycle_state != JobLifecycleState.ARCHIVED
        ]

    def list_rejections(self) -> list[NormalizationRejection]:
        return list(self._rejections)

    def list_duplicate_links(self) -> list[JobDuplicateLink]:
        return list(self._duplicate_links)

    def list_lifecycle_transitions(self, job_posting_id: str | None = None) -> list[JobLifecycleTransition]:
        if job_posting_id is None:
            return list(self._transitions)
        return [transition for transition in self._transitions if transition.job_posting_id == job_posting_id]

    def expire_unseen_for_source(
        self,
        source_id: str,
        seen_posting_ids: set[str],
        *,
        correlation_id: str,
    ) -> list[JobLifecycleTransition]:
        transitions: list[JobLifecycleTransition] = []
        for posting in self._postings.values():
            if posting.career_source_id != source_id:
                continue
            if posting.lifecycle_state in (JobLifecycleState.EXPIRED, JobLifecycleState.ARCHIVED):
                continue
            if posting.id in seen_posting_ids:
                continue
            transition = self._transition_posting(
                posting,
                to_state=JobLifecycleState.EXPIRED,
                reason="not_seen_in_source_crawl",
                correlation_id=correlation_id,
                expired_at=_utc_now(),
            )
            transitions.append(transition)
        return transitions

    def apply_retention_policy(
        self,
        evaluated_at: datetime,
        *,
        correlation_id: str,
    ) -> RetentionBatchResult:
        archived_count = 0
        for posting in list(self._postings.values()):
            if posting.lifecycle_state != JobLifecycleState.EXPIRED:
                continue
            if not should_archive(posting.expired_at, evaluated_at):
                continue
            self._transition_posting(
                posting,
                to_state=JobLifecycleState.ARCHIVED,
                reason="retention_policy_elapsed",
                correlation_id=correlation_id,
                archived_at=evaluated_at,
            )
            archived_count += 1
        return RetentionBatchResult(
            archived_count=archived_count,
            correlation_id=correlation_id,
            evaluated_at=evaluated_at,
        )

    def _register_canonical(
        self,
        canonical: JobPosting,
        identity_key: str,
        source_external: tuple[str, str],
    ) -> None:
        self._canonical_by_identity[identity_key] = canonical
        self._postings[canonical.id] = canonical
        self._canonical_by_source_external[source_external] = canonical.id

    def _update_canonical(
        self,
        posting: JobPosting,
        existing: JobPosting,
        identity_key: str,
    ) -> JobPosting:
        old_identity_key = existing.identity_key
        if old_identity_key and old_identity_key != identity_key:
            self._canonical_by_identity.pop(old_identity_key, None)

        next_state, reason = next_state_on_observation(existing=existing, observed=posting)
        now = _utc_now()
        updated = replace(
            posting,
            id=existing.id,
            identity_key=identity_key,
            completeness=JobPostingCompleteness.COMPLETE,
            rejection_reason=None,
            created_at=existing.created_at,
            lifecycle_state=next_state,
            last_seen_at=now,
            expired_at=None,
            archived_at=None,
        )
        updated.updated_at = now
        source_external = (posting.career_source_id, posting.external_id)
        self._canonical_by_identity[identity_key] = updated
        self._postings[existing.id] = updated
        self._canonical_by_source_external[source_external] = existing.id
        if existing.lifecycle_state != next_state:
            self._record_lifecycle_transition(
                updated,
                from_state=existing.lifecycle_state,
                to_state=next_state,
                reason=reason,
                correlation_id=str(posting.source_metadata.get("correlation_id") or "unknown"),
            )
        return updated

    def _mark_reobserved(self, canonical: JobPosting, *, correlation_id: str) -> JobPosting:
        now = _utc_now()
        updated = replace(
            canonical,
            lifecycle_state=JobLifecycleState.ACTIVE,
            last_seen_at=now,
            expired_at=None,
            archived_at=None,
        )
        updated.updated_at = now
        if canonical.identity_key:
            self._canonical_by_identity[canonical.identity_key] = updated
        self._postings[canonical.id] = updated
        if canonical.lifecycle_state != JobLifecycleState.ACTIVE:
            self._record_lifecycle_transition(
                updated,
                from_state=canonical.lifecycle_state,
                to_state=JobLifecycleState.ACTIVE,
                reason="duplicate_reobserved",
                correlation_id=correlation_id,
            )
        return updated

    def _record_duplicate_link(
        self,
        canonical: JobPosting,
        posting: JobPosting,
        identity_key: str,
    ) -> None:
        link_key = (canonical.id, posting.career_source_id, posting.external_id)
        if link_key in self._duplicate_link_keys:
            return
        self._duplicate_link_keys.add(link_key)
        self._duplicate_links.append(
            JobDuplicateLink(
                canonical_id=canonical.id,
                identity_key=identity_key,
                career_source_id=posting.career_source_id,
                external_id=posting.external_id,
                duplicate_reason="identity_key_match",
            )
        )

    def _as_canonical(self, posting: JobPosting, *, identity_key: str) -> JobPosting:
        now = _utc_now()
        return replace(
            posting,
            id=derive_canonical_id(identity_key),
            identity_key=identity_key,
            completeness=JobPostingCompleteness.COMPLETE,
            rejection_reason=None,
            lifecycle_state=JobLifecycleState.NEW,
            last_seen_at=now,
            expired_at=None,
            archived_at=None,
        )

    def _transition_posting(
        self,
        posting: JobPosting,
        *,
        to_state: JobLifecycleState,
        reason: str,
        correlation_id: str,
        expired_at: datetime | None = None,
        archived_at: datetime | None = None,
    ) -> JobLifecycleTransition:
        updated = replace(
            posting,
            lifecycle_state=to_state,
            expired_at=expired_at if expired_at is not None else posting.expired_at,
            archived_at=archived_at if archived_at is not None else posting.archived_at,
        )
        updated.touch()
        if posting.identity_key:
            self._canonical_by_identity[posting.identity_key] = updated
        self._postings[posting.id] = updated
        return self._record_lifecycle_transition(
            updated,
            from_state=posting.lifecycle_state,
            to_state=to_state,
            reason=reason,
            correlation_id=correlation_id,
        )

    def _record_lifecycle_transition(
        self,
        posting: JobPosting,
        *,
        from_state: JobLifecycleState | None,
        to_state: JobLifecycleState,
        reason: str,
        correlation_id: str,
    ) -> JobLifecycleTransition:
        transition = JobLifecycleTransition(
            job_posting_id=posting.id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            correlation_id=correlation_id,
            transitioned_at=_utc_now(),
        )
        self._transitions.append(transition)
        if self._telemetry:
            self._telemetry.record_transition(transition)
        return transition
