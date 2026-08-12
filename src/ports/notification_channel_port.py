from __future__ import annotations

from typing import Protocol

from src.domain.notification import (
    NotificationDelivery,
    NotificationDeliveryBatchResult,
    NotificationDeliveryFailure,
    NotificationPayload,
)


class NotificationChannelAdapter(Protocol):
    channel_id: str

    def deliver(self, payload: NotificationPayload) -> NotificationDelivery: ...


class NotificationDeliveryRepositoryPort(Protocol):
    def save_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery: ...

    def list_deliveries(self) -> list[NotificationDelivery]: ...

    def list_for_channel(self, channel_id: str) -> list[NotificationDelivery]: ...


class NotificationTelemetryPort(Protocol):
    def record_batch(self, result: NotificationDeliveryBatchResult) -> None: ...

    def record_failure(self, failure: NotificationDeliveryFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
