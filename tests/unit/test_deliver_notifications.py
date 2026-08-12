from datetime import datetime, timezone

from src.adapters.notification import (
    InAppNotificationAdapter,
    NotificationChannelRegistry,
    RecordingEmailNotificationAdapter,
)
from src.adapters.observability.structured_notification_telemetry_adapter import (
    StructuredNotificationTelemetryAdapter,
)
from src.adapters.persistence.in_memory_immediate_alert_adapter import InMemoryImmediateAlertAdapter
from src.adapters.persistence.in_memory_morning_digest_adapter import InMemoryMorningDigestAdapter
from src.adapters.persistence.in_memory_notification_delivery_adapter import (
    InMemoryNotificationDeliveryAdapter,
)
from src.application.use_cases.deliver_notifications import DeliverNotificationsUseCase
from src.domain.immediate_alert import ImmediateAlert
from src.domain.morning_digest import MorningDigest
from src.domain.notification import NotificationDelivery, NotificationDeliveryFailure, NotificationPayload
from src.ports.notification_channel_port import NotificationChannelAdapter


class FakeTelegramAdapter(NotificationChannelAdapter):
    channel_id = "telegram"

    def deliver(self, payload: NotificationPayload) -> NotificationDelivery:
        return NotificationDelivery(
            id="ndel-telegram",
            channel_id=self.channel_id,
            kind=payload.kind,
            source_id=payload.source_id,
            correlation_id=payload.correlation_id,
            run_context=payload.run_context,
            status="recorded",
            detail="telegram",
        )


def _use_case(
    *,
    alerts: InMemoryImmediateAlertAdapter | None = None,
    digests: InMemoryMorningDigestAdapter | None = None,
    registry: NotificationChannelRegistry | None = None,
) -> DeliverNotificationsUseCase:
    return DeliverNotificationsUseCase(
        alert_repository=alerts or InMemoryImmediateAlertAdapter(),
        digest_repository=digests or InMemoryMorningDigestAdapter(),
        channel_registry=registry
        or NotificationChannelRegistry(
            [InAppNotificationAdapter(), RecordingEmailNotificationAdapter()]
        ),
        delivery_repository=InMemoryNotificationDeliveryAdapter(),
        telemetry=StructuredNotificationTelemetryAdapter(),
    )


