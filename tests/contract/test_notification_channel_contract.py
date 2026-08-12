from datetime import datetime, timezone

import pytest

from src.adapters.notification import InAppNotificationAdapter, RecordingEmailNotificationAdapter
from src.domain.immediate_alert import ImmediateAlert
from src.domain.morning_digest import MorningDigest
from src.domain.notification import NotificationPayload
from src.ports.notification_channel_port import NotificationChannelAdapter


@pytest.fixture(params=[InAppNotificationAdapter, RecordingEmailNotificationAdapter])
def adapter(request) -> NotificationChannelAdapter:
    return request.param()


def _alert_payload() -> NotificationPayload:
    return NotificationPayload(
        kind="immediate_alert",
        correlation_id="contract-1",
        run_context="run-1",
        alert=ImmediateAlert(
            id="alert-contract",
            job_posting_id="job-1",
            role_summary="Role at Acme (Tel Aviv)",
            match_score=90,
            deep_link="/job-postings/job-1",
            run_context="run-1",
            correlation_id="contract-1",
            created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        ),
    )


def _digest_payload() -> NotificationPayload:
    return NotificationPayload(
        kind="morning_digest",
        correlation_id="contract-2",
        run_context="2026-08-11",
        digest=MorningDigest(
            id="digest-contract",
            run_context="2026-08-11",
            correlation_id="contract-2",
            digest_date="2026-08-11",
            new_items=(),
            updated_items=(),
            expired_items=(),
            top_recommendations=(),
            is_noop=True,
            skipped_below_threshold_count=0,
            skipped_missing_score_count=0,
            skipped_missing_posting_count=0,
        ),
    )


@pytest.mark.parametrize("payload_factory", [_alert_payload, _digest_payload])
def test_notification_channel_contract(adapter: NotificationChannelAdapter, payload_factory):
    payload = payload_factory()
    assert isinstance(adapter.channel_id, str) and adapter.channel_id
    delivery = adapter.deliver(payload)
    assert delivery.channel_id == adapter.channel_id
    assert delivery.kind == payload.kind
    assert delivery.source_id == payload.source_id
    assert delivery.correlation_id == payload.correlation_id
    assert delivery.run_context == payload.run_context
    assert isinstance(delivery.status, str) and delivery.status
    assert isinstance(delivery.detail, str) and delivery.detail
    assert delivery.id
