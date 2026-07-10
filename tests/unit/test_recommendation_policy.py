from datetime import datetime, timezone

import pytest

from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.recommendation_gating import GatingValidationError, RecommendationGateConfig
from src.domain.recommendation_policy import evaluate_gates, validate_gate_config
from src.domain.user_profile import UserProfile


def _posting(**overrides) -> JobPosting:
    defaults = {
        "id": "job-1",
        "title": "Senior Python FastAPI Engineer",
        "company": "Acme",
        "location": "Tel Aviv, Israel (English)",
        "url": "https://example.com/jobs/1",
        "posted_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "career_source_id": "src-1",
        "external_id": "ext-1",
        "plugin_id": "generic",
        "completeness": JobPostingCompleteness.COMPLETE,
        "lifecycle_state": JobLifecycleState.NEW,
    }
    defaults.update(overrides)
    return JobPosting(**defaults)


def _profile() -> UserProfile:
    return UserProfile(
        skills=("python", "fastapi"),
        preferred_locations=("Tel Aviv",),
        preferred_languages=("english",),
        target_seniority="senior",
    )


def _match_score(**overrides) -> MatchScore:
    defaults = {
        "job_posting_id": "job-1",
        "score": 85,
        "profile_version": "v1",
        "config_version": "v1",
        "signal_breakdown": {"skills": 40, "location": 25, "language": 15, "recency": 5},
        "computed_at": datetime(2026, 7, 5, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return MatchScore(**defaults)


def test_validate_gate_config_rejects_invalid_threshold():
    with pytest.raises(GatingValidationError) as exc:
        validate_gate_config(RecommendationGateConfig(global_threshold=50))
    assert exc.value.code == "GATE_THRESHOLD_OUT_OF_RANGE"


def test_validate_gate_config_rejects_invalid_skill_overlap():
    with pytest.raises(GatingValidationError) as exc:
        validate_gate_config(RecommendationGateConfig(skill_overlap_min_pct=101))
    assert exc.value.code == "GATE_SKILL_OVERLAP_OUT_OF_RANGE"


def test_validate_gate_config_rejects_invalid_recency_window():
    with pytest.raises(GatingValidationError) as exc:
        validate_gate_config(RecommendationGateConfig(recency_window_days=0))
    assert exc.value.code == "GATE_RECENCY_WINDOW_INVALID"


def test_evaluate_gates_marks_passing_candidate_actionable():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    result = evaluate_gates(
        _profile(),
        _posting(),
        _match_score(),
        now=fixed_now,
    )

    assert result.actionable is True
    assert all(entry.passed for entry in result.gate_trace)


def test_evaluate_gates_captures_threshold_failure():
    result = evaluate_gates(
        _profile(),
        _posting(),
        _match_score(score=70),
        config=RecommendationGateConfig(global_threshold=80),
        now=datetime(2026, 7, 5, tzinfo=timezone.utc),
    )

    assert result.actionable is False
    threshold = next(entry for entry in result.gate_trace if entry.gate == "threshold")
    assert threshold.passed is False


def test_evaluate_gates_captures_seniority_failure():
    result = evaluate_gates(
        _profile(),
        _posting(title="Python Engineer"),
        _match_score(),
        now=datetime(2026, 7, 5, tzinfo=timezone.utc),
    )

    assert result.actionable is False
    seniority = next(entry for entry in result.gate_trace if entry.gate == "seniority")
    assert seniority.passed is False


def test_evaluate_gates_is_deterministic():
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    profile = _profile()
    posting = _posting()
    score = _match_score()
    config = RecommendationGateConfig()

    first = evaluate_gates(profile, posting, score, config=config, now=fixed_now)
    second = evaluate_gates(profile, posting, score, config=config, now=fixed_now)

    assert first == second


def test_threshold_change_affects_actionable_without_code_change():
    profile = _profile()
    posting = _posting()
    score = _match_score(score=75)
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)

    strict = evaluate_gates(
        profile,
        posting,
        score,
        config=RecommendationGateConfig(global_threshold=80),
        now=fixed_now,
    )
    relaxed = evaluate_gates(
        profile,
        posting,
        score,
        config=RecommendationGateConfig(global_threshold=70),
        now=fixed_now,
    )

    assert strict.actionable is False
    assert relaxed.actionable is True
