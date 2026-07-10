from datetime import datetime, timezone

import pytest

from src.domain.explainability import ExplainabilityNote, ExplainabilityQualityError
from src.domain.explainability_policy import (
    generate_explainability_note,
    validate_explainability_note,
)
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.recommendation_gating import GatedRecommendation, GateTraceEntry
from src.domain.user_profile import UserProfile


def _posting(**overrides) -> JobPosting:
    defaults = {
        "id": "job-1",
        "title": "Senior Python FastAPI Engineer",
        "company": "Acme",
        "location": "Tel Aviv, Israel",
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
        skills=("python", "fastapi", "kubernetes"),
        preferred_locations=("Tel Aviv",),
        preferred_languages=("english",),
        target_seniority="senior",
    )


def _match_score(**overrides) -> MatchScore:
    defaults = {
        "job_posting_id": "job-1",
        "score": 88,
        "profile_version": "v1",
        "config_version": "v1",
        "signal_breakdown": {"skills": 45, "location": 25, "language": 10, "recency": 8},
        "computed_at": datetime(2026, 7, 5, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return MatchScore(**defaults)


def _gated() -> GatedRecommendation:
    return GatedRecommendation(
        job_posting_id="job-1",
        match_score=88,
        profile_version="v1",
        config_version="v1",
        actionable=True,
        gate_trace=(
            GateTraceEntry(gate="threshold", passed=True, message="ok"),
            GateTraceEntry(gate="region", passed=True, message="ok"),
        ),
        evaluated_at=datetime(2026, 7, 5, tzinfo=timezone.utc),
    )


def test_generate_explainability_note_includes_required_fields():
    note = generate_explainability_note(_profile(), _posting(), _match_score(), _gated())

    assert note.match_rationale
    assert note.missing_skills == ("kubernetes",)
    assert 0 <= note.interview_probability_pct <= 100
    assert note.effort_estimate in {"low", "medium", "high"}


def test_validate_explainability_note_rejects_empty_rationale():
    with pytest.raises(ExplainabilityQualityError) as exc:
        validate_explainability_note(
            ExplainabilityNote(
                match_rationale="   ",
                missing_skills=(),
                interview_probability_pct=80,
                effort_estimate="low",
            )
        )
    assert exc.value.code == "EXPLAINABILITY_RATIONALE_REQUIRED"


def test_validate_explainability_note_rejects_invalid_interview_probability():
    with pytest.raises(ExplainabilityQualityError) as exc:
        validate_explainability_note(
            ExplainabilityNote(
                match_rationale="Strong match.",
                missing_skills=(),
                interview_probability_pct=120,
                effort_estimate="low",
            )
        )
    assert exc.value.code == "EXPLAINABILITY_INTERVIEW_PROBABILITY_INVALID"


def test_validate_explainability_note_rejects_invalid_effort_estimate():
    with pytest.raises(ExplainabilityQualityError) as exc:
        validate_explainability_note(
            ExplainabilityNote(
                match_rationale="Strong match.",
                missing_skills=(),
                interview_probability_pct=80,
                effort_estimate="extreme",
            )
        )
    assert exc.value.code == "EXPLAINABILITY_EFFORT_INVALID"


def test_generate_explainability_note_is_deterministic():
    profile = _profile()
    posting = _posting()
    score = _match_score()
    gated = _gated()

    first = generate_explainability_note(profile, posting, score, gated)
    second = generate_explainability_note(profile, posting, score, gated)

    assert first == second
