from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TrackerState(str, Enum):
    NEW = "new"
    REVIEW = "review"
    APPLY = "apply"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    CLOSED = "closed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TrackedOpportunity:
    job_posting_id: str
    tracker_state: TrackerState = TrackerState.NEW
    bookmarked: bool = True
    bookmarked_at: datetime | None = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        self.updated_at = _utc_now()


@dataclass(frozen=True, slots=True)
class TrackerTransition:
    job_posting_id: str
    from_state: TrackerState | None
    to_state: TrackerState
    reason: str
    correlation_id: str
    transitioned_at: datetime = field(default_factory=_utc_now)


class TrackerValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
