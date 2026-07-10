from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.adapters.crawling.plugin_runtime import CrawlerPluginRuntime
from src.application.discovery.execution_gate import gate_source_execution
from src.application.discovery.filter_sources import filter_runnable_sources
from src.application.ingestion.enrich_crawl_outcome import CrawlNormalizationService
from src.application.ingestion.track_lifecycle import JobLifecycleService
from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlRunResult, SourceCrawlOutcome, SourceCrawlStatus
from src.domain.source_policy import SourceValidationError
from src.ports.career_source_port import CareerSourceRepositoryPort
from src.ports.crawler_plugin_port import CrawlerPluginRegistryPort


@dataclass(slots=True)
class DiscoverJobsUseCase:
    repository: CareerSourceRepositoryPort
    plugin_registry: CrawlerPluginRegistryPort
    runtime: CrawlerPluginRuntime = field(default_factory=CrawlerPluginRuntime)
    normalization_service: CrawlNormalizationService | None = None
    lifecycle_service: JobLifecycleService | None = None

    def run_all(self, *, correlation_id: str) -> CrawlRunResult:
        runnable = filter_runnable_sources(self.repository.list_all(), correlation_id)
        outcomes = [
            self._finalize_outcome(
                self._execute_source(source, correlation_id=correlation_id, enforce_gate=True),
                correlation_id=correlation_id,
            )
            for source in runnable
        ]
        if self.lifecycle_service is not None:
            self.lifecycle_service.apply_retention(correlation_id=correlation_id)
        return CrawlRunResult(
            correlation_id=correlation_id,
            outcomes=outcomes,
            completed_at=datetime.now(timezone.utc),
        )

    def run_source(self, source_id: str, *, correlation_id: str) -> SourceCrawlOutcome:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceValidationError("SOURCE_NOT_FOUND", "Career source not found.")
        gate_source_execution(source, correlation_id=correlation_id)
        outcome = self._finalize_outcome(
            self._execute_source(source, correlation_id=correlation_id, enforce_gate=False),
            correlation_id=correlation_id,
        )
        if self.lifecycle_service is not None:
            self.lifecycle_service.apply_retention(correlation_id=correlation_id)
        return outcome

    def _execute_source(
        self,
        source: CareerSource,
        *,
        correlation_id: str,
        enforce_gate: bool,
    ) -> SourceCrawlOutcome:
        if enforce_gate:
            try:
                gate_source_execution(source, correlation_id=correlation_id)
            except SourceValidationError as exc:
                return SourceCrawlOutcome(
                    source_id=source.id,
                    plugin_id=source.plugin_id,
                    status=SourceCrawlStatus.FAILED,
                    error_code=exc.code,
                    error_message=str(exc),
                )

        try:
            plugin = self.plugin_registry.resolve(source)
        except KeyError as exc:
            return SourceCrawlOutcome(
                source_id=source.id,
                plugin_id=source.plugin_id,
                status=SourceCrawlStatus.FAILED,
                error_code="CRAWLER_PLUGIN_NOT_FOUND",
                error_message=str(exc),
            )

        return self.runtime.execute(plugin, source, correlation_id=correlation_id)

    def _finalize_outcome(self, outcome: SourceCrawlOutcome, *, correlation_id: str) -> SourceCrawlOutcome:
        if self.normalization_service is not None:
            outcome = self.normalization_service.enrich_outcome(outcome, correlation_id=correlation_id)
        if self.lifecycle_service is not None and outcome.status == SourceCrawlStatus.SUCCEEDED:
            seen_posting_ids = {posting.id for posting in outcome.job_postings}
            self.lifecycle_service.finalize_source_crawl(
                outcome.source_id,
                seen_posting_ids,
                correlation_id=correlation_id,
            )
        return outcome
