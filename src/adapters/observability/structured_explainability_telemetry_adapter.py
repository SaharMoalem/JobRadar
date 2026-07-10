from __future__ import annotations

import json
import logging

from src.domain.explainability import ExplainabilityBatchResult, ExplainabilityFailure
from src.ports.explainability_telemetry_port import ExplainabilityTelemetryPort

logger = logging.getLogger("jobradar.explainability")


class StructuredExplainabilityTelemetryAdapter(ExplainabilityTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "explainability_runs_total": 0,
            "promoted_recommendations_total": 0,
            "explainability_failures_total": 0,
            "quality_check_failures_total": 0,
        }

    def record_batch(self, result: ExplainabilityBatchResult) -> None:
        self._metrics["explainability_runs_total"] += 1
        self._metrics["promoted_recommendations_total"] += result.promoted_count
        self._metrics["quality_check_failures_total"] += result.failed_count
        payload = {
            "event": "explainability_batch",
            "correlation_id": result.correlation_id,
            "promoted_count": result.promoted_count,
            "failed_count": result.failed_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: ExplainabilityFailure) -> None:
        self._metrics["explainability_failures_total"] += 1
        payload = {
            "event": "explainability_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
