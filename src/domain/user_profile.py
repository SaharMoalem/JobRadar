from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class UserProfile:
    skills: tuple[str, ...]
    preferred_locations: tuple[str, ...]
    preferred_languages: tuple[str, ...]
    target_seniority: str
    id: str = "default"
    profile_version: str = "v1"
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        self.updated_at = _utc_now()
