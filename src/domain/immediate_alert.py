from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ImmediateAlertConfig:
    config_version: str = "v1"
    alert_threshold: int = 90


@dataclass(frozen=True, slots=True)
class ImmediateAlert:
    id: str
    job_posting_id: str
    role_summary: str
    match_score: int
    deep_link: str
    run_context: str
    correlation_id: str
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class ImmediateAlertBatchResult:
    alerts: tuple[ImmediateAlert, ...]
    triggered_count: int
    skipped_below_threshold_count: int
    skipped_duplicate_count: int
    skipped_missing_posting_count: int
    correlation_id: str
    run_context: str


@dataclass(frozen=True, slots=True)
class ImmediateAlertFailure:
    code: str
    message: str
    correlation_id: str


class ImmediateAlertValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
