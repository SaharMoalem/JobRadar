from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.career_source import CareerSourceStatus, ComplianceStatus
from src.domain.source_policy import SourcePolicyConfig, SourceValidationError
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


def make_service(limit: int = 50) -> CareerSourceService:
    return CareerSourceService(
        repository=InMemoryCareerSourceAdapter(),
        config=SourcePolicyConfig(max_enabled_sources=limit),
    )


def make_compliance_service() -> SourceComplianceService:
    return SourceComplianceService(
        repository=InMemoryCareerSourceAdapter(),
        compliance_checker=FakeComplianceCheckAdapter(),
    )


def test_create_enable_disable_source():
    service = make_service()
    compliance = make_compliance_service()
    source = service.create("Company A", "https://jobs.example.com")
    assert source.status == CareerSourceStatus.DISABLED

    compliance.repository = service.repository
    compliance.approve(source.id)
    enabled = service.enable(source.id)
    assert enabled.status == CareerSourceStatus.ENABLED

    disabled = service.disable(source.id)
    assert disabled.status == CareerSourceStatus.DISABLED


def test_enable_requires_compliance_approval():
    service = make_service()
    source = service.create("Company A", "https://jobs.example.com")

    try:
        service.enable(source.id)
    except SourceValidationError as exc:
        assert exc.code == "SOURCE_COMPLIANCE_NOT_APPROVED"
    else:
        raise AssertionError("Expected compliance validation error")


def test_update_invalidates_compliance_when_base_url_changes():
    service = make_service()
    compliance = make_compliance_service()
    compliance.repository = service.repository
    source = service.create("Company", "https://jobs.example.com")
    compliance.approve(source.id)
    service.enable(source.id)

    updated = service.update(source.id, "Company", "https://other.example.com/jobs")

    assert updated.compliance_status == ComplianceStatus.PENDING
    assert updated.compliance_reason == "base_url_changed"
    assert updated.robots_check_passed is None
    assert updated.status == CareerSourceStatus.DISABLED

    try:
        service.enable(updated.id)
    except SourceValidationError as exc:
        assert exc.code == "SOURCE_COMPLIANCE_NOT_APPROVED"
    else:
        raise AssertionError("Expected compliance validation after URL change")


def test_enable_limit_validation():
    service = make_service(limit=1)
    compliance = make_compliance_service()
    compliance.repository = service.repository
    a = service.create("A", "https://a.example.com")
    b = service.create("B", "https://b.example.com")
    compliance.approve(a.id)
    compliance.approve(b.id)
    service.enable(a.id)

    try:
        service.enable(b.id)
    except SourceValidationError as exc:
        assert exc.code == "SOURCE_ENABLED_LIMIT_EXCEEDED"
    else:
        raise AssertionError("Expected limit validation error")
