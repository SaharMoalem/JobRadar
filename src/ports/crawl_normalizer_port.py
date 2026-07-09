from __future__ import annotations

from typing import Protocol

from src.domain.career_source import CareerSource
from src.domain.crawl import RawCrawlRecord
from src.domain.job_posting import JobPosting


class CrawlNormalizerPort(Protocol):
    plugin_id: str

    def to_job_posting(self, record: RawCrawlRecord, *, source: CareerSource) -> JobPosting: ...
