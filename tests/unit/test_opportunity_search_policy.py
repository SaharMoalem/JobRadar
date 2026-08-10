from datetime import datetime, timezone

import pytest

from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.opportunity_search import OpportunitySearchCriteria, OpportunitySearchValidationError, WorkModel
from src.domain.opportunity_search_policy import search_opportunities, validate_search_criteria


def _posting(
    *,
    posting_id: str,
    title: str = "Backend Engineer",
    location: str = "Tel Aviv, Israel",
    role_family: str = "engineering",
    work_model: str = "hybrid",
    lifecycle_state: JobLifecycleState = JobLifecycleState.ACTIVE,
    posted_at: datetime | None = None,
) -> JobPosting:
    return JobPosting(
        id=posting_id,
        title=title,
        company="Acme",
        location=location,
        url=f"https://jobs.example.com/{posting_id}",
        posted_at=posted_at or datetime(2026, 7, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id=posting_id,
        plugin_id="generic",
        lifecycle_state=lifecycle_state,
        completeness=JobPostingCompleteness.COMPLETE,
        source_metadata={"role_family": role_family, "work_model": work_model},
    )


def test_validate_search_criteria_rejects_invalid_score_range():
    criteria = OpportunitySearchCriteria(min_score=90, max_score=70)
    with pytest.raises(OpportunitySearchValidationError) as exc:
        validate_search_criteria(criteria)
    assert exc.value.code == "SEARCH_SCORE_RANGE_INVALID"


def test_search_filters_by_role_family_location_and_work_model():
    postings = [
        _posting(posting_id="eng-hybrid", role_family="engineering", work_model="hybrid"),
        _posting(
            posting_id="data-remote",
            title="Data Analyst",
            location="Remote",
            role_family="data",
            work_model="remote",
        ),
    ]
    criteria = OpportunitySearchCriteria(
        role_family="data",
        location="remote",
        work_model=WorkModel.REMOTE,
    )
    result = search_opportunities(postings, {}, criteria=criteria)
    assert result.total_count == 1
    assert result.items[0].job_posting_id == "data-remote"


def test_search_excludes_postings_without_score_when_score_range_set():
    postings = [_posting(posting_id="eng-hybrid")]
    scores = {
        "eng-hybrid": MatchScore(
            job_posting_id="eng-hybrid",
            score=75,
            profile_version="v1",
            config_version="v1",
            signal_breakdown={},
        )
    }
    criteria = OpportunitySearchCriteria(min_score=80)
    result = search_opportunities(postings, scores, criteria=criteria)
    assert result.is_empty is True


def test_search_sorts_by_work_model_priority_then_score():
    postings = [
        _posting(posting_id="remote-role", work_model="remote"),
        _posting(posting_id="hybrid-role", work_model="hybrid"),
        _posting(posting_id="onsite-role", work_model="on_site"),
    ]
    scores = {
        posting_id: MatchScore(
            job_posting_id=posting_id,
            score=80,
            profile_version="v1",
            config_version="v1",
            signal_breakdown={},
        )
        for posting_id in ("remote-role", "hybrid-role", "onsite-role")
    }
    result = search_opportunities(postings, scores, criteria=OpportunitySearchCriteria(min_score=0))
    assert [item.job_posting_id for item in result.items] == [
        "hybrid-role",
        "onsite-role",
        "remote-role",
    ]


def test_role_family_filter_is_metadata_exact_match_not_title():
    postings = [
        _posting(
            posting_id="eng-data-title",
            title="Data Platform Engineer",
            role_family="engineering",
        ),
    ]
    result = search_opportunities(
        postings,
        {},
        criteria=OpportunitySearchCriteria(role_family="data"),
    )
    assert result.is_empty is True


def test_search_filters_by_freshness_days():
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    postings = [
        _posting(posting_id="fresh", posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
        _posting(posting_id="stale", posted_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
    ]
    result = search_opportunities(
        postings,
        {},
        criteria=OpportunitySearchCriteria(freshness_days=14),
        now=now,
    )
    assert result.total_count == 1
    assert result.items[0].job_posting_id == "fresh"


def test_search_filters_by_lifecycle_states():
    postings = [
        _posting(posting_id="active", lifecycle_state=JobLifecycleState.ACTIVE),
        _posting(posting_id="expired", lifecycle_state=JobLifecycleState.EXPIRED),
    ]
    default_result = search_opportunities(postings, {}, criteria=OpportunitySearchCriteria())
    assert [item.job_posting_id for item in default_result.items] == ["active"]

    expired_only = search_opportunities(
        postings,
        {},
        criteria=OpportunitySearchCriteria(lifecycle_states=(JobLifecycleState.EXPIRED,)),
    )
    assert [item.job_posting_id for item in expired_only.items] == ["expired"]
