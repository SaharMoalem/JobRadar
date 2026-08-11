from datetime import datetime, timedelta, timezone

from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState, JobLifecycleTransition
from src.domain.morning_digest import MorningDigestConfig, MorningDigestValidationError
from src.domain.morning_digest_policy import (
    bucket_transitions,
    build_deep_link,
    build_role_summary,
    default_run_context,
    latest_change_transitions,
    qualifies_for_change_section,
    resolve_digest_date,
    select_top_recommendations,
    transitions_in_window,
    validate_digest_config,
)
from src.domain.precision_policy import TopRecommendation


def _transition(
    job_posting_id: str,
    to_state: JobLifecycleState,
    *,
    at: datetime,
) -> JobLifecycleTransition:
    return JobLifecycleTransition(
        job_posting_id=job_posting_id,
        from_state=None,
        to_state=to_state,
        reason="test",
        correlation_id="c1",
        transitioned_at=at,
    )


def test_default_digest_threshold_is_eighty():
    assert MorningDigestConfig().digest_threshold == 80
    assert MorningDigestConfig().top_n == 5
    assert MorningDigestConfig().digest_window_hours == 24


def test_validate_digest_config_rejects_invalid_values():
    try:
        validate_digest_config(MorningDigestConfig(digest_threshold=101))
        raise AssertionError("expected validation error")
    except MorningDigestValidationError as exc:
        assert exc.code == "DIGEST_THRESHOLD_OUT_OF_RANGE"

    try:
        validate_digest_config(MorningDigestConfig(digest_window_hours=0))
        raise AssertionError("expected validation error")
    except MorningDigestValidationError as exc:
        assert exc.code == "DIGEST_WINDOW_INVALID"

    try:
        validate_digest_config(MorningDigestConfig(digest_window_hours=8761))
        raise AssertionError("expected validation error")
    except MorningDigestValidationError as exc:
        assert exc.code == "DIGEST_WINDOW_INVALID"

    try:
        validate_digest_config(MorningDigestConfig(top_n=11))
        raise AssertionError("expected validation error")
    except MorningDigestValidationError as exc:
        assert exc.code == "DIGEST_TOP_N_OUT_OF_RANGE"


def test_transitions_in_window_filters_time_keeps_all_states():
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    transitions = [
        _transition("a", JobLifecycleState.NEW, at=now - timedelta(hours=1)),
        _transition("b", JobLifecycleState.ACTIVE, at=now - timedelta(hours=1)),
        _transition("c", JobLifecycleState.EXPIRED, at=now - timedelta(hours=30)),
        _transition("d", JobLifecycleState.ARCHIVED, at=now - timedelta(hours=2)),
    ]
    selected = transitions_in_window(
        transitions,
        window_start_at=now - timedelta(hours=24),
        window_end_at=now,
    )
    assert {item.job_posting_id for item in selected} == {"a", "b", "d"}


def test_latest_change_excludes_stale_new_after_active():
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    transitions = [
        _transition("job-1", JobLifecycleState.NEW, at=now - timedelta(hours=3)),
        _transition("job-1", JobLifecycleState.ACTIVE, at=now - timedelta(hours=1)),
        _transition("job-2", JobLifecycleState.EXPIRED, at=now - timedelta(hours=2)),
        _transition("job-3", JobLifecycleState.ARCHIVED, at=now - timedelta(hours=1)),
    ]
    latest = latest_change_transitions(transitions)
    by_id = {item.job_posting_id: item for item in latest}
    assert "job-1" not in by_id
    assert "job-3" not in by_id
    assert by_id["job-2"].to_state == JobLifecycleState.EXPIRED


def test_same_timestamp_tie_break_is_deterministic():
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    transitions = [
        _transition("job-1", JobLifecycleState.NEW, at=now),
        _transition("job-1", JobLifecycleState.UPDATED, at=now),
    ]
    latest = latest_change_transitions(transitions)
    assert len(latest) == 1
    assert latest[0].to_state == JobLifecycleState.UPDATED


def test_bucket_transitions_groups_sections():
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    buckets = bucket_transitions(
        [
            _transition("n", JobLifecycleState.NEW, at=now),
            _transition("u", JobLifecycleState.UPDATED, at=now),
            _transition("e", JobLifecycleState.EXPIRED, at=now),
        ]
    )
    assert [item.job_posting_id for item in buckets[JobLifecycleState.NEW]] == ["n"]
    assert [item.job_posting_id for item in buckets[JobLifecycleState.UPDATED]] == ["u"]
    assert [item.job_posting_id for item in buckets[JobLifecycleState.EXPIRED]] == ["e"]


def test_qualifies_for_change_section():
    assert qualifies_for_change_section(match_score=80, threshold=80)
    assert not qualifies_for_change_section(match_score=79, threshold=80)
    assert not qualifies_for_change_section(match_score=None, threshold=80)


def test_select_top_recommendations_backfills_missing_postings():
    recs = [
        TopRecommendation(
            job_posting_id=f"job-{idx}",
            match_score=100 - idx,
            rank=idx,
            suppressed=False,
            suppression_reason=None,
            policy_version="v1",
            gate_config_version="v1",
            profile_version="v1",
        )
        for idx in range(1, 8)
    ]
    selected, skipped = select_top_recommendations(
        recs,
        top_n=5,
        available_posting_ids={"job-2", "job-3", "job-4", "job-5", "job-6", "job-7"},
    )
    assert [item.job_posting_id for item in selected] == [
        "job-2",
        "job-3",
        "job-4",
        "job-5",
        "job-6",
    ]
    assert skipped == 1


def test_resolve_digest_date_and_summaries():
    posting = JobPosting(
        id="job-1",
        title="Backend Engineer",
        company="Acme",
        location="Tel Aviv",
        url="https://jobs.example.com/1",
        posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id="ext-1",
        plugin_id="generic",
        completeness=JobPostingCompleteness.COMPLETE,
        lifecycle_state=JobLifecycleState.NEW,
    )
    assert build_role_summary(posting) == "Backend Engineer at Acme (Tel Aviv)"
    assert build_deep_link("job-1") == "/job-postings/job-1"
    assert default_run_context(now=datetime(2026, 8, 11, 9, tzinfo=timezone.utc)) == "2026-08-11"
    assert resolve_digest_date(
        run_context="2026-08-11",
        evaluated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    ) == "2026-08-11"
    assert resolve_digest_date(
        run_context="manual-run",
        evaluated_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
    ) == "2026-08-12"