def test_deliver_alerts_fans_out_to_both_channels():
    alerts = InMemoryImmediateAlertAdapter()
    alerts.save_alerts(
        [
            ImmediateAlert(
                id="alert-1",
                job_posting_id="job-1",
                role_summary="Role at Acme (Tel Aviv)",
                match_score=91,
                deep_link="/job-postings/job-1",
                run_context="run-a",
                correlation_id="seed",
                created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    use_case = _use_case(alerts=alerts)

    result = use_case.run(kind="immediate_alert", correlation_id="c1", run_context="run-a")

    assert result.delivered_count == 2
    assert {item.channel_id for item in result.deliveries} == {"in_app", "email"}
    assert len(use_case.list_in_app()) == 1


def test_unknown_channel_fails():
    use_case = _use_case()
    result = use_case.run(
        kind="immediate_alert",
        correlation_id="c1",
        run_context="run-a",
        channels=["sms"],
    )
    assert isinstance(result, NotificationDeliveryFailure)
    assert result.code == "NOTIFICATION_CHANNEL_UNKNOWN"


def test_missing_source_fails():
    use_case = _use_case()
    result = use_case.run(kind="morning_digest", correlation_id="c1", run_context="missing")
    assert isinstance(result, NotificationDeliveryFailure)
    assert result.code == "NOTIFICATION_SOURCE_NOT_FOUND"


def test_registry_accepts_additional_adapter_without_core_change():
    alerts = InMemoryImmediateAlertAdapter()
    alerts.save_alerts(
        [
            ImmediateAlert(
                id="alert-1",
                job_posting_id="job-1",
                role_summary="Role at Acme (Tel Aviv)",
                match_score=91,
                deep_link="/job-postings/job-1",
                run_context="run-a",
                correlation_id="seed",
                created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    registry = NotificationChannelRegistry(
        [InAppNotificationAdapter(), RecordingEmailNotificationAdapter(), FakeTelegramAdapter()]
    )
    use_case = _use_case(alerts=alerts, registry=registry)

    result = use_case.run(kind="immediate_alert", correlation_id="c1", run_context="run-a")

    assert result.delivered_count == 3
    assert {item.channel_id for item in result.deliveries} == {"in_app", "email", "telegram"}


def test_digest_delivery():
    digests = InMemoryMorningDigestAdapter()
    digests.replace_for_run_context(
        MorningDigest(
            id="digest-1",
            run_context="2026-08-11",
            correlation_id="seed",
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
    )
    use_case = _use_case(digests=digests)
    result = use_case.run(kind="morning_digest", correlation_id="c1", run_context="2026-08-11")
    assert result.delivered_count == 2
    assert result.kind == "morning_digest"


def test_blank_correlation_id_rejected():
    use_case = _use_case()
    result = use_case.run(kind="immediate_alert", correlation_id="   ")
    assert isinstance(result, NotificationDeliveryFailure)
    assert result.code == "NOTIFICATION_CORRELATION_ID_REQUIRED"


def test_selective_channel_delivery():
    alerts = InMemoryImmediateAlertAdapter()
    alerts.save_alerts(
        [
            ImmediateAlert(
                id="alert-1",
                job_posting_id="job-1",
                role_summary="Role at Acme (Tel Aviv)",
                match_score=91,
                deep_link="/job-postings/job-1",
                run_context="run-a",
                correlation_id="seed",
                created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    use_case = _use_case(alerts=alerts)
    result = use_case.run(
        kind="immediate_alert",
        correlation_id="c1",
        run_context="run-a",
        channels=["email"],
    )
    assert result.delivered_count == 1
    assert result.deliveries[0].channel_id == "email"


class FailingAdapter(NotificationChannelAdapter):
    channel_id = "failing"

    def deliver(self, payload: NotificationPayload) -> NotificationDelivery:
        raise RuntimeError("channel down")


def test_adapter_failure_isolates_sibling_channels():
    alerts = InMemoryImmediateAlertAdapter()
    alerts.save_alerts(
        [
            ImmediateAlert(
                id="alert-1",
                job_posting_id="job-1",
                role_summary="Role at Acme (Tel Aviv)",
                match_score=91,
                deep_link="/job-postings/job-1",
                run_context="run-a",
                correlation_id="seed",
                created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    registry = NotificationChannelRegistry(
        [FailingAdapter(), InAppNotificationAdapter(), RecordingEmailNotificationAdapter()]
    )
    use_case = _use_case(alerts=alerts, registry=registry)
    result = use_case.run(kind="immediate_alert", correlation_id="c1", run_context="run-a")
    assert result.failed_count == 1
    assert result.delivered_count == 2
    assert {item.channel_id for item in result.deliveries} == {"in_app", "email"}


def test_duplicate_channel_ids_deduplicated():
    alerts = InMemoryImmediateAlertAdapter()
    alerts.save_alerts(
        [
            ImmediateAlert(
                id="alert-1",
                job_posting_id="job-1",
                role_summary="Role at Acme (Tel Aviv)",
                match_score=91,
                deep_link="/job-postings/job-1",
                run_context="run-a",
                correlation_id="seed",
                created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    use_case = _use_case(alerts=alerts)
    result = use_case.run(
        kind="immediate_alert",
        correlation_id="c1",
        run_context="run-a",
        channels=["email", "email"],
    )
    assert result.delivered_count == 1
    assert result.deliveries[0].channel_id == "email"


def test_digest_source_id_mismatched_run_context_not_found():
    digests = InMemoryMorningDigestAdapter()
    digests.replace_for_run_context(
        MorningDigest(
            id="digest-1",
            run_context="2026-08-11",
            correlation_id="seed",
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
    )
    use_case = _use_case(digests=digests)
    result = use_case.run(
        kind="morning_digest",
        correlation_id="c1",
        run_context="2026-08-12",
        source_id="digest-1",
    )
    assert isinstance(result, NotificationDeliveryFailure)
    assert result.code == "NOTIFICATION_SOURCE_NOT_FOUND"


def test_blank_source_id_rejected():
    use_case = _use_case()
    result = use_case.run(
        kind="morning_digest",
        correlation_id="c1",
        run_context="2026-08-11",
        source_id="   ",
    )
    assert isinstance(result, NotificationDeliveryFailure)
    assert result.code == "NOTIFICATION_SOURCE_NOT_FOUND"


def test_no_registered_channels_fails():
    alerts = InMemoryImmediateAlertAdapter()
    alerts.save_alerts(
        [
            ImmediateAlert(
                id="alert-1",
                job_posting_id="job-1",
                role_summary="Role at Acme (Tel Aviv)",
                match_score=91,
                deep_link="/job-postings/job-1",
                run_context="run-a",
                correlation_id="seed",
                created_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    use_case = _use_case(alerts=alerts, registry=NotificationChannelRegistry([]))
    result = use_case.run(kind="immediate_alert", correlation_id="c1", run_context="run-a")
    assert isinstance(result, NotificationDeliveryFailure)
    assert result.code == "NOTIFICATION_NO_CHANNELS_REGISTERED"
