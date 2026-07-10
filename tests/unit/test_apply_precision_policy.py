from datetime import datetime, timezone

from src.adapters.observability.structured_precision_telemetry_adapter import (
    StructuredPrecisionTelemetryAdapter,
)
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_precision_policy_config_adapter import (
    InMemoryPrecisionPolicyConfigAdapter,
)
from src.adapters.persistence.in_memory_top_recommendation_adapter import (
    InMemoryTopRecommendationAdapter,
)
from src.application.use_cases.apply_precision_policy import ApplyPrecisionPolicyUseCase
from src.domain.precision_policy import PrecisionPolicyConfig
from src.domain.recommendation_gating import GatedRecommendation


def _gated(job_posting_id: str, match_score: int) -> GatedRecommendation:
    return GatedRecommendation(
        job_posting_id=job_posting_id,
        match_score=match_score,
        profile_version="v1",
        config_version="v1",
        actionable=True,
        gate_trace=(),
        evaluated_at=datetime(2026, 7, 5, tzinfo=timezone.utc),
    )


def test_run_precision_policy_persists_top_and_suppressed_traces():
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations([_gated("job-high", 92), _gated("job-low", 80)])
    top = InMemoryTopRecommendationAdapter()
    precision_configs = InMemoryPrecisionPolicyConfigAdapter()
    precision_configs.save_config(PrecisionPolicyConfig(min_confidence_for_top=85, max_top_count=10))
    use_case = ApplyPrecisionPolicyUseCase(
        gated_recommendation_repository=gated,
        precision_config_repository=precision_configs,
        top_recommendation_repository=top,
        telemetry=StructuredPrecisionTelemetryAdapter(),
    )
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)

    result = use_case.run_precision_policy(correlation_id="precision-1", evaluated_at=fixed_now)

    assert result.top_count == 1
    assert result.suppressed_low_confidence_count == 1
    assert len(top.list_top()) == 1
    assert len(top.list_all()) == 2
    assert top.list_top()[0].policy_version == "v1"


def test_run_precision_policy_replaces_stale_top_recommendations():
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations([_gated("job-1", 90)])
    top = InMemoryTopRecommendationAdapter()
    use_case = ApplyPrecisionPolicyUseCase(
        gated_recommendation_repository=gated,
        precision_config_repository=InMemoryPrecisionPolicyConfigAdapter(),
        top_recommendation_repository=top,
        telemetry=StructuredPrecisionTelemetryAdapter(),
    )
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    use_case.run_precision_policy(correlation_id="precision-a", evaluated_at=fixed_now)
    gated.replace_recommendations([])
    use_case.run_precision_policy(correlation_id="precision-b", evaluated_at=fixed_now)

    assert top.list_all() == []


def test_config_change_on_rerun_changes_top_count():
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations([_gated("job-1", 82)])
    precision_configs = InMemoryPrecisionPolicyConfigAdapter()
    precision_configs.save_config(PrecisionPolicyConfig(min_confidence_for_top=85))
    top = InMemoryTopRecommendationAdapter()
    use_case = ApplyPrecisionPolicyUseCase(
        gated_recommendation_repository=gated,
        precision_config_repository=precision_configs,
        top_recommendation_repository=top,
        telemetry=StructuredPrecisionTelemetryAdapter(),
    )
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)

    strict = use_case.run_precision_policy(correlation_id="precision-strict", evaluated_at=fixed_now)
    precision_configs.save_config(PrecisionPolicyConfig(min_confidence_for_top=80))
    relaxed = use_case.run_precision_policy(correlation_id="precision-relaxed", evaluated_at=fixed_now)

    assert strict.top_count == 0
    assert relaxed.top_count == 1
