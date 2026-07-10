from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ExplainabilityNote:
    match_rationale: str
    missing_skills: tuple[str, ...]
    interview_probability_pct: int
    effort_estimate: str


@dataclass(frozen=True, slots=True)
class ExplainableRecommendation:
    job_posting_id: str
    match_score: int
    profile_version: str
    scoring_config_version: str
    gate_config_version: str
    policy_version: str
    promoted: bool
    note: ExplainabilityNote | None
    failure_code: str | None
    failure_reason: str | None
    generated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class ExplainabilityBatchResult:
    recommendations: tuple[ExplainableRecommendation, ...]
    promoted_count: int
    failed_count: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ExplainabilityFailure:
    code: str
    message: str
    correlation_id: str


class ExplainabilityQualityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
