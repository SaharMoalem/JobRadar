import json
import logging

from src.application.discovery.filter_sources import filter_runnable_sources
from src.domain.career_source import CareerSource, CareerSourceStatus, ComplianceStatus


def test_filter_runnable_sources_logs_disabled_and_compliance_skips(caplog):
    runnable = CareerSource(
        id="run-1",
        name="Runnable",
        base_url="https://run.example.com",
        status=CareerSourceStatus.ENABLED,
        compliance_status=ComplianceStatus.APPROVED,
    )
    disabled = CareerSource(
        id="disabled-1",
        name="Disabled",
        base_url="https://disabled.example.com",
        status=CareerSourceStatus.DISABLED,
        compliance_status=ComplianceStatus.APPROVED,
    )
    pending = CareerSource(
        id="pending-1",
        name="Pending",
        base_url="https://pending.example.com",
        status=CareerSourceStatus.ENABLED,
        compliance_status=ComplianceStatus.PENDING,
    )

    with caplog.at_level(logging.INFO, logger="jobradar.discovery"):
        result = filter_runnable_sources([runnable, disabled, pending], correlation_id="corr-123")

    assert result == [runnable]
    payloads = [json.loads(record.message) for record in caplog.records]
    assert payloads[0]["reason"] == "source_disabled"
    assert payloads[1]["reason"] == "compliance_not_approved"
