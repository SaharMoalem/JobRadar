from __future__ import annotations

from typing import Protocol

from src.domain.opportunity_search import OpportunityFilterState, OpportunitySearchCriteria


class OpportunityFilterStateRepositoryPort(Protocol):
    def get_state(self, session_id: str) -> OpportunityFilterState | None: ...

    def save_state(
        self,
        session_id: str,
        criteria: OpportunitySearchCriteria,
    ) -> OpportunityFilterState: ...
