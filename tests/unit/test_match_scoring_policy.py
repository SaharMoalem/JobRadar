from datetime import datetime, timezone

from src.adapters.observability.structured_scoring_telemetry_adapter import (
    StructuredScoringTelemetryAdapter,
)
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_user_profile_adapter import InMemoryUserProfileAdapter
from src.application.use_cases.score_job_postings import ScoreJobPostingsUseCase
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScoringConfig, ScoringFailure
from src.domain.match_scoring_policy import compute_match_score
from src.domain.user_profile import UserProfile


def _posting(**overrides) -> JobPosting:
    defaults = {
        "id": "job-1",
        "title": "Senior Python Engineer",
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
        preferred_languages=("english",),
        target_seniority="senior",
    )


def test_compute_match_score_is_deterministic():
    profile = _profile()
    posting = _posting()
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)
    config = MatchScoringConfig()

    first = compute_match_score(profile, posting, config=config, now=fixed_now)
    second = compute_match_score(profile, posting, config=config, now=fixed_now)

    assert first.score == second.score
    assert 0 <= first.score <= 100
    assert first.signal_breakdown == second.signal_breakdown


def test_invalid_profile_returns_failure_without_persisting_scores():
    from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter

    postings = InMemoryJobPostingAdapter()
    postings.save_posting(_posting())
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(
        UserProfile(
            skills=(),
            preferred_locations=("Tel Aviv",),
            preferred_languages=(),
            target_seniority="senior",
        )
    )
    scores = InMemoryMatchScoreAdapter()
    telemetry = StructuredScoringTelemetryAdapter()
    use_case = ScoreJobPostingsUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        telemetry=telemetry,
    )

    result = use_case.score_all_eligible(correlation_id="score-fail")

    assert isinstance(result, ScoringFailure)
    assert result.code == "PROFILE_SKILLS_REQUIRED"
    assert scores.list_scores() == []
    assert telemetry.snapshot_metrics()["scoring_failures_total"] == 1


def test_score_all_eligible_persists_scores():
    from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter

    postings = InMemoryJobPostingAdapter()
    postings.save_posting(_posting())
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    scores = InMemoryMatchScoreAdapter()
    telemetry = StructuredScoringTelemetryAdapter()
    use_case = ScoreJobPostingsUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        telemetry=telemetry,
    )
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)

    result = use_case.score_all_eligible(correlation_id="score-1", evaluated_at=fixed_now)

    assert not isinstance(result, ScoringFailure)
    assert result.scored_count == 1
    assert scores.list_scores()[0].score == result.scores[0].score
    assert scores.list_scores()[0].computed_at == fixed_now


def test_score_run_replaces_stale_scores_for_ineligible_postings():
    from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
    from src.domain.match_scoring import MatchScore

    postings = InMemoryJobPostingAdapter()
    active = postings.save_posting(_posting(id="job-active"))
    postings.save_posting(_posting(id="job-expired", lifecycle_state=JobLifecycleState.EXPIRED))
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    scores = InMemoryMatchScoreAdapter()
    seeded_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=active.id,
                score=80,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={"skills": 40},
                computed_at=seeded_at,
            ),
            MatchScore(
                job_posting_id="stale-expired-score",
                score=60,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={"skills": 30},
                computed_at=seeded_at,
            ),
        ]
    )
    use_case = ScoreJobPostingsUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        telemetry=StructuredScoringTelemetryAdapter(),
    )

    result = use_case.score_all_eligible(
        correlation_id="score-prune",
        evaluated_at=datetime(2026, 7, 5, tzinfo=timezone.utc),
    )

    assert not isinstance(result, ScoringFailure)
    assert result.scored_count == 1
    assert {score.job_posting_id for score in scores.list_scores()} == {active.id}


def test_batch_scoring_is_deterministic_with_fixed_evaluated_at():
    from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter

    postings = InMemoryJobPostingAdapter()
    postings.save_posting(_posting())
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(_profile())
    scores = InMemoryMatchScoreAdapter()
    use_case = ScoreJobPostingsUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=scores,
        telemetry=StructuredScoringTelemetryAdapter(),
    )
    fixed_now = datetime(2026, 7, 5, tzinfo=timezone.utc)

    first = use_case.score_all_eligible(correlation_id="score-a", evaluated_at=fixed_now)
    second = use_case.score_all_eligible(correlation_id="score-b", evaluated_at=fixed_now)

    assert not isinstance(first, ScoringFailure)
    assert not isinstance(second, ScoringFailure)
    assert first.scores[0].score == second.scores[0].score
    assert first.scores[0].computed_at == second.scores[0].computed_at
