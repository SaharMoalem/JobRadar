from __future__ import annotations

import json
import logging

from src.domain.recommendation_gating import GatingBatchResult, GatingFailure
from src.ports.gating_telemetry_port import GatingTelemetryPort

logger = logging.getLogger("jobradar.gating")


class StructuredGatingTelemetryAdapter(GatingTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "gating_runs_total": 0,
            "actionable_recommendations_total": 0,
            "gating_failures_total": 0,
        }

    def record_batch(self, result: GatingBatchResult) -> None:
        self._metrics["gating_runs_total"] += 1
        self._metrics["actionable_recommendations_total"] += result.actionable_count
        payload = {
            "event": "recommendation_gating_batch",
            "correlation_id": result.correlation_id,
            "actionable_count": result.actionable_count,
            "non_actionable_count": result.non_actionable_count,
            "skipped_count": result.skipped_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: GatingFailure) -> None:
        self._metrics["gating_failures_total"] += 1
        payload = {
            "event": "recommendation_gating_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
