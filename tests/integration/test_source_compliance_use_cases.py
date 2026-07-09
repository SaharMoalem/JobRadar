import pytest

from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.career_source import CareerSourceStatus, ComplianceStatus
from src.domain.source_policy import SourcePolicyConfig, SourceValidationError
from src.ports.compliance_check_port import ComplianceCheckResult
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


@pytest.fixture
def services():
    repository = InMemoryCareerSourceAdapter()
    source_service = CareerSourceService(
        repository=repository,
        config=SourcePolicyConfig(max_enabled_sources=50),
    )
    compliance_service = SourceComplianceService(
        repository=repository,
        compliance_checker=FakeComplianceCheckAdapter(),
    )
    return source_service, compliance_service


def test_approve_persists_compliance_metadata(services):
    source_service, compliance_service = services
    source = source_service.create("Company", "https://jobs.example.com")

    approved = compliance_service.approve(source.id)

    assert approved.compliance_status == ComplianceStatus.APPROVED
    assert approved.robots_check_passed is True
    assert approved.compliance_reason == "fake_check_passed"
    assert approved.compliance_reviewed_at is not None


def test_approve_failure_marks_source_rejected(services):
    source_service, compliance_service = services
    source = source_service.create("Company", "https://blocked.example.com")
    compliance_service.compliance_checker = FakeComplianceCheckAdapter(
        results={
            "https://blocked.example.com": ComplianceCheckResult(
                passed=False,
                reason="robots_txt_disallows_all",
                robots_txt_available=True,
            )
        }
    )

    with pytest.raises(SourceValidationError) as exc:
        compliance_service.approve(source.id)
    assert exc.value.code == "SOURCE_COMPLIANCE_CHECK_FAILED"

    stored = source_service.repository.get(source.id)
    assert stored is not None
    assert stored.compliance_status == ComplianceStatus.REJECTED


def test_execution_blocked_until_enabled_and_approved(services):
    source_service, compliance_service = services
    source = source_service.create("Company", "https://jobs.example.com")

    with pytest.raises(SourceValidationError) as exc:
        compliance_service.attempt_execution(source.id, correlation_id="corr-1")
    assert exc.value.code == "SOURCE_COMPLIANCE_NOT_APPROVED"

    compliance_service.approve(source.id)
    with pytest.raises(SourceValidationError) as exc:
        compliance_service.attempt_execution(source.id, correlation_id="corr-2")
    assert exc.value.code == "SOURCE_NOT_ENABLED"

    source_service.enable(source.id)
    runnable = compliance_service.attempt_execution(source.id, correlation_id="corr-3")
    assert runnable.status == CareerSourceStatus.ENABLED
