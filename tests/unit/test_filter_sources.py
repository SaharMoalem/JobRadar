import json
import logging

from src.application.discovery.filter_sources import filter_enabled_sources
from src.domain.career_source import CareerSource, CareerSourceStatus


def test_filter_enabled_sources_logs_disabled_skip(caplog):
    enabled = CareerSource(
        id="enabled-1",
        name="Enabled",
        base_url="https://enabled.example.com",
        status=CareerSourceStatus.ENABLED,
    )
    disabled = CareerSource(
        id="disabled-1",
        name="Disabled",
        base_url="https://disabled.example.com",
        status=CareerSourceStatus.DISABLED,
    )

    with caplog.at_level(logging.INFO, logger="jobradar.discovery"):
        result = filter_enabled_sources([enabled, disabled], correlation_id="corr-123")

    assert result == [enabled]
    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload == {
        "event": "source_skipped",
        "reason": "source_disabled",
        "source_id": "disabled-1",
        "correlation_id": "corr-123",
    }
