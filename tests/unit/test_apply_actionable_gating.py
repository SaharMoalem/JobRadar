from datetime import datetime, timezone

from src.adapters.observability.structured_gating_telemetry_adapter import (
    StructuredGatingTelemetryAdapter,
)
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_recommendation_gate_config_adapter import (
    InMemoryRecommendationGateConfigAdapter,
)
from src.adapters.persistence.in_memory_user_profile_adapter import InMemoryUserProfileAdapter
from src.application.use_cases.apply_actionable_gating import ApplyActionableGatingUseCase
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.recommendation_gating import GatingFailure, RecommendationGateConfig
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


def test_run_gating_persists_actionable_and_non_actionable_candidates():
    postings = InMemoryJobPostingAdapter()
    passing = postings.save_posting(_posting())
    failing = postings.save_posting(
        _posting(
            title="Junior Python FastAPI Engineer",
            url="https://example.com/jobs/2",
            external_id="ext-2",
        )
    )
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    scores = InMemoryMatchScoreAdapter()
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=passing.id,
                score=90,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={"skills": 45},
                computed_at=fixed_now,
            ),
            MatchScore(
                job_posting_id=failing.id,
                score=90,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={"skills": 45},
                computed_at=fixed_now,
            ),
        ]
    )
    gated = InMemoryGatedRecommendationAdapter()
    use_case = ApplyActionableGatingUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        gate_config_repository=InMemoryRecommendationGateConfigAdapter(),
        gated_recommendation_repository=gated,
        telemetry=StructuredGatingTelemetryAdapter(),
    )

    result = use_case.run_gating(correlation_id="gating-1", evaluated_at=fixed_now)

    assert not isinstance(result, GatingFailure)
    assert result.actionable_count == 1
    assert result.non_actionable_count == 1
    assert len(gated.list_recommendations()) == 2
    assert len(gated.list_actionable()) == 1
    failed = next(item for item in gated.list_recommendations() if not item.actionable)
    assert any(entry.passed is False for entry in failed.gate_trace)


def test_run_gating_replaces_stale_recommendations():
    postings = InMemoryJobPostingAdapter()
    saved = postings.save_posting(_posting())
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    scores = InMemoryMatchScoreAdapter()
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=saved.id,
                score=90,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={"skills": 45},
                computed_at=fixed_now,
            )
        ]
    )
    gated = InMemoryGatedRecommendationAdapter()
    gate_configs = InMemoryRecommendationGateConfigAdapter()
    use_case = ApplyActionableGatingUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        gate_config_repository=gate_configs,
        gated_recommendation_repository=gated,
        telemetry=StructuredGatingTelemetryAdapter(),
    )
    use_case.run_gating(correlation_id="gating-a", evaluated_at=fixed_now)
    scores.replace_scores([])
    use_case.run_gating(correlation_id="gating-b", evaluated_at=fixed_now)

    assert gated.list_recommendations() == []


def test_run_gating_without_profile_returns_failure():
    use_case = ApplyActionableGatingUseCase(
        profile_repository=InMemoryUserProfileAdapter(),
        job_posting_repository=InMemoryJobPostingAdapter(),
        match_score_repository=InMemoryMatchScoreAdapter(),
        gate_config_repository=InMemoryRecommendationGateConfigAdapter(),
        gated_recommendation_repository=InMemoryGatedRecommendationAdapter(),
        telemetry=StructuredGatingTelemetryAdapter(),
    )

    result = use_case.run_gating(correlation_id="gating-no-profile")

    assert isinstance(result, GatingFailure)
    assert result.code == "PROFILE_NOT_CONFIGURED"


def test_config_change_on_rerun_changes_actionable_set():
    postings = InMemoryJobPostingAdapter()
    saved = postings.save_posting(_posting())
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    scores = InMemoryMatchScoreAdapter()
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=saved.id,
                score=75,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={"skills": 35},
                computed_at=fixed_now,
            )
        ]
    )
    gate_configs = InMemoryRecommendationGateConfigAdapter()
    gate_configs.save_config(RecommendationGateConfig(global_threshold=80))
    gated = InMemoryGatedRecommendationAdapter()
    use_case = ApplyActionableGatingUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        gate_config_repository=gate_configs,
        gated_recommendation_repository=gated,
        telemetry=StructuredGatingTelemetryAdapter(),
    )

    first = use_case.run_gating(correlation_id="gating-strict", evaluated_at=fixed_now)
    gate_configs.save_config(RecommendationGateConfig(global_threshold=70))
    second = use_case.run_gating(correlation_id="gating-relaxed", evaluated_at=fixed_now)

    assert not isinstance(first, GatingFailure)
    assert not isinstance(second, GatingFailure)
    assert first.actionable_count == 0
    assert second.actionable_count == 1
