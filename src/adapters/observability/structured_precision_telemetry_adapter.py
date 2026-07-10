from __future__ import annotations

import json
import logging

from src.domain.precision_policy import PrecisionBatchResult, PrecisionFailure
from src.ports.precision_telemetry_port import PrecisionTelemetryPort

logger = logging.getLogger("jobradar.precision")


class StructuredPrecisionTelemetryAdapter(PrecisionTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "precision_runs_total": 0,
            "top_recommendations_emitted_total": 0,
            "suppressed_low_confidence_total": 0,
            "suppressed_capacity_total": 0,
            "precision_failures_total": 0,
        }

    def record_batch(self, result: PrecisionBatchResult) -> None:
        self._metrics["precision_runs_total"] += 1
        self._metrics["top_recommendations_emitted_total"] += result.top_count
        self._metrics["suppressed_low_confidence_total"] += result.suppressed_low_confidence_count
        self._metrics["suppressed_capacity_total"] += result.suppressed_capacity_count
        payload = {
            "event": "precision_policy_batch",
            "correlation_id": result.correlation_id,
            "top_count": result.top_count,
            "suppressed_low_confidence_count": result.suppressed_low_confidence_count,
            "suppressed_capacity_count": result.suppressed_capacity_count,
            "actionable_input_count": result.actionable_input_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: PrecisionFailure) -> None:
        self._metrics["precision_failures_total"] += 1
        payload = {
            "event": "precision_policy_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
