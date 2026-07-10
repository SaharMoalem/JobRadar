from datetime import datetime, timezone

import pytest

from src.domain.precision_policy import PrecisionPolicyConfig, PrecisionValidationError
from src.domain.precision_ranking_policy import (
    SUPPRESSION_BELOW_MIN_CONFIDENCE,
    SUPPRESSION_EXCEEDED_MAX_TOP,
    apply_precision_policy,
    validate_precision_config,
)
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


def test_validate_precision_config_rejects_invalid_min_confidence():
    with pytest.raises(PrecisionValidationError) as exc:
        validate_precision_config(PrecisionPolicyConfig(min_confidence_for_top=50))
    assert exc.value.code == "PRECISION_MIN_CONFIDENCE_OUT_OF_RANGE"


def test_validate_precision_config_rejects_invalid_max_top():
    with pytest.raises(PrecisionValidationError) as exc:
        validate_precision_config(PrecisionPolicyConfig(max_top_count=0))
    assert exc.value.code == "PRECISION_MAX_TOP_OUT_OF_RANGE"


def test_apply_precision_policy_ignores_non_actionable_inputs():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    non_actionable = GatedRecommendation(
        job_posting_id="job-skip",
        match_score=99,
        profile_version="v1",
        config_version="v1",
        actionable=False,
        gate_trace=(),
        evaluated_at=fixed_now,
    )
    results = apply_precision_policy(
        [non_actionable, _gated("job-high", 90)],
        config=PrecisionPolicyConfig(min_confidence_for_top=85, max_top_count=10),
        evaluated_at=fixed_now,
    )

    assert [item.job_posting_id for item in results] == ["job-high"]


def test_apply_precision_policy_suppresses_low_confidence_candidates():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    results = apply_precision_policy(
        [_gated("job-high", 90), _gated("job-low", 80)],
        config=PrecisionPolicyConfig(min_confidence_for_top=85, max_top_count=10),
        evaluated_at=fixed_now,
    )

    by_id = {item.job_posting_id: item for item in results}
    assert by_id["job-high"].suppressed is False
    assert by_id["job-high"].rank == 1
    assert by_id["job-low"].suppressed is True
    assert by_id["job-low"].suppression_reason == SUPPRESSION_BELOW_MIN_CONFIDENCE


def test_apply_precision_policy_enforces_max_top_count():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    results = apply_precision_policy(
        [_gated("job-a", 95), _gated("job-b", 90), _gated("job-c", 88)],
        config=PrecisionPolicyConfig(min_confidence_for_top=85, max_top_count=2),
        evaluated_at=fixed_now,
    )

    top = [item for item in results if not item.suppressed]
    suppressed_capacity = [
        item for item in results if item.suppression_reason == SUPPRESSION_EXCEEDED_MAX_TOP
    ]
    assert len(top) == 2
    assert top[0].job_posting_id == "job-a"
    assert top[1].job_posting_id == "job-b"
    assert len(suppressed_capacity) == 1


def test_apply_precision_policy_is_deterministic():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    actionable = [_gated("job-b", 90), _gated("job-a", 90), _gated("job-c", 80)]
    config = PrecisionPolicyConfig(min_confidence_for_top=85, max_top_count=10)

    first = apply_precision_policy(actionable, config=config, evaluated_at=fixed_now)
    second = apply_precision_policy(actionable, config=config, evaluated_at=fixed_now)

    assert first == second


def test_precision_config_change_affects_top_output():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    actionable = [_gated("job-1", 82)]

    strict = apply_precision_policy(
        actionable,
        config=PrecisionPolicyConfig(min_confidence_for_top=85),
        evaluated_at=fixed_now,
    )
    relaxed = apply_precision_policy(
        actionable,
        config=PrecisionPolicyConfig(min_confidence_for_top=80),
        evaluated_at=fixed_now,
    )

    assert strict[0].suppressed is True
    assert relaxed[0].suppressed is False
