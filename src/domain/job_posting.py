from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class JobPostingCompleteness(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class JobPosting:
    id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: datetime | None
    career_source_id: str
    external_id: str
    plugin_id: str
    identity_key: str | None = None
    completeness: JobPostingCompleteness = JobPostingCompleteness.COMPLETE
    rejection_reason: str | None = None
    source_metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        self.updated_at = _utc_now()
