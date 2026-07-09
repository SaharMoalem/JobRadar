from __future__ import annotations

from dataclasses import replace

from src.domain.dedup_policy import (
    JobDuplicateLink,
    compute_identity_key,
    derive_canonical_id,
)
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.normalization import NormalizationRejection
from src.ports.job_posting_port import JobPostingRepositoryPort


class InMemoryJobPostingAdapter(JobPostingRepositoryPort):
    def __init__(self) -> None:
        self._postings: dict[str, JobPosting] = {}
        self._canonical_by_identity: dict[str, JobPosting] = {}
        self._canonical_by_source_external: dict[tuple[str, str], str] = {}
        self._duplicate_links: list[JobDuplicateLink] = []
        self._duplicate_link_keys: set[tuple[str, str, str]] = set()
        self._rejections: list[NormalizationRejection] = []

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
            return existing_by_identity

        canonical = self._as_canonical(posting, identity_key=identity_key)
        self._register_canonical(canonical, identity_key, source_external)
        return canonical

    def save_rejection(self, rejection: NormalizationRejection) -> NormalizationRejection:
        self._rejections.append(rejection)
        return rejection

    def list_complete(self) -> list[JobPosting]:
        return [
            posting
            for posting in self._postings.values()
            if posting.completeness == JobPostingCompleteness.COMPLETE
        ]

    def list_rejections(self) -> list[NormalizationRejection]:
        return list(self._rejections)

    def list_duplicate_links(self) -> list[JobDuplicateLink]:
        return list(self._duplicate_links)

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

        updated = replace(
            posting,
            id=existing.id,
            identity_key=identity_key,
            completeness=JobPostingCompleteness.COMPLETE,
            rejection_reason=None,
            created_at=existing.created_at,
        )
        updated.touch()
        source_external = (posting.career_source_id, posting.external_id)
        self._canonical_by_identity[identity_key] = updated
        self._postings[existing.id] = updated
        self._canonical_by_source_external[source_external] = existing.id
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
        return replace(
            posting,
            id=derive_canonical_id(identity_key),
            identity_key=identity_key,
            completeness=JobPostingCompleteness.COMPLETE,
            rejection_reason=None,
        )
