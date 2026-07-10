from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.precision_policy import (
    PrecisionBatchResult,
    PrecisionFailure,
    PrecisionPolicyConfig,
    PrecisionValidationError,
)
from src.domain.precision_ranking_policy import (
    SUPPRESSION_BELOW_MIN_CONFIDENCE,
    SUPPRESSION_EXCEEDED_MAX_TOP,
    apply_precision_policy,
    validate_precision_config,
)
from src.ports.precision_policy_port import (
    PrecisionPolicyConfigRepositoryPort,
    TopRecommendationRepositoryPort,
)
from src.ports.precision_telemetry_port import PrecisionTelemetryPort
from src.ports.recommendation_gating_port import GatedRecommendationRepositoryPort


@dataclass(slots=True)
class ApplyPrecisionPolicyUseCase:
    gated_recommendation_repository: GatedRecommendationRepositoryPort
    precision_config_repository: PrecisionPolicyConfigRepositoryPort
    top_recommendation_repository: TopRecommendationRepositoryPort
    telemetry: PrecisionTelemetryPort
    default_config: PrecisionPolicyConfig | None = None

    def run_precision_policy(
        self,
        *,
        correlation_id: str,
        evaluated_at: datetime | None = None,
    ) -> PrecisionBatchResult | PrecisionFailure:
        precision_config = (
            self.precision_config_repository.get_config() or self.default_config or PrecisionPolicyConfig()
        )
        try:
            validate_precision_config(precision_config)
        except PrecisionValidationError as exc:
            failure = PrecisionFailure(code=exc.code, message=str(exc), correlation_id=correlation_id)
            self.telemetry.record_failure(failure)
            return failure

        evaluated = evaluated_at or datetime.now(timezone.utc)
        actionable = self.gated_recommendation_repository.list_actionable()
        ranked = apply_precision_policy(
            actionable,
            config=precision_config,
            evaluated_at=evaluated,
        )
        saved = self.top_recommendation_repository.replace_recommendations(ranked)
        top_count = sum(1 for item in saved if not item.suppressed)
        suppressed_low_confidence_count = sum(
            1 for item in saved if item.suppression_reason == SUPPRESSION_BELOW_MIN_CONFIDENCE
        )
        suppressed_capacity_count = sum(
            1 for item in saved if item.suppression_reason == SUPPRESSION_EXCEEDED_MAX_TOP
        )
        result = PrecisionBatchResult(
            top_recommendations=tuple(saved),
            top_count=top_count,
            suppressed_low_confidence_count=suppressed_low_confidence_count,
            suppressed_capacity_count=suppressed_capacity_count,
            actionable_input_count=len(actionable),
            correlation_id=correlation_id,
        )
        self.telemetry.record_batch(result)
        return result
