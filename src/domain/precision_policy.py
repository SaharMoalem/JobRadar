from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PrecisionPolicyConfig:
    config_version: str = "v1"
    min_confidence_for_top: int = 85
    max_top_count: int = 10


@dataclass(frozen=True, slots=True)
class TopRecommendation:
    job_posting_id: str
    match_score: int
    rank: int | None
    suppressed: bool
    suppression_reason: str | None
    policy_version: str
    gate_config_version: str
    profile_version: str
    evaluated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class PrecisionBatchResult:
    top_recommendations: tuple[TopRecommendation, ...]
    top_count: int
    suppressed_low_confidence_count: int
    suppressed_capacity_count: int
    actionable_input_count: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class PrecisionFailure:
    code: str
    message: str
    correlation_id: str


class PrecisionValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
