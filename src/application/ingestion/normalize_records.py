from __future__ import annotations

from dataclasses import dataclass

from src.domain.career_source import CareerSource
from src.domain.crawl import RawCrawlRecord
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.normalization import NormalizationBatchResult, NormalizationRejection
from src.domain.normalization_policy import find_missing_required_fields
from src.ports.crawl_normalizer_port import CrawlNormalizerPort
from src.ports.job_posting_port import JobPostingRepositoryPort


@dataclass(slots=True)
class NormalizeCrawlRecordsUseCase:
    job_posting_repository: JobPostingRepositoryPort

    def normalize(
        self,
        records: list[RawCrawlRecord],
        *,
        source: CareerSource,
        normalizer: CrawlNormalizerPort,
    ) -> NormalizationBatchResult:
        accepted: list[JobPosting] = []
        rejected: list[NormalizationRejection] = []

        for record in records:
            try:
                posting = normalizer.to_job_posting(record, source=source)
            except Exception as exc:  # noqa: BLE001 - isolate per-record normalizer failures
                rejection = self._build_rejection(
                    record=record,
                    source=source,
                    reason=f"normalizer_failed:{type(exc).__name__}",
                    missing_fields=(),
                )
                self.job_posting_repository.save_rejection(rejection)
                rejected.append(rejection)
                continue

            missing = find_missing_required_fields(
                title=posting.title,
                company=posting.company,
                location=posting.location,
                url=posting.url,
                posted_at=posting.posted_at,
            )
            if not missing:
                posting.completeness = JobPostingCompleteness.COMPLETE
                posting.rejection_reason = None
                saved = self.job_posting_repository.save_posting(posting)
                accepted.append(saved)
                continue

            rejection = self._build_rejection(
                record=record,
                source=source,
                reason=posting.rejection_reason or "missing_required_fields",
                missing_fields=tuple(missing),
            )
            self.job_posting_repository.save_rejection(rejection)
            rejected.append(rejection)

        return NormalizationBatchResult(accepted=accepted, rejected=rejected)

    def reject_all(
        self,
        records: list[RawCrawlRecord],
        *,
        source: CareerSource,
        reason: str,
    ) -> NormalizationBatchResult:
        rejected: list[NormalizationRejection] = []
        for record in records:
            rejection = self._build_rejection(
                record=record,
                source=source,
                reason=reason,
                missing_fields=(),
            )
            self.job_posting_repository.save_rejection(rejection)
            rejected.append(rejection)
        return NormalizationBatchResult(accepted=[], rejected=rejected)

    def _build_rejection(
        self,
        *,
        record: RawCrawlRecord,
        source: CareerSource,
        reason: str,
        missing_fields: tuple[str, ...],
    ) -> NormalizationRejection:
        return NormalizationRejection(
            external_id=record.external_id,
            career_source_id=source.id,
            plugin_id=source.plugin_id,
            reason=reason,
            missing_fields=missing_fields,
            raw_payload=dict(record.raw_payload),
        )
