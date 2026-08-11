from __future__ import annotations

import json
import logging

from src.domain.immediate_alert import ImmediateAlertBatchResult, ImmediateAlertFailure
from src.ports.immediate_alert_port import ImmediateAlertTelemetryPort

logger = logging.getLogger("jobradar.immediate_alerts")


class StructuredImmediateAlertTelemetryAdapter(ImmediateAlertTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "immediate_alert_runs_total": 0,
            "immediate_alerts_triggered_total": 0,
            "immediate_alerts_skipped_threshold_total": 0,
            "immediate_alerts_skipped_duplicate_total": 0,
            "immediate_alerts_skipped_missing_posting_total": 0,
            "immediate_alert_failures_total": 0,
        }

    def record_batch(self, result: ImmediateAlertBatchResult) -> None:
        self._metrics["immediate_alert_runs_total"] += 1
        self._metrics["immediate_alerts_triggered_total"] += result.triggered_count
        self._metrics["immediate_alerts_skipped_threshold_total"] += (
            result.skipped_below_threshold_count
        )
        self._metrics["immediate_alerts_skipped_duplicate_total"] += result.skipped_duplicate_count
        self._metrics["immediate_alerts_skipped_missing_posting_total"] += (
            result.skipped_missing_posting_count
        )
        payload = {
            "event": "immediate_alert_batch",
            "correlation_id": result.correlation_id,
            "run_context": result.run_context,
            "triggered_count": result.triggered_count,
            "skipped_below_threshold_count": result.skipped_below_threshold_count,
            "skipped_duplicate_count": result.skipped_duplicate_count,
            "skipped_missing_posting_count": result.skipped_missing_posting_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: ImmediateAlertFailure) -> None:
        self._metrics["immediate_alert_failures_total"] += 1
        payload = {
            "event": "immediate_alert_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
