from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.domain.career_source import CareerSourceStatus
from src.domain.source_policy import SourcePolicyConfig, SourceValidationError


def make_service(limit: int = 50) -> CareerSourceService:
    return CareerSourceService(
        repository=InMemoryCareerSourceAdapter(),
        config=SourcePolicyConfig(max_enabled_sources=limit),
    )


def test_create_enable_disable_source():
    service = make_service()
    source = service.create("Company A", "https://jobs.example.com")
    assert source.status == CareerSourceStatus.DISABLED

    enabled = service.enable(source.id)
    assert enabled.status == CareerSourceStatus.ENABLED

    disabled = service.disable(source.id)
    assert disabled.status == CareerSourceStatus.DISABLED


def test_enable_limit_validation():
    service = make_service(limit=1)
    a = service.create("A", "https://a.example.com")
    b = service.create("B", "https://b.example.com")
    service.enable(a.id)

    try:
        service.enable(b.id)
    except SourceValidationError as exc:
        assert exc.code == "SOURCE_ENABLED_LIMIT_EXCEEDED"
    else:
        raise AssertionError("Expected limit validation error")
