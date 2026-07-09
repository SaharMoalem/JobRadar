from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CareerSourceStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CareerSource:
    id: str
    name: str
    base_url: str
    status: CareerSourceStatus = CareerSourceStatus.DISABLED
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def set_status(self, status: CareerSourceStatus) -> None:
        self.status = status
        self.touch()
