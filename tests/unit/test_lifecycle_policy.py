from datetime import datetime, timedelta, timezone

from src.adapters.observability.structured_lifecycle_telemetry_adapter import (
    StructuredLifecycleTelemetryAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.lifecycle_policy import RETENTION_DAYS, should_archive


def _posting(**overrides) -> JobPosting:
    defaults = {
        "id": "provisional",
        "title": "Engineer",
        "company": "Acme",
        "location": "Remote",
        "url": "https://example.com/jobs/1",
        "posted_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "career_source_id": "src-1",
        "external_id": "ext-1",
        "plugin_id": "generic",
        "completeness": JobPostingCompleteness.COMPLETE,
        "source_metadata": {"correlation_id": "corr-1"},
    }
    defaults.update(overrides)
    return JobPosting(**defaults)


def test_should_archive_after_retention_window():
    expired_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    before = expired_at + timedelta(days=RETENTION_DAYS - 1)
    after = expired_at + timedelta(days=RETENTION_DAYS)
    assert should_archive(expired_at, before) is False
    assert should_archive(expired_at, after) is True


def test_new_posting_starts_in_new_state():
    repository = InMemoryJobPostingAdapter()
    saved = repository.save_posting(_posting())

    assert saved.lifecycle_state == JobLifecycleState.NEW
    transitions = repository.list_lifecycle_transitions(saved.id)
    assert len(transitions) == 1
    assert transitions[0].to_state == JobLifecycleState.NEW
    assert transitions[0].correlation_id == "corr-1"


def test_material_change_transitions_to_updated():
    repository = InMemoryJobPostingAdapter()
    repository.save_posting(_posting())
    updated = repository.save_posting(
        _posting(title="Senior Engineer", source_metadata={"correlation_id": "corr-2"})
    )

    assert updated.lifecycle_state == JobLifecycleState.UPDATED
    assert any(t.to_state == JobLifecycleState.UPDATED for t in repository.list_lifecycle_transitions())


def test_reobservation_without_change_becomes_active():
    repository = InMemoryJobPostingAdapter()
    repository.save_posting(_posting())
    second = repository.save_posting(_posting(source_metadata={"correlation_id": "corr-2"}))

    assert second.lifecycle_state == JobLifecycleState.ACTIVE


def test_unseen_postings_expire_after_source_crawl():
    repository = InMemoryJobPostingAdapter()
    saved = repository.save_posting(_posting())

    transitions = repository.expire_unseen_for_source("src-1", set(), correlation_id="expire-1")

    assert len(transitions) == 1
    assert transitions[0].to_state == JobLifecycleState.EXPIRED
    expired = repository.list_complete()[0]
    assert expired.lifecycle_state == JobLifecycleState.EXPIRED
    assert expired.id == saved.id


def test_transition_timestamps_are_recorded_per_event():
    repository = InMemoryJobPostingAdapter()
    repository.save_posting(_posting())
    repository.save_posting(_posting(source_metadata={"correlation_id": "corr-2"}))

    transitions = repository.list_lifecycle_transitions()
    assert len(transitions) >= 2
    assert transitions[0].transitioned_at <= transitions[-1].transitioned_at


def test_retention_archives_expired_postings():
    from src.application.ingestion.track_lifecycle import JobLifecycleService

    telemetry = StructuredLifecycleTelemetryAdapter()
    repository = InMemoryJobPostingAdapter(telemetry=telemetry)
    service = JobLifecycleService(repository=repository, telemetry=telemetry)
    repository.save_posting(_posting())
    repository.expire_unseen_for_source("src-1", set(), correlation_id="expire-1")
    posting = repository.list_complete()[0]
    assert posting.expired_at is not None

    result = service.apply_retention(
        correlation_id="retain-1",
        evaluated_at=posting.expired_at + timedelta(days=RETENTION_DAYS),
    )

    assert result.archived_count == 1
    assert repository.list_complete() == []
    assert telemetry.snapshot_metrics()["retention_archived_total"] == 1
