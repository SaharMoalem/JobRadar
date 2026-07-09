from src.adapters.crawling.normalizers.generic_stub_normalizer import GenericStubCrawlNormalizer
from src.domain.career_source import CareerSource
from src.domain.crawl import RawCrawlRecord
from src.domain.job_posting import JobPostingCompleteness


def test_generic_normalizer_contract_shape():
    normalizer = GenericStubCrawlNormalizer()
    source = CareerSource(id="src-1", name="Acme", base_url="https://acme.example.com")
    record = RawCrawlRecord(
        external_id="ext-1",
        title="Role",
        url="https://acme.example.com/jobs/1",
        raw_payload={
            "company": "Acme",
            "location": "Remote",
            "posted_at": "2026-07-01T08:00:00+00:00",
        },
    )

    first = normalizer.to_job_posting(record, source=source)
    second = normalizer.to_job_posting(record, source=source)

    assert first.completeness == JobPostingCompleteness.COMPLETE
    assert first.title == second.title
    assert first.company == second.company
    assert first.location == second.location
    assert first.url == second.url
    assert first.id == second.id
