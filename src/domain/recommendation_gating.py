from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RecommendationGateConfig:
    config_version: str = "v1"
    global_threshold: int = 80
    skill_overlap_min_pct: int = 70
    recency_window_days: int = 14
    enforce_seniority: bool = True
    enforce_skill_overlap: bool = True
    enforce_language: bool = True
    enforce_region: bool = True
    enforce_recency: bool = True
    enforce_active_link: bool = True


@dataclass(frozen=True, slots=True)
class GateTraceEntry:
    gate: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class GatedRecommendation:
    job_posting_id: str
    match_score: int
    profile_version: str
    config_version: str
    actionable: bool
    gate_trace: tuple[GateTraceEntry, ...]
    evaluated_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class GatingBatchResult:
    recommendations: tuple[GatedRecommendation, ...]
    actionable_count: int
    non_actionable_count: int
    skipped_count: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class GatingFailure:
    code: str
    message: str
    correlation_id: str


class GatingValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
