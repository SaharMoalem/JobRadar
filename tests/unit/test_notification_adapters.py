from datetime import datetime, timezone

from src.adapters.notification import (
    InAppNotificationAdapter,
    RecordingEmailNotificationAdapter,
)
from src.domain.immediate_alert import ImmediateAlert
from src.domain.morning_digest import MorningDigest
from src.domain.notification import NotificationPayload


def _alert_payload() -> NotificationPayload:
    alert = ImmediateAlert(
        id="alert-1",
        job_posting_id="job-1",
        role_summary="Backend at Acme (Tel Aviv)",
        match_score=92,
        deep_link="/job-postings/job-1",
        run_context="run-1",
        correlation_id="c1",
        created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    return NotificationPayload(
        kind="immediate_alert",
        correlation_id="c1",
        run_context="run-1",
        alert=alert,
    )


def test_in_app_adapter_delivers():
    adapter = InAppNotificationAdapter()
    delivery = adapter.deliver(_alert_payload())
    assert adapter.channel_id == "in_app"
    assert delivery.channel_id == "in_app"
    assert delivery.status == "delivered"
    assert delivery.source_id == "alert-1"
    assert "Backend at Acme" in delivery.detail
    assert len(adapter.inbox) == 1


def test_email_adapter_records_without_network():
    adapter = RecordingEmailNotificationAdapter()
    delivery = adapter.deliver(_alert_payload())
    assert adapter.channel_id == "email"
    assert delivery.status == "recorded"
    assert delivery.detail.startswith("[JobRadar]")
    assert len(adapter.outbox) == 1


def test_digest_payload_formatting():
    digest = MorningDigest(
        id="digest-1",
        run_context="2026-08-11",
        correlation_id="c1",
        digest_date="2026-08-11",
        new_items=(),
        updated_items=(),
        expired_items=(),
        top_recommendations=(),
        is_noop=True,
        skipped_below_threshold_count=0,
        skipped_missing_score_count=0,
        skipped_missing_posting_count=0,
    )
    payload = NotificationPayload(
        kind="morning_digest",
        correlation_id="c1",
        run_context="2026-08-11",
        digest=digest,
    )
    delivery = InAppNotificationAdapter().deliver(payload)
    assert "Morning digest 2026-08-11" in delivery.detail
