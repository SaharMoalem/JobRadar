from __future__ import annotations

from uuid import uuid4

from src.adapters.notification.payload_formatter import format_payload_detail
from src.domain.notification import NotificationDelivery, NotificationPayload
from src.ports.notification_channel_port import NotificationChannelAdapter


class InAppNotificationAdapter(NotificationChannelAdapter):
    channel_id = "in_app"

    def __init__(self) -> None:
        self.inbox: list[NotificationDelivery] = []

    def deliver(self, payload: NotificationPayload) -> NotificationDelivery:
        delivery = NotificationDelivery(
            id=f"ndel-{uuid4().hex[:12]}",
            channel_id=self.channel_id,
            kind=payload.kind,
            source_id=payload.source_id,
            correlation_id=payload.correlation_id,
            run_context=payload.run_context,
            status="delivered",
            detail=format_payload_detail(payload),
        )
        self.inbox.append(delivery)
        return delivery
