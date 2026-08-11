from src.domain.immediate_alert import ImmediateAlertConfig, ImmediateAlertValidationError
from src.domain.immediate_alert_policy import (
    build_deep_link,
    build_role_summary,
    qualifies_for_alert,
    select_alert_candidates,
    validate_alert_config,
)
from src.domain.job_posting import JobPosting
from src.domain.recommendation_gating import GatedRecommendation
from datetime import datetime, timezone


def _gated(job_posting_id: str, match_score: int, *, actionable: bool = True) -> GatedRecommendation:
    return GatedRecommendation(
        job_posting_id=job_posting_id,
        match_score=match_score,
        profile_version="v1",
        config_version="v1",
        actionable=actionable,
        gate_trace=(),
        evaluated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )


def test_validate_alert_config_rejects_out_of_range():
    try:
        validate_alert_config(ImmediateAlertConfig(alert_threshold=101))
        raise AssertionError("expected validation error")
    except ImmediateAlertValidationError as exc:
        assert exc.code == "ALERT_THRESHOLD_OUT_OF_RANGE"


def test_default_threshold_is_ninety():
    assert ImmediateAlertConfig().alert_threshold == 90


def test_qualifies_for_alert_requires_actionable_and_threshold():
    assert qualifies_for_alert(_gated("a", 90), threshold=90)
    assert not qualifies_for_alert(_gated("a", 89), threshold=90)
    assert not qualifies_for_alert(_gated("a", 95, actionable=False), threshold=90)


def test_select_alert_candidates_dedups_by_job_posting_id():
    selected = select_alert_candidates(
        [
            _gated("job-a", 91),
            _gated("job-a", 95),
            _gated("job-b", 88),
            _gated("job-c", 92),
        ],
        threshold=90,
    )
    assert [item.job_posting_id for item in selected] == ["job-a", "job-c"]
    assert selected[0].match_score == 95


def test_role_summary_and_deep_link():
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
    )
    assert build_role_summary(posting) == "Backend Engineer at Acme (Tel Aviv)"
    assert build_deep_link("job-1") == "/job-postings/job-1"
