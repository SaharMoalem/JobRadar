from __future__ import annotations

import json
import logging

from src.domain.notification import NotificationDeliveryBatchResult, NotificationDeliveryFailure
from src.ports.notification_channel_port import NotificationTelemetryPort

logger = logging.getLogger("jobradar.notifications")


class StructuredNotificationTelemetryAdapter(NotificationTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "notification_deliver_runs_total": 0,
            "notification_deliveries_total": 0,
            "notification_delivery_failures_total": 0,
            "notification_skipped_missing_source_total": 0,
            "notification_failed_adapter_total": 0,
        }

    def record_batch(self, result: NotificationDeliveryBatchResult) -> None:
        self._metrics["notification_deliver_runs_total"] += 1
        self._metrics["notification_deliveries_total"] += result.delivered_count
        self._metrics["notification_skipped_missing_source_total"] += (
            result.skipped_missing_source_count
        )
        self._metrics["notification_failed_adapter_total"] += result.failed_count
        payload = {
            "event": "notification_delivery_batch",
            "correlation_id": result.correlation_id,
            "run_context": result.run_context,
            "kind": result.kind,
            "delivered_count": result.delivered_count,
            "failed_count": result.failed_count,
            "skipped_missing_source_count": result.skipped_missing_source_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: NotificationDeliveryFailure) -> None:
        self._metrics["notification_delivery_failures_total"] += 1
        payload = {
            "event": "notification_delivery_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
