from datetime import datetime, timezone

from src.adapters.explainability.rule_based_explainability_generator import (
    InMemoryExplainableRecommendationAdapter,
    RuleBasedExplainabilityGeneratorAdapter,
)
from src.adapters.observability.structured_explainability_telemetry_adapter import (
    StructuredExplainabilityTelemetryAdapter,
)
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_top_recommendation_adapter import (
    InMemoryTopRecommendationAdapter,
)
from src.adapters.persistence.in_memory_user_profile_adapter import InMemoryUserProfileAdapter
from src.application.use_cases.generate_explainability import GenerateExplainabilityUseCase
from src.domain.explainability import ExplainabilityFailure, ExplainabilityNote
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.precision_policy import TopRecommendation
from src.domain.recommendation_gating import GatedRecommendation, GateTraceEntry
from src.domain.user_profile import UserProfile
from src.ports.explainability_port import ExplainabilityGeneratorPort


class _FailingExplainabilityGenerator(ExplainabilityGeneratorPort):
    def generate(self, profile, posting, match_score, gated_recommendation):
        return ExplainabilityNote(
            match_rationale="",
            missing_skills=(),
            interview_probability_pct=80,
            effort_estimate="low",
        )


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
        skills=("python", "fastapi"),
        preferred_locations=("Tel Aviv",),
        preferred_languages=(),
        target_seniority="senior",
    )


def test_run_explainability_promotes_valid_top_recommendations():
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
    gated.replace_recommendations(
        [
            GatedRecommendation(
                job_posting_id=saved.id,
                match_score=90,
                profile_version="v1",
                config_version="v1",
                actionable=True,
                gate_trace=(GateTraceEntry(gate="threshold", passed=True, message="ok"),),
                evaluated_at=fixed_now,
            )
        ]
    )
    top = InMemoryTopRecommendationAdapter()
    top.replace_recommendations(
        [
            TopRecommendation(
                job_posting_id=saved.id,
                match_score=90,
                rank=1,
                suppressed=False,
                suppression_reason=None,
                policy_version="v1",
                gate_config_version="v1",
                profile_version="v1",
                evaluated_at=fixed_now,
            )
        ]
    )
    explainable = InMemoryExplainableRecommendationAdapter()
    use_case = GenerateExplainabilityUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        gated_recommendation_repository=gated,
        top_recommendation_repository=top,
        explainable_recommendation_repository=explainable,
        generator=RuleBasedExplainabilityGeneratorAdapter(),
        telemetry=StructuredExplainabilityTelemetryAdapter(),
    )

    result = use_case.run_explainability(correlation_id="explain-1", generated_at=fixed_now)

    assert not isinstance(result, ExplainabilityFailure)
    assert result.promoted_count == 1
    promoted = explainable.list_promoted()[0]
    assert promoted.note is not None
    assert promoted.scoring_config_version == "v1"


def test_run_explainability_persists_quality_failures_without_promotion():
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
    gated.replace_recommendations(
        [
            GatedRecommendation(
                job_posting_id=saved.id,
                match_score=90,
                profile_version="v1",
                config_version="v1",
                actionable=True,
                gate_trace=(),
                evaluated_at=fixed_now,
            )
        ]
    )
    top = InMemoryTopRecommendationAdapter()
    top.replace_recommendations(
        [
            TopRecommendation(
                job_posting_id=saved.id,
                match_score=90,
                rank=1,
                suppressed=False,
                suppression_reason=None,
                policy_version="v1",
                gate_config_version="v1",
                profile_version="v1",
                evaluated_at=fixed_now,
            )
        ]
    )
    explainable = InMemoryExplainableRecommendationAdapter()
    use_case = GenerateExplainabilityUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        gated_recommendation_repository=gated,
        top_recommendation_repository=top,
        explainable_recommendation_repository=explainable,
        generator=_FailingExplainabilityGenerator(),
        telemetry=StructuredExplainabilityTelemetryAdapter(),
    )

    result = use_case.run_explainability(correlation_id="explain-fail", generated_at=fixed_now)

    assert not isinstance(result, ExplainabilityFailure)
    assert result.promoted_count == 0
    assert result.failed_count == 1
    failed = explainable.list_all()[0]
    assert failed.promoted is False
    assert failed.failure_code == "EXPLAINABILITY_RATIONALE_REQUIRED"
    assert explainable.list_promoted() == []


def test_run_explainability_records_context_missing_failures():
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    top = InMemoryTopRecommendationAdapter()
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    top.replace_recommendations(
        [
            TopRecommendation(
                job_posting_id="missing-context",
                match_score=90,
                rank=1,
                suppressed=False,
                suppression_reason=None,
                policy_version="v1",
                gate_config_version="v1",
                profile_version="v1",
                evaluated_at=fixed_now,
            )
        ]
    )
    explainable = InMemoryExplainableRecommendationAdapter()
    use_case = GenerateExplainabilityUseCase(
        profile_repository=profiles,
        job_posting_repository=InMemoryJobPostingAdapter(),
        match_score_repository=InMemoryMatchScoreAdapter(),
        gated_recommendation_repository=InMemoryGatedRecommendationAdapter(),
        top_recommendation_repository=top,
        explainable_recommendation_repository=explainable,
        generator=RuleBasedExplainabilityGeneratorAdapter(),
        telemetry=StructuredExplainabilityTelemetryAdapter(),
    )

    result = use_case.run_explainability(correlation_id="explain-missing", generated_at=fixed_now)

    assert not isinstance(result, ExplainabilityFailure)
    assert result.promoted_count == 0
    assert result.failed_count == 1
    failed = explainable.list_all()[0]
    assert failed.failure_code == "EXPLAINABILITY_CONTEXT_MISSING"
    assert explainable.list_promoted() == []
