from __future__ import annotations

from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult, RawCrawlRecord


class GenericStubCrawlerPlugin:
    plugin_id = "generic"

    def crawl(self, source: CareerSource, *, correlation_id: str) -> CrawlPluginResult:
        record = RawCrawlRecord(
            external_id=f"{source.id}-sample-1",
            title=f"Sample role from {source.name}",
            url=source.base_url,
            raw_payload={
                "source_name": source.name,
                "company": source.name,
                "location": "Tel Aviv, Israel",
                "posted_at": "2026-07-01T08:00:00+00:00",
                "correlation_id": correlation_id,
                "plugin_id": self.plugin_id,
            },
        )
        return CrawlPluginResult(plugin_id=self.plugin_id, records=[record])
