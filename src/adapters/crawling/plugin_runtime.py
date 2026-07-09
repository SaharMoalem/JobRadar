from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult, SourceCrawlOutcome, SourceCrawlStatus
from src.ports.crawler_plugin_port import CrawlerPluginPort


logger = logging.getLogger("jobradar.discovery")


@dataclass(slots=True)
class CrawlerPluginRuntime:
    def execute(
        self,
        plugin: CrawlerPluginPort,
        source: CareerSource,
        *,
        correlation_id: str,
    ) -> SourceCrawlOutcome:
        started = time.perf_counter()
        try:
            result = plugin.crawl(source, correlation_id=correlation_id)
            duration_ms = int((time.perf_counter() - started) * 1000)
            outcome = self._outcome_from_result(
                plugin=plugin,
                source=source,
                result=result,
                duration_ms=duration_ms,
            )
            self._log_finished(outcome=outcome, correlation_id=correlation_id)
            return outcome
        except Exception as exc:  # noqa: BLE001 - plugin boundary captures all plugin failures
            duration_ms = int((time.perf_counter() - started) * 1000)
            outcome = SourceCrawlOutcome(
                source_id=source.id,
                plugin_id=plugin.plugin_id,
                status=SourceCrawlStatus.FAILED,
                error_code="CRAWLER_PLUGIN_FAILED",
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            self._log_finished(outcome=outcome, correlation_id=correlation_id)
            return outcome

    def _outcome_from_result(
        self,
        *,
        plugin: CrawlerPluginPort,
        source: CareerSource,
        result: CrawlPluginResult,
        duration_ms: int,
    ) -> SourceCrawlOutcome:
        if not result.records:
            return SourceCrawlOutcome(
                source_id=source.id,
                plugin_id=plugin.plugin_id,
                status=SourceCrawlStatus.FAILED,
                error_code="CRAWLER_EMPTY_RESULT",
                error_message="Crawler plugin returned zero records.",
                duration_ms=duration_ms,
            )
        return SourceCrawlOutcome(
            source_id=source.id,
            plugin_id=plugin.plugin_id,
            status=SourceCrawlStatus.SUCCEEDED,
            records=result.records,
            duration_ms=duration_ms,
        )

    def _log_finished(self, *, outcome: SourceCrawlOutcome, correlation_id: str) -> None:
        logger.info(
            json.dumps(
                {
                    "event": "source_crawl_finished",
                    "source_id": outcome.source_id,
                    "plugin_id": outcome.plugin_id,
                    "status": outcome.status.value,
                    "record_count": len(outcome.records),
                    "error_code": outcome.error_code,
                    "duration_ms": outcome.duration_ms,
                    "correlation_id": correlation_id,
                }
            )
        )
