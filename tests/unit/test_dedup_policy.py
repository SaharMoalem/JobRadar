from datetime import datetime, timezone

from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.domain.dedup_policy import (
    compute_identity_key,
    derive_canonical_id,
    normalize_job_url,
)
from src.domain.job_posting import JobPosting, JobPostingCompleteness


def _posting(
    *,
    posting_id: str = "provisional",
    url: str,
    career_source_id: str = "src-1",
    external_id: str = "ext-1",
) -> JobPosting:
    return JobPosting(
        id=posting_id,
        title="Engineer",
        company="Acme",
        location="Remote",
        url=url,
        posted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        career_source_id=career_source_id,
        external_id=external_id,
        plugin_id="generic",
        completeness=JobPostingCompleteness.COMPLETE,
    )


def test_normalize_job_url_strips_tracking_params_and_trailing_slash():
    raw = "HTTPS://Example.com/jobs/1/?utm_source=newsletter&b=2&a=1"
    assert normalize_job_url(raw) == "https://example.com/jobs/1?a=1&b=2"


def test_identity_key_and_canonical_id_are_deterministic():
    key_a = compute_identity_key(url="https://example.com/jobs/1")
    key_b = compute_identity_key(url="https://example.com/jobs/1/")
    assert key_a == key_b

    id_a = derive_canonical_id(key_a)
    id_b = derive_canonical_id(key_a)
    assert id_a == id_b
    assert id_a.startswith("job-")


def test_save_posting_assigns_canonical_identity():
    repository = InMemoryJobPostingAdapter()
    posting = _posting(url="https://example.com/jobs/1")

    saved = repository.save_posting(posting)

    expected_key = compute_identity_key(url=posting.url)
    assert saved.identity_key == expected_key
    assert saved.id == derive_canonical_id(expected_key)
    assert repository.list_complete() == [saved]


def test_duplicate_url_from_different_source_is_suppressed():
    repository = InMemoryJobPostingAdapter()
    first = repository.save_posting(
        _posting(url="https://example.com/jobs/1", career_source_id="src-1", external_id="ext-1")
    )
    second = repository.save_posting(
        _posting(url="https://example.com/jobs/1", career_source_id="src-2", external_id="ext-2")
    )

    assert second.id == first.id
    assert len(repository.list_complete()) == 1
    links = repository.list_duplicate_links()
    assert len(links) == 1
    assert links[0].canonical_id == first.id
    assert links[0].career_source_id == "src-2"


def test_same_source_external_id_updates_canonical_in_place():
    repository = InMemoryJobPostingAdapter()
    first = repository.save_posting(
        _posting(url="https://example.com/jobs/1", career_source_id="src-1", external_id="ext-1")
    )
    updated = JobPosting(
        id="provisional-2",
        title="Senior Engineer",
        company="Acme",
        location="Remote",
        url="https://example.com/jobs/1",
        posted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id="ext-1",
        plugin_id="generic",
        completeness=JobPostingCompleteness.COMPLETE,
    )
    saved = repository.save_posting(updated)

    assert saved.id == first.id
    assert saved.title == "Senior Engineer"
    assert repository.list_duplicate_links() == []
    assert len(repository.list_complete()) == 1


def test_repeat_save_produces_identical_canonical_id():
    repository = InMemoryJobPostingAdapter()
    posting = _posting(url="https://example.com/jobs/repeat")

    first = repository.save_posting(posting)
    second = repository.save_posting(posting)

    assert first.id == second.id
    assert first.identity_key == second.identity_key


def test_url_change_same_source_external_keeps_single_canonical():
    repository = InMemoryJobPostingAdapter()
    first = repository.save_posting(
        _posting(url="https://example.com/jobs/old", career_source_id="src-1", external_id="ext-1")
    )
    updated = repository.save_posting(
        _posting(url="https://example.com/jobs/new", career_source_id="src-1", external_id="ext-1")
    )

    assert updated.id == first.id
    assert updated.url == "https://example.com/jobs/new"
    assert updated.identity_key == compute_identity_key(url="https://example.com/jobs/new")
    assert len(repository.list_complete()) == 1
    assert compute_identity_key(url="https://example.com/jobs/old") not in {
        posting.identity_key for posting in repository.list_complete()
    }


def test_repeat_duplicate_crawl_does_not_accumulate_links():
    repository = InMemoryJobPostingAdapter()
    repository.save_posting(
        _posting(url="https://example.com/jobs/1", career_source_id="src-1", external_id="ext-1")
    )
    duplicate = _posting(url="https://example.com/jobs/1", career_source_id="src-2", external_id="ext-2")

    repository.save_posting(duplicate)
    repository.save_posting(duplicate)
    repository.save_posting(duplicate)

    assert len(repository.list_duplicate_links()) == 1
