from __future__ import annotations

from dataclasses import dataclass, replace

from src.adapters.crawling.normalizer_registry import InMemoryCrawlNormalizerRegistry
from src.application.ingestion.normalize_records import NormalizeCrawlRecordsUseCase
from src.domain.crawl import SourceCrawlOutcome, SourceCrawlStatus
from src.ports.career_source_port import CareerSourceRepositoryPort


@dataclass(slots=True)
class CrawlNormalizationService:
    repository: CareerSourceRepositoryPort
    normalizer_registry: InMemoryCrawlNormalizerRegistry
    normalize_use_case: NormalizeCrawlRecordsUseCase

    def enrich_outcome(self, outcome: SourceCrawlOutcome, *, correlation_id: str) -> SourceCrawlOutcome:
        if outcome.status != SourceCrawlStatus.SUCCEEDED:
            return outcome
        if not outcome.records:
            return outcome

        source = self.repository.get(outcome.source_id)
        if source is None:
            return outcome

        try:
            normalizer = self.normalizer_registry.resolve(source)
        except KeyError:
            batch = self.normalize_use_case.reject_all(
                list(outcome.records),
                source=source,
                reason="CRAWLER_NORMALIZER_NOT_FOUND",
                correlation_id=correlation_id,
            )
            return replace(
                outcome,
                job_postings=tuple(batch.accepted),
                normalization_rejections=tuple(batch.rejected),
            )

        batch = self.normalize_use_case.normalize(
            list(outcome.records),
            source=source,
            normalizer=normalizer,
            correlation_id=correlation_id,
        )
        return replace(
            outcome,
            job_postings=tuple(batch.accepted),
            normalization_rejections=tuple(batch.rejected),
        )
