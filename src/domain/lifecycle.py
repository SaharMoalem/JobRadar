from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class JobLifecycleState(str, Enum):
    NEW = "new"
    UPDATED = "updated"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class JobLifecycleTransition:
    job_posting_id: str
    from_state: JobLifecycleState | None
    to_state: JobLifecycleState
    reason: str
    correlation_id: str
    transitioned_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class RetentionBatchResult:
    archived_count: int
    correlation_id: str
    evaluated_at: datetime
