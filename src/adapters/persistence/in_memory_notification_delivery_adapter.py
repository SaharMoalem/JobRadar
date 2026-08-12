from __future__ import annotations

from src.domain.notification import NotificationDelivery
from src.ports.notification_channel_port import NotificationDeliveryRepositoryPort


class InMemoryNotificationDeliveryAdapter(NotificationDeliveryRepositoryPort):
    def __init__(self) -> None:
        self._deliveries: list[NotificationDelivery] = []

    def save_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self._deliveries.append(delivery)
        return delivery

    def list_deliveries(self) -> list[NotificationDelivery]:
        return sorted(self._deliveries, key=lambda item: item.created_at)

    def list_for_channel(self, channel_id: str) -> list[NotificationDelivery]:
        return [item for item in self.list_deliveries() if item.channel_id == channel_id]
