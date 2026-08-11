from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.domain.immediate_alert import (
    ImmediateAlert,
    ImmediateAlertBatchResult,
    ImmediateAlertConfig,
    ImmediateAlertFailure,
    ImmediateAlertValidationError,
)
from src.domain.immediate_alert_policy import (
    build_deep_link,
    build_role_summary,
    select_alert_candidates,
    validate_alert_config,
)
from src.ports.immediate_alert_port import (
    ImmediateAlertConfigRepositoryPort,
    ImmediateAlertRepositoryPort,
    ImmediateAlertTelemetryPort,
)
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.recommendation_gating_port import GatedRecommendationRepositoryPort


@dataclass(slots=True)
class TriggerImmediateAlertsUseCase:
    gated_recommendation_repository: GatedRecommendationRepositoryPort
    job_posting_repository: JobPostingRepositoryPort
    alert_config_repository: ImmediateAlertConfigRepositoryPort
    alert_repository: ImmediateAlertRepositoryPort
    telemetry: ImmediateAlertTelemetryPort
    default_config: ImmediateAlertConfig | None = None

    def run(
        self,
        *,
        correlation_id: str,
        run_context: str | None = None,
    ) -> ImmediateAlertBatchResult | ImmediateAlertFailure:
        if not (correlation_id or "").strip():
            failure = ImmediateAlertFailure(
                code="ALERT_CORRELATION_ID_REQUIRED",
                message="Correlation id is required and cannot be blank.",
                correlation_id=correlation_id or "",
            )
            self.telemetry.record_failure(failure)
            return failure
        correlation_id = correlation_id.strip()
        if run_context is not None and not run_context.strip():
            failure = ImmediateAlertFailure(
                code="ALERT_RUN_CONTEXT_INVALID",
                message="Run context cannot be blank when provided.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        config = (
            self.alert_config_repository.get_config()
            or self.default_config
            or ImmediateAlertConfig()
        )
        try:
            validate_alert_config(config)
        except ImmediateAlertValidationError as exc:
            failure = ImmediateAlertFailure(
                code=exc.code,
                message=str(exc),
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        context = run_context.strip() if run_context is not None else correlation_id
        actionable = self.gated_recommendation_repository.list_actionable()
        below_threshold = sum(
            1
            for item in actionable
            if item.match_score < config.alert_threshold
        )
        candidates = select_alert_candidates(
            actionable,
            threshold=config.alert_threshold,
        )
        postings = {
            posting.id: posting for posting in self.job_posting_repository.list_complete()
        }

        created: list[ImmediateAlert] = []
        skipped_duplicate = 0
        skipped_missing = 0
        for candidate in candidates:
            if self.alert_repository.has_alert(
                run_context=context,
                job_posting_id=candidate.job_posting_id,
            ):
                skipped_duplicate += 1
                continue
            posting = postings.get(candidate.job_posting_id)
            if posting is None:
                skipped_missing += 1
                continue
            created.append(
                ImmediateAlert(
                    id=f"alert-{uuid4().hex[:12]}",
                    job_posting_id=candidate.job_posting_id,
                    role_summary=build_role_summary(posting),
                    match_score=candidate.match_score,
                    deep_link=build_deep_link(candidate.job_posting_id),
                    run_context=context,
                    correlation_id=correlation_id,
                )
            )

        saved = self.alert_repository.save_alerts(created)
        # Repository-level dedup may also skip if races; count those as duplicates.
        skipped_duplicate += len(created) - len(saved)
        result = ImmediateAlertBatchResult(
            alerts=tuple(saved),
            triggered_count=len(saved),
            skipped_below_threshold_count=below_threshold,
            skipped_duplicate_count=skipped_duplicate,
            skipped_missing_posting_count=skipped_missing,
            correlation_id=correlation_id,
            run_context=context,
        )
        self.telemetry.record_batch(result)
        return result

    def list_alerts(self) -> list[ImmediateAlert]:
        return self.alert_repository.list_alerts()
