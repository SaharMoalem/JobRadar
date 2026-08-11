from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.domain.lifecycle import JobLifecycleState
from src.domain.morning_digest import (
    DigestJobItem,
    MorningDigest,
    MorningDigestConfig,
    MorningDigestFailure,
    MorningDigestResult,
    MorningDigestValidationError,
)
from src.domain.morning_digest_policy import (
    bucket_transitions,
    build_change_item,
    build_top_item,
    default_run_context,
    ensure_utc,
    latest_change_transitions,
    qualifies_for_change_section,
    resolve_digest_date,
    select_top_recommendations,
    transitions_in_window,
    validate_digest_config,
    window_start,
)
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.match_scoring_port import MatchScoreRepositoryPort
from src.ports.morning_digest_port import (
    MorningDigestConfigRepositoryPort,
    MorningDigestRepositoryPort,
    MorningDigestTelemetryPort,
)
from src.ports.precision_policy_port import TopRecommendationRepositoryPort


@dataclass(slots=True)
class GenerateMorningDigestUseCase:
    job_posting_repository: JobPostingRepositoryPort
    match_score_repository: MatchScoreRepositoryPort
    top_recommendation_repository: TopRecommendationRepositoryPort
    digest_config_repository: MorningDigestConfigRepositoryPort
    digest_repository: MorningDigestRepositoryPort
    telemetry: MorningDigestTelemetryPort
    default_config: MorningDigestConfig | None = None

    def run(
        self,
        *,
        correlation_id: str,
        run_context: str | None = None,
        now: datetime | None = None,
    ) -> MorningDigestResult | MorningDigestFailure:
        if not (correlation_id or "").strip():
            failure = MorningDigestFailure(
                code="DIGEST_CORRELATION_ID_REQUIRED",
                message="Correlation id is required and cannot be blank.",
                correlation_id=correlation_id or "",
            )
            self.telemetry.record_failure(failure)
            return failure
        correlation_id = correlation_id.strip()
        if run_context is not None and not run_context.strip():
            failure = MorningDigestFailure(
                code="DIGEST_RUN_CONTEXT_INVALID",
                message="Run context cannot be blank when provided.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        config = (
            self.digest_config_repository.get_config()
            or self.default_config
            or MorningDigestConfig()
        )
        try:
            validate_digest_config(config)
        except MorningDigestValidationError as exc:
            failure = MorningDigestFailure(
                code=exc.code,
                message=str(exc),
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        evaluated_at = ensure_utc(now or datetime.now(timezone.utc))
        context = run_context.strip() if run_context is not None else default_run_context(now=evaluated_at)
        start_at = window_start(window_hours=config.digest_window_hours, now=evaluated_at)

        postings = {item.id: item for item in self.job_posting_repository.list_complete()}
        scores = {
            item.job_posting_id: item.score for item in self.match_score_repository.list_scores()
        }

        windowed = transitions_in_window(
            self.job_posting_repository.list_lifecycle_transitions(),
            window_start_at=start_at,
            window_end_at=evaluated_at,
        )
        latest = latest_change_transitions(windowed)
        buckets = bucket_transitions(latest)

        skipped_below = 0
        skipped_missing_score = 0
        skipped_missing_posting = 0

        def build_section(state: JobLifecycleState) -> tuple[DigestJobItem, ...]:
            nonlocal skipped_below, skipped_missing_score, skipped_missing_posting
            items: list[DigestJobItem] = []
            for transition in buckets[state]:
                posting = postings.get(transition.job_posting_id)
                if posting is None:
                    skipped_missing_posting += 1
                    continue
                score = scores.get(transition.job_posting_id)
                if score is None:
                    skipped_missing_score += 1
                    continue
                if not qualifies_for_change_section(match_score=score, threshold=config.digest_threshold):
                    skipped_below += 1
                    continue
                items.append(
                    build_change_item(
                        posting=posting,
                        match_score=score,
                        lifecycle_state=state,
                        transitioned_at=transition.transitioned_at,
                    )
                )
            return tuple(items)

        new_items = build_section(JobLifecycleState.NEW)
        updated_items = build_section(JobLifecycleState.UPDATED)
        expired_items = build_section(JobLifecycleState.EXPIRED)

        top_selected, top_missing = select_top_recommendations(
            self.top_recommendation_repository.list_top(),
            top_n=config.top_n,
            available_posting_ids=set(postings),
        )
        skipped_missing_posting += top_missing
        top_items = [
            build_top_item(posting=postings[item.job_posting_id], recommendation=item)
            for item in top_selected
        ]

        is_noop = not (new_items or updated_items or expired_items or top_items)
        digest = MorningDigest(
            id=f"digest-{uuid4().hex[:12]}",
            run_context=context,
            correlation_id=correlation_id,
            digest_date=resolve_digest_date(run_context=context, evaluated_at=evaluated_at),
            new_items=new_items,
            updated_items=updated_items,
            expired_items=expired_items,
            top_recommendations=tuple(top_items),
            is_noop=is_noop,
            skipped_below_threshold_count=skipped_below,
            skipped_missing_score_count=skipped_missing_score,
            skipped_missing_posting_count=skipped_missing_posting,
            created_at=evaluated_at,
        )
        saved = self.digest_repository.replace_for_run_context(digest)
        result = MorningDigestResult(
            digest=saved,
            correlation_id=correlation_id,
            run_context=context,
        )
        self.telemetry.record_result(result)
        return result

    def list_digests(self) -> list[MorningDigest]:
        return self.digest_repository.list_digests()
