from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.domain.job_posting import JobPosting
from src.domain.normalization import NormalizationRejection


class SourceCrawlStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RawCrawlRecord:
    external_id: str
    title: str
    url: str
    raw_payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CrawlPluginResult:
    plugin_id: str
    records: list[RawCrawlRecord]


@dataclass(frozen=True, slots=True)
class SourceCrawlOutcome:
    source_id: str
    plugin_id: str
    status: SourceCrawlStatus
    records: list[RawCrawlRecord] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int = 0
    job_postings: tuple[JobPosting, ...] = ()
    normalization_rejections: tuple[NormalizationRejection, ...] = ()


@dataclass(frozen=True, slots=True)
class CrawlRunResult:
    correlation_id: str
    outcomes: list[SourceCrawlOutcome]
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: datetime | None = None

    @property
    def succeeded_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == SourceCrawlStatus.SUCCEEDED)

    @property
    def failed_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == SourceCrawlStatus.FAILED)
