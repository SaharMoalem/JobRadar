from src.adapters.crawling.normalizer_registry import InMemoryCrawlNormalizerRegistry
from src.adapters.crawling.normalizers.generic_stub_normalizer import GenericStubCrawlNormalizer
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.application.ingestion.enrich_crawl_outcome import CrawlNormalizationService
from src.application.ingestion.normalize_records import NormalizeCrawlRecordsUseCase
from src.domain.career_source import CareerSource
from src.domain.crawl import RawCrawlRecord, SourceCrawlOutcome, SourceCrawlStatus
from src.domain.job_posting import JobPosting, JobPostingCompleteness


def test_enrich_outcome_rejects_when_normalizer_missing():
    repository = InMemoryCareerSourceAdapter()
    source = CareerSource(id="src-1", name="Acme", base_url="https://acme.example.com", plugin_id="orphan")
    repository.create(source)
    postings = InMemoryJobPostingAdapter()
    service = CrawlNormalizationService(
        repository=repository,
        normalizer_registry=InMemoryCrawlNormalizerRegistry({"generic": GenericStubCrawlNormalizer()}),
        normalize_use_case=NormalizeCrawlRecordsUseCase(job_posting_repository=postings),
    )
    outcome = SourceCrawlOutcome(
        source_id=source.id,
        plugin_id=source.plugin_id,
        status=SourceCrawlStatus.SUCCEEDED,
        records=[
            RawCrawlRecord(
                external_id="ext-1",
                title="Role",
                url="https://acme.example.com/jobs/1",
                raw_payload={},
            )
        ],
    )

    enriched = service.enrich_outcome(outcome, correlation_id="norm-missing-1")

    assert enriched.status == SourceCrawlStatus.SUCCEEDED
    assert enriched.job_postings == ()
    assert len(enriched.normalization_rejections) == 1
    assert enriched.normalization_rejections[0].reason == "CRAWLER_NORMALIZER_NOT_FOUND"
    assert len(postings.list_rejections()) == 1


def test_normalize_revalidates_even_when_normalizer_marks_complete():
    class LyingNormalizer:
        plugin_id = "lying"

        def to_job_posting(self, record: RawCrawlRecord, *, source: CareerSource) -> JobPosting:
            posting = JobPosting(
                id="bad",
                title="",
                company="Acme",
                location="Tel Aviv",
                url="https://example.com",
                posted_at=None,
                career_source_id=source.id,
                external_id=record.external_id,
                plugin_id=source.plugin_id,
            )
            posting.completeness = JobPostingCompleteness.COMPLETE
            return posting

    postings = InMemoryJobPostingAdapter()
    use_case = NormalizeCrawlRecordsUseCase(job_posting_repository=postings)
    source = CareerSource(id="s1", name="Acme", base_url="https://acme.example.com")
    record = RawCrawlRecord(
        external_id="ext-1",
        title="",
        url="https://example.com",
        raw_payload={},
    )

    batch = use_case.normalize([record], source=source, normalizer=LyingNormalizer(), correlation_id="corr-lying")

    assert batch.accepted == []
    assert len(batch.rejected) == 1
    assert "title" in batch.rejected[0].missing_fields


def test_normalize_isolates_per_record_failures():
    class FlakyNormalizer:
        plugin_id = "flaky"

        def to_job_posting(self, record: RawCrawlRecord, *, source: CareerSource) -> JobPosting:
            if record.external_id == "bad":
                raise ValueError("boom")
            from datetime import datetime, timezone

            return JobPosting(
                id=f"{source.id}:{record.external_id}",
                title=record.title,
                company="Acme",
                location="Tel Aviv",
                url=record.url,
                posted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                career_source_id=source.id,
                external_id=record.external_id,
                plugin_id=source.plugin_id,
                completeness=JobPostingCompleteness.COMPLETE,
            )

    postings = InMemoryJobPostingAdapter()
    use_case = NormalizeCrawlRecordsUseCase(job_posting_repository=postings)
    source = CareerSource(id="s1", name="Acme", base_url="https://acme.example.com")
    records = [
        RawCrawlRecord(
            external_id="good",
            title="Good",
            url="https://example.com/good",
            raw_payload={},
        ),
        RawCrawlRecord(external_id="bad", title="Bad", url="https://example.com/bad", raw_payload={}),
    ]

    batch = use_case.normalize(records, source=source, normalizer=FlakyNormalizer(), correlation_id="corr-flaky")

    assert len(batch.accepted) == 1
    assert len(batch.rejected) == 1
    assert batch.rejected[0].reason.startswith("normalizer_failed:")
