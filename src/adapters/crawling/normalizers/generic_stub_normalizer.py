from __future__ import annotations

from datetime import datetime, timezone

from src.domain.career_source import CareerSource
from src.domain.crawl import RawCrawlRecord
from src.domain.job_posting import JobPosting
from src.domain.normalization_policy import apply_completeness


def _parse_posted_at(raw_payload: dict[str, object]) -> datetime | None:
    value = raw_payload.get("posted_at")
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class GenericStubCrawlNormalizer:
    plugin_id = "generic"

    def to_job_posting(self, record: RawCrawlRecord, *, source: CareerSource) -> JobPosting:
        raw = record.raw_payload
        posting = JobPosting(
            id=f"{source.id}:{record.external_id}",
            title=record.title.strip(),
            company=str(raw.get("company") or source.name).strip(),
            location=str(raw.get("location") or "").strip(),
            url=record.url.strip(),
            posted_at=_parse_posted_at(raw),
            career_source_id=source.id,
            external_id=record.external_id,
            plugin_id=source.plugin_id,
            source_metadata={
                "career_source_name": source.name,
                "plugin_id": source.plugin_id,
                "raw_external_id": record.external_id,
            },
        )
        return apply_completeness(posting)
