from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class MatchScoringConfig:
    config_version: str = "v1"
    skill_weight: int = 50
    location_weight: int = 25
    language_weight: int = 15
    recency_weight: int = 10
    recency_window_days: int = 14


@dataclass(frozen=True, slots=True)
class MatchScore:
    job_posting_id: str
    score: int
    profile_version: str
    config_version: str
    signal_breakdown: dict[str, int]
    computed_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class ScoringBatchResult:
    scores: tuple[MatchScore, ...]
    scored_count: int
    skipped_count: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ScoringFailure:
    code: str
    message: str
    correlation_id: str


class ScoringValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
