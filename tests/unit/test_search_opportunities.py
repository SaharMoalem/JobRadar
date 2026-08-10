from datetime import datetime, timezone

import pytest

from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_opportunity_filter_state_adapter import (
    InMemoryOpportunityFilterStateAdapter,
)
from src.application.use_cases.search_opportunities import SearchOpportunitiesUseCase
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.opportunity_search import (
    OpportunitySearchCriteria,
    OpportunitySearchValidationError,
    WorkModel,
)


def _seed_posting(posting_id: str, *, role_family: str, work_model: str) -> JobPosting:
    return JobPosting(
        id=posting_id,
        title=f"{role_family} role",
        company="Acme",
        location="Tel Aviv, Israel",
        url=f"https://jobs.example.com/{posting_id}",
        posted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id=posting_id,
        plugin_id="generic",
        lifecycle_state=JobLifecycleState.ACTIVE,
        completeness=JobPostingCompleteness.COMPLETE,
        source_metadata={"role_family": role_family, "work_model": work_model},
    )


def test_search_persists_filter_state_for_session():
    postings = InMemoryJobPostingAdapter()
    postings.save_posting(_seed_posting("one", role_family="engineering", work_model="hybrid"))
    match_scores = InMemoryMatchScoreAdapter()
    filter_states = InMemoryOpportunityFilterStateAdapter()
    use_case = SearchOpportunitiesUseCase(
        job_posting_repository=postings,
        match_score_repository=match_scores,
        filter_state_repository=filter_states,
    )
    criteria = OpportunitySearchCriteria(role_family="engineering", work_model=WorkModel.HYBRID)

    result = use_case.search(criteria, session_id="dashboard-1")
    saved = use_case.get_filter_state("dashboard-1")

    assert result.total_count == 1
    assert saved is not None
    assert saved.criteria.role_family == "engineering"
    assert saved.criteria.work_model == WorkModel.HYBRID


def test_invalid_search_does_not_persist_filter_state():
    use_case = SearchOpportunitiesUseCase(
        job_posting_repository=InMemoryJobPostingAdapter(),
        match_score_repository=InMemoryMatchScoreAdapter(),
        filter_state_repository=InMemoryOpportunityFilterStateAdapter(),
    )
    with pytest.raises(OpportunitySearchValidationError) as exc:
        use_case.search(
            OpportunitySearchCriteria(min_score=90, max_score=10),
            session_id="bad-session",
        )
    assert exc.value.code == "SEARCH_SCORE_RANGE_INVALID"
    assert use_case.get_filter_state("bad-session") is None


def test_save_filter_state_validates_criteria():
    use_case = SearchOpportunitiesUseCase(
        job_posting_repository=InMemoryJobPostingAdapter(),
        match_score_repository=InMemoryMatchScoreAdapter(),
        filter_state_repository=InMemoryOpportunityFilterStateAdapter(),
    )
    with pytest.raises(OpportunitySearchValidationError) as exc:
        use_case.save_filter_state(
            OpportunitySearchCriteria(min_score=150),
            session_id="bad-put",
        )
    assert exc.value.code == "SEARCH_SCORE_OUT_OF_RANGE"
    assert use_case.get_filter_state("bad-put") is None
