import pytest

from src.domain.career_source import CareerSource, CareerSourceStatus, ComplianceStatus
from src.domain.compliance_policy import require_compliance_approved, require_runnable
from src.domain.source_policy import SourceValidationError


def test_require_compliance_approved_rejects_pending():
    source = CareerSource(
        id="s1",
        name="A",
        base_url="https://example.com",
        compliance_status=ComplianceStatus.PENDING,
    )
    with pytest.raises(SourceValidationError) as exc:
        require_compliance_approved(source)
    assert exc.value.code == "SOURCE_COMPLIANCE_NOT_APPROVED"


def test_require_runnable_requires_enabled_and_approved():
    source = CareerSource(
        id="s1",
        name="A",
        base_url="https://example.com",
        status=CareerSourceStatus.DISABLED,
        compliance_status=ComplianceStatus.APPROVED,
    )
    with pytest.raises(SourceValidationError) as exc:
        require_runnable(source)
    assert exc.value.code == "SOURCE_NOT_ENABLED"
