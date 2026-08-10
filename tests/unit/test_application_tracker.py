from datetime import datetime, timezone

import pytest

from src.adapters.persistence.in_memory_application_tracker_adapter import (
    InMemoryApplicationTrackerAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.application.use_cases.application_tracker import ApplicationTrackerUseCase
from src.domain.application_tracker import TrackerState, TrackerValidationError
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState


def _seed_posting(postings: InMemoryJobPostingAdapter, posting_id: str = "job-1") -> str:
    postings.save_posting(
        JobPosting(
            id=posting_id,
            title="Backend Engineer",
            company="Acme",
            location="Tel Aviv",
            url=f"https://jobs.example.com/{posting_id}",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id=posting_id,
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.ACTIVE,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    return postings.list_complete()[0].id


def _use_case() -> tuple[ApplicationTrackerUseCase, str]:
    postings = InMemoryJobPostingAdapter()
    posting_id = _seed_posting(postings)
    use_case = ApplicationTrackerUseCase(
        tracker_repository=InMemoryApplicationTrackerAdapter(),
        job_posting_repository=postings,
    )
    return use_case, posting_id


def test_bookmark_creates_tracked_opportunity_in_new_state():
    use_case, posting_id = _use_case()
    tracked = use_case.bookmark(posting_id, correlation_id="bm-1")
    assert tracked.bookmarked is True
    assert tracked.tracker_state == TrackerState.NEW
    history = use_case.list_history(posting_id)
    assert len(history) == 1
    assert history[0].from_state is None
    assert history[0].to_state == TrackerState.NEW


def test_unbookmark_preserves_tracker_history():
    use_case, posting_id = _use_case()
    use_case.bookmark(posting_id)
    use_case.transition(posting_id, to_state=TrackerState.REVIEW)
    unbookmarked = use_case.unbookmark(posting_id)
    assert unbookmarked.bookmarked is False
    assert unbookmarked.tracker_state == TrackerState.REVIEW
    assert len(use_case.list_history(posting_id)) == 2
    assert use_case.list_bookmarked() == []
    assert len(use_case.list_tracked()) == 1


def test_invalid_transition_rejected():
    use_case, posting_id = _use_case()
    use_case.bookmark(posting_id)
    with pytest.raises(TrackerValidationError) as exc:
        use_case.transition(posting_id, to_state=TrackerState.SUBMITTED)
    assert exc.value.code == "TRACKER_TRANSITION_INVALID"


def test_bookmark_unknown_posting_fails():
    use_case, _ = _use_case()
    with pytest.raises(TrackerValidationError) as exc:
        use_case.bookmark("missing-id")
    assert exc.value.code == "TRACKER_JOB_POSTING_NOT_FOUND"


def test_full_pipeline_through_submitted_and_closed():
    use_case, posting_id = _use_case()
    use_case.bookmark(posting_id)
    use_case.transition(posting_id, to_state=TrackerState.REVIEW)
    use_case.transition(posting_id, to_state=TrackerState.APPLY)
    use_case.transition(posting_id, to_state=TrackerState.SUBMITTED)
    closed = use_case.transition(posting_id, to_state=TrackerState.CLOSED)
    assert closed.tracker_state == TrackerState.CLOSED
    assert [item.to_state for item in use_case.list_history(posting_id)] == [
        TrackerState.NEW,
        TrackerState.REVIEW,
        TrackerState.APPLY,
        TrackerState.SUBMITTED,
        TrackerState.CLOSED,
    ]


def test_rebookmark_restores_flag_and_preserves_state():
    use_case, posting_id = _use_case()
    use_case.bookmark(posting_id)
    use_case.transition(posting_id, to_state=TrackerState.REVIEW)
    use_case.unbookmark(posting_id)
    restored = use_case.bookmark(posting_id)
    assert restored.bookmarked is True
    assert restored.tracker_state == TrackerState.REVIEW
    assert len(use_case.list_history(posting_id)) == 2
