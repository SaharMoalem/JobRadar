from __future__ import annotations

from datetime import datetime, timezone

from src.domain.precision_policy import (
    PrecisionPolicyConfig,
    PrecisionValidationError,
    TopRecommendation,
)
from src.domain.recommendation_gating import GatedRecommendation

SUPPRESSION_BELOW_MIN_CONFIDENCE = "below_min_confidence"
SUPPRESSION_EXCEEDED_MAX_TOP = "exceeded_max_top_limit"


def validate_precision_config(config: PrecisionPolicyConfig) -> None:
    if not 60 <= config.min_confidence_for_top <= 100:
        raise PrecisionValidationError(
            "PRECISION_MIN_CONFIDENCE_OUT_OF_RANGE",
            "Minimum confidence for top output must be between 60 and 100.",
        )
    if not 1 <= config.max_top_count <= 50:
        raise PrecisionValidationError(
            "PRECISION_MAX_TOP_OUT_OF_RANGE",
            "Maximum top recommendation count must be between 1 and 50.",
        )


def apply_precision_policy(
    actionable_recommendations: list[GatedRecommendation],
    *,
    config: PrecisionPolicyConfig | None = None,
    evaluated_at: datetime | None = None,
) -> list[TopRecommendation]:
    policy_config = config or PrecisionPolicyConfig()
    validate_precision_config(policy_config)
    evaluated = evaluated_at or datetime.now(timezone.utc)

    ranked_inputs = sorted(
        (item for item in actionable_recommendations if item.actionable),
        key=lambda item: (-item.match_score, item.job_posting_id),
    )
    results: list[TopRecommendation] = []
    top_slots_used = 0

    for recommendation in ranked_inputs:
        suppressed = False
        suppression_reason: str | None = None
        rank: int | None = None

        if recommendation.match_score < policy_config.min_confidence_for_top:
            suppressed = True
            suppression_reason = SUPPRESSION_BELOW_MIN_CONFIDENCE
        elif top_slots_used >= policy_config.max_top_count:
            suppressed = True
            suppression_reason = SUPPRESSION_EXCEEDED_MAX_TOP
        else:
            top_slots_used += 1
            rank = top_slots_used

        results.append(
            TopRecommendation(
                job_posting_id=recommendation.job_posting_id,
                match_score=recommendation.match_score,
                rank=rank,
                suppressed=suppressed,
                suppression_reason=suppression_reason,
                policy_version=policy_config.config_version,
                gate_config_version=recommendation.config_version,
                profile_version=recommendation.profile_version,
                evaluated_at=evaluated,
            )
        )

    return results
