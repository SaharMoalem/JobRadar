import json
import logging

from src.application.discovery.execution_gate import gate_source_execution
from src.domain.career_source import CareerSource, CareerSourceStatus, ComplianceStatus
from src.domain.source_policy import SourceValidationError
import pytest


def test_gate_source_execution_logs_compliance_block(caplog):
    source = CareerSource(
        id="pending-1",
        name="Pending",
        base_url="https://pending.example.com",
        status=CareerSourceStatus.ENABLED,
        compliance_status=ComplianceStatus.PENDING,
    )

    with caplog.at_level(logging.INFO, logger="jobradar.discovery"):
        with pytest.raises(SourceValidationError) as exc:
            gate_source_execution(source, correlation_id="corr-456")

    assert exc.value.code == "SOURCE_COMPLIANCE_NOT_APPROVED"
    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "source_execution_blocked"
    assert payload["reason"] == "SOURCE_COMPLIANCE_NOT_APPROVED"
    assert payload["source_id"] == "pending-1"
    assert payload["correlation_id"] == "corr-456"
