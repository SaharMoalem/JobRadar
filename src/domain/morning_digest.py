from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class MorningDigestConfig:
    config_version: str = "v1"
    digest_threshold: int = 80
    digest_window_hours: int = 24
    top_n: int = 5


@dataclass(frozen=True, slots=True)
class DigestJobItem:
    job_posting_id: str
    role_summary: str
    match_score: int
    deep_link: str
    lifecycle_state: str
    transitioned_at: datetime | None = None
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class MorningDigest:
    id: str
    run_context: str
    correlation_id: str
    digest_date: str
    new_items: tuple[DigestJobItem, ...]
    updated_items: tuple[DigestJobItem, ...]
    expired_items: tuple[DigestJobItem, ...]
    top_recommendations: tuple[DigestJobItem, ...]
    is_noop: bool
    skipped_below_threshold_count: int
    skipped_missing_score_count: int
    skipped_missing_posting_count: int
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class MorningDigestResult:
    digest: MorningDigest
    correlation_id: str
    run_context: str


@dataclass(frozen=True, slots=True)
class MorningDigestFailure:
    code: str
    message: str
    correlation_id: str


class MorningDigestValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
