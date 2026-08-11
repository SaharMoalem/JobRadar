from datetime import datetime, timedelta, timezone

from src.adapters.observability.structured_morning_digest_telemetry_adapter import (
    StructuredMorningDigestTelemetryAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_morning_digest_adapter import (
    InMemoryMorningDigestAdapter,
    InMemoryMorningDigestConfigAdapter,
)
from src.adapters.persistence.in_memory_top_recommendation_adapter import (
    InMemoryTopRecommendationAdapter,
)
from src.application.use_cases.generate_morning_digest import GenerateMorningDigestUseCase
from src.application.use_cases.morning_digest_config import MorningDigestConfigService
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState, JobLifecycleTransition
from src.domain.match_scoring import MatchScore
from src.domain.morning_digest import MorningDigestFailure
from src.domain.precision_policy import TopRecommendation


NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _posting(job_posting_id: str, *, state: JobLifecycleState = JobLifecycleState.NEW) -> JobPosting:
    return JobPosting(
        id=job_posting_id,
        title=f"Role {job_posting_id}",
        company="Acme",
        location="Tel Aviv",
        url=f"https://jobs.example.com/{job_posting_id}",
        posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id=job_posting_id,
        plugin_id="generic",
        lifecycle_state=state,
        completeness=JobPostingCompleteness.COMPLETE,
    )


def _score(job_posting_id: str, score: int) -> MatchScore:
    return MatchScore(
        job_posting_id=job_posting_id,
        score=score,
        profile_version="v1",
        config_version="v1",
        signal_breakdown={},
    )


def _top(job_posting_id: str, score: int, rank: int) -> TopRecommendation:
    return TopRecommendation(
        job_posting_id=job_posting_id,
        match_score=score,
        rank=rank,
        suppressed=False,
        suppression_reason=None,
        policy_version="v1",
        gate_config_version="v1",
        profile_version="v1",
        evaluated_at=NOW,
    )


def _transition(
    job_posting_id: str,
    to_state: JobLifecycleState,
    *,
    hours_ago: int,
) -> JobLifecycleTransition:
    return JobLifecycleTransition(
        job_posting_id=job_posting_id,
        from_state=None,
        to_state=to_state,
        reason="test",
        correlation_id="seed",
        transitioned_at=NOW - timedelta(hours=hours_ago),
    )


def _use_case(
    *,
    postings: InMemoryJobPostingAdapter,
    scores: InMemoryMatchScoreAdapter,
    tops: InMemoryTopRecommendationAdapter,
    configs: InMemoryMorningDigestConfigAdapter | None = None,
    digests: InMemoryMorningDigestAdapter | None = None,
    telemetry: StructuredMorningDigestTelemetryAdapter | None = None,
) -> GenerateMorningDigestUseCase:
    return GenerateMorningDigestUseCase(
        job_posting_repository=postings,
        match_score_repository=scores,
        top_recommendation_repository=tops,
        digest_config_repository=configs or InMemoryMorningDigestConfigAdapter(),
        digest_repository=digests or InMemoryMorningDigestAdapter(),
        telemetry=telemetry or StructuredMorningDigestTelemetryAdapter(),
    )


def test_config_service_defaults_and_persists():
    service = MorningDigestConfigService(repository=InMemoryMorningDigestConfigAdapter())
    assert service.get().digest_threshold == 80
    saved = service.save(digest_threshold=75, digest_window_hours=12, top_n=3)
    assert saved.digest_threshold == 75
    assert saved.digest_window_hours == 12
    assert saved.top_n == 3


def test_generate_digest_sections_and_top_five():
    postings = InMemoryJobPostingAdapter()
    new_posting = postings.save_posting(_posting("job-new"))
    updated_posting = postings.save_posting(_posting("job-upd", state=JobLifecycleState.UPDATED))
    expired_posting = postings.save_posting(_posting("job-exp", state=JobLifecycleState.EXPIRED))
    low_posting = postings.save_posting(_posting("job-low"))
    top_postings = [
        postings.save_posting(_posting(f"top-{idx}")) for idx in range(1, 7)
    ]
    postings._transitions = [
        _transition(new_posting.id, JobLifecycleState.NEW, hours_ago=2),
        _transition(updated_posting.id, JobLifecycleState.UPDATED, hours_ago=3),
        _transition(expired_posting.id, JobLifecycleState.EXPIRED, hours_ago=4),
        _transition(low_posting.id, JobLifecycleState.NEW, hours_ago=1),
    ]
    scores = InMemoryMatchScoreAdapter()
    scores.replace_scores(
        [
            _score(new_posting.id, 90),
            _score(updated_posting.id, 85),
            _score(expired_posting.id, 82),
            _score(low_posting.id, 70),
            *[_score(item.id, 95 - idx) for idx, item in enumerate(top_postings)],
        ]
    )
    tops = InMemoryTopRecommendationAdapter()
    tops.replace_recommendations(
        [_top(item.id, 95 - idx, idx + 1) for idx, item in enumerate(top_postings)]
    )
    digests = InMemoryMorningDigestAdapter()
    use_case = _use_case(postings=postings, scores=scores, tops=tops, digests=digests)

    result = use_case.run(correlation_id="digest-1", run_context="2026-08-11", now=NOW)

    assert result.digest.is_noop is False
    assert [item.job_posting_id for item in result.digest.new_items] == [new_posting.id]
    assert [item.job_posting_id for item in result.digest.updated_items] == [updated_posting.id]
    assert [item.job_posting_id for item in result.digest.expired_items] == [expired_posting.id]
    assert result.digest.skipped_below_threshold_count == 1
    assert len(result.digest.top_recommendations) == 5
    assert [item.rank for item in result.digest.top_recommendations] == [1, 2, 3, 4, 5]


def test_empty_digest_is_successful_noop():
    use_case = _use_case(
        postings=InMemoryJobPostingAdapter(),
        scores=InMemoryMatchScoreAdapter(),
        tops=InMemoryTopRecommendationAdapter(),
    )

    result = use_case.run(correlation_id="empty", run_context="noop-day", now=NOW)

    assert result.digest.is_noop is True
    assert result.digest.new_items == ()
    assert result.digest.updated_items == ()
    assert result.digest.expired_items == ()
    assert result.digest.top_recommendations == ()


def test_replace_for_same_run_context():
    postings = InMemoryJobPostingAdapter()
    posting = postings.save_posting(_posting("job-a"))
    postings._transitions = [_transition(posting.id, JobLifecycleState.NEW, hours_ago=1)]
    scores = InMemoryMatchScoreAdapter()
    scores.replace_scores([_score(posting.id, 90)])
    digests = InMemoryMorningDigestAdapter()
    use_case = _use_case(
        postings=postings,
        scores=scores,
        tops=InMemoryTopRecommendationAdapter(),
        digests=digests,
    )

    first = use_case.run(correlation_id="c1", run_context="same-day", now=NOW)
    second = use_case.run(correlation_id="c2", run_context="same-day", now=NOW)

    assert first.digest.id != second.digest.id
    assert len(digests.list_digests()) == 1
    assert digests.get_by_run_context("same-day").correlation_id == "c2"


def test_missing_score_is_counted():
    postings = InMemoryJobPostingAdapter()
    posting = postings.save_posting(_posting("orphan-score"))
    postings._transitions = [_transition(posting.id, JobLifecycleState.NEW, hours_ago=1)]
    telemetry = StructuredMorningDigestTelemetryAdapter()
    use_case = _use_case(
        postings=postings,
        scores=InMemoryMatchScoreAdapter(),
        tops=InMemoryTopRecommendationAdapter(),
        telemetry=telemetry,
    )

    result = use_case.run(correlation_id="missing-score", run_context="day", now=NOW)

    assert result.digest.skipped_missing_score_count == 1
    assert result.digest.new_items == ()
    assert telemetry.snapshot_metrics()["morning_digest_skipped_missing_score_total"] == 1


def test_blank_correlation_rejected():
    use_case = _use_case(
        postings=InMemoryJobPostingAdapter(),
        scores=InMemoryMatchScoreAdapter(),
        tops=InMemoryTopRecommendationAdapter(),
    )
    result = use_case.run(correlation_id="  ")
    assert isinstance(result, MorningDigestFailure)
    assert result.code == "DIGEST_CORRELATION_ID_REQUIRED"


def test_blank_run_context_rejected():
    use_case = _use_case(
        postings=InMemoryJobPostingAdapter(),
        scores=InMemoryMatchScoreAdapter(),
        tops=InMemoryTopRecommendationAdapter(),
    )
    result = use_case.run(correlation_id="ok", run_context="   ")
    assert isinstance(result, MorningDigestFailure)
    assert result.code == "DIGEST_RUN_CONTEXT_INVALID"


def test_top_n_backfills_when_posting_missing():
    postings = InMemoryJobPostingAdapter()
    kept = [postings.save_posting(_posting(f"keep-{idx}")) for idx in range(1, 6)]
    scores = InMemoryMatchScoreAdapter()
    scores.replace_scores([_score(item.id, 90) for item in kept])
    tops = InMemoryTopRecommendationAdapter()
    tops.replace_recommendations(
        [
            _top("missing-top", 99, 1),
            *[_top(item.id, 95 - idx, idx + 2) for idx, item in enumerate(kept)],
        ]
    )
    use_case = _use_case(postings=postings, scores=scores, tops=tops)

    result = use_case.run(correlation_id="backfill", run_context="day", now=NOW)

    assert len(result.digest.top_recommendations) == 5
    assert result.digest.skipped_missing_posting_count == 1
    assert all(item.job_posting_id != "missing-top" for item in result.digest.top_recommendations)
    assert {item.job_posting_id for item in result.digest.top_recommendations} == {
        item.id for item in kept
    }


def test_non_iso_run_context_does_not_become_digest_date():
    use_case = _use_case(
        postings=InMemoryJobPostingAdapter(),
        scores=InMemoryMatchScoreAdapter(),
        tops=InMemoryTopRecommendationAdapter(),
    )
    result = use_case.run(correlation_id="c1", run_context="manual-run", now=NOW)
    assert result.digest.digest_date == "2026-08-11"
    assert result.digest.run_context == "manual-run"
