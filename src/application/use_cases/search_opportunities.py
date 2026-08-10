from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.opportunity_search import (
    OpportunityFilterState,
    OpportunitySearchCriteria,
    OpportunitySearchResult,
)
from src.domain.opportunity_search_policy import search_opportunities, validate_search_criteria
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.match_scoring_port import MatchScoreRepositoryPort
from src.ports.opportunity_search_port import OpportunityFilterStateRepositoryPort


@dataclass(slots=True)
class SearchOpportunitiesUseCase:
    job_posting_repository: JobPostingRepositoryPort
    match_score_repository: MatchScoreRepositoryPort
    filter_state_repository: OpportunityFilterStateRepositoryPort

    def search(
        self,
        criteria: OpportunitySearchCriteria,
        *,
        session_id: str = "default",
        now: datetime | None = None,
    ) -> OpportunitySearchResult:
        validate_search_criteria(criteria)
        result = self._execute_search(criteria, now=now)
        self.filter_state_repository.save_state(session_id, criteria)
        return result

    def get_filter_state(self, session_id: str = "default") -> OpportunityFilterState | None:
        return self.filter_state_repository.get_state(session_id)

    def save_filter_state(
        self,
        criteria: OpportunitySearchCriteria,
        *,
        session_id: str = "default",
    ) -> OpportunityFilterState:
        validate_search_criteria(criteria)
        return self.filter_state_repository.save_state(session_id, criteria)

    def _execute_search(
        self,
        criteria: OpportunitySearchCriteria,
        *,
        now: datetime | None = None,
    ) -> OpportunitySearchResult:
        postings = self.job_posting_repository.list_complete()
        scores_by_id = {
            score.job_posting_id: score for score in self.match_score_repository.list_scores()
        }
        evaluated_at = now or datetime.now(timezone.utc)
        return search_opportunities(
            postings,
            scores_by_id,
            criteria=criteria,
            now=evaluated_at,
        )
