from __future__ import annotations

from datetime import datetime, timezone

from src.domain.opportunity_search import OpportunityFilterState, OpportunitySearchCriteria
from src.ports.opportunity_search_port import OpportunityFilterStateRepositoryPort


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryOpportunityFilterStateAdapter(OpportunityFilterStateRepositoryPort):
    def __init__(self) -> None:
        self._states: dict[str, OpportunityFilterState] = {}

    def get_state(self, session_id: str) -> OpportunityFilterState | None:
        return self._states.get(session_id)

    def save_state(
        self,
        session_id: str,
        criteria: OpportunitySearchCriteria,
    ) -> OpportunityFilterState:
        state = OpportunityFilterState(
            session_id=session_id,
            criteria=criteria,
            updated_at=_utc_now(),
        )
        self._states[session_id] = state
        return state
