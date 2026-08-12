from __future__ import annotations

from uuid import uuid4

from src.adapters.notification.payload_formatter import format_payload_detail
from src.domain.notification import NotificationDelivery, NotificationPayload
from src.ports.notification_channel_port import NotificationChannelAdapter


class RecordingEmailNotificationAdapter(NotificationChannelAdapter):
    """Local-only email adapter — records subject/body, never sends SMTP."""

    channel_id = "email"

    def __init__(self) -> None:
        self.outbox: list[NotificationDelivery] = []

    def deliver(self, payload: NotificationPayload) -> NotificationDelivery:
        detail = format_payload_detail(payload)
        subject = (
            f"[JobRadar] Alert: {payload.source_id}"
            if payload.kind == "immediate_alert"
            else f"[JobRadar] Morning digest: {payload.run_context}"
        )
        delivery = NotificationDelivery(
            id=f"ndel-{uuid4().hex[:12]}",
            channel_id=self.channel_id,
            kind=payload.kind,
            source_id=payload.source_id,
            correlation_id=payload.correlation_id,
            run_context=payload.run_context,
            status="recorded",
            detail=f"{subject} | {detail}",
        )
        self.outbox.append(delivery)
        return delivery
