
from src.adapters.crawling.normalizers.generic_stub_normalizer import GenericStubCrawlNormalizer
from src.domain.career_source import CareerSource
from src.domain.crawl import RawCrawlRecord
from src.domain.job_posting import JobPostingCompleteness
from src.domain.normalization_policy import apply_completeness, find_missing_required_fields


def test_find_missing_required_fields_detects_gaps():
    missing = find_missing_required_fields(
        title="Engineer",
        company="",
        location="Tel Aviv",
        url="https://jobs.example.com/1",
        posted_at=None,
    )
    assert missing == ["company", "posted_at"]


def test_apply_completeness_marks_incomplete_posting():
    from src.domain.job_posting import JobPosting

    posting = JobPosting(
        id="p1",
        title="Engineer",
        company="Acme",
        location="",
        url="https://jobs.example.com/1",
        posted_at=None,
        career_source_id="s1",
        external_id="ext-1",
        plugin_id="generic",
    )
    result = apply_completeness(posting)
    assert result.completeness == JobPostingCompleteness.INCOMPLETE
    assert "location" in result.rejection_reason


def test_generic_normalizer_maps_required_fields():
    normalizer = GenericStubCrawlNormalizer()
    source = CareerSource(id="src-1", name="Acme", base_url="https://acme.example.com/jobs")
    record = RawCrawlRecord(
        external_id="ext-1",
        title="Backend Engineer",
        url="https://acme.example.com/jobs/1",
        raw_payload={
            "company": "Acme",
            "location": "Tel Aviv, Israel",
            "posted_at": "2026-07-01T08:00:00+00:00",
        },
    )

    posting = normalizer.to_job_posting(record, source=source)

    assert posting.completeness == JobPostingCompleteness.COMPLETE
    assert posting.title == "Backend Engineer"
    assert posting.company == "Acme"
    assert posting.location == "Tel Aviv, Israel"
    assert posting.id == "src-1:ext-1"
