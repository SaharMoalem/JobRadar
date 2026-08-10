from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.domain.lifecycle import JobLifecycleState


class WorkModel(str, Enum):
    HYBRID = "hybrid"
    ON_SITE = "on_site"
    REMOTE = "remote"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OpportunitySearchCriteria:
    role_family: str | None = None
    location: str | None = None
    work_model: WorkModel | None = None
    min_score: int | None = None
    max_score: int | None = None
    freshness_days: int | None = None
    lifecycle_states: tuple[JobLifecycleState, ...] | None = None


@dataclass(frozen=True, slots=True)
class OpportunityFilterState:
    session_id: str
    criteria: OpportunitySearchCriteria
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class OpportunityItem:
    job_posting_id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: datetime | None
    lifecycle_state: JobLifecycleState
    role_family: str
    work_model: WorkModel
    match_score: int | None


@dataclass(frozen=True, slots=True)
class OpportunitySearchResult:
    items: tuple[OpportunityItem, ...]
    total_count: int
    is_empty: bool
    criteria: OpportunitySearchCriteria


class OpportunitySearchValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
