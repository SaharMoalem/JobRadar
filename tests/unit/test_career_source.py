from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.domain.career_source import CareerSource, CareerSourceStatus
from src.domain.source_policy import SourcePolicyConfig


def test_default_timestamps_are_not_shared_between_instances():
    a = CareerSource(id="a", name="A", base_url="https://example.com")
    b = CareerSource(id="b", name="B", base_url="https://example.com")
    assert a.created_at is not b.created_at
    assert a.updated_at is not b.updated_at


def test_update_refreshes_updated_at():
    service = CareerSourceService(
        repository=InMemoryCareerSourceAdapter(),
        config=SourcePolicyConfig(max_enabled_sources=50),
    )
    source = service.create("Company", "https://jobs.example.com")
    original_updated = source.updated_at
    updated = service.update(source.id, "Company Renamed", "https://jobs.example.com/careers")
    assert updated.updated_at >= original_updated
    assert updated.name == "Company Renamed"


def test_set_status_refreshes_updated_at():
    source = CareerSource(id="s1", name="A", base_url="https://example.com")
    before = source.updated_at
    source.set_status(CareerSourceStatus.ENABLED)
    assert source.updated_at >= before
