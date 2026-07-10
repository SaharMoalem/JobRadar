from __future__ import annotations

import json
import logging

from src.domain.lifecycle import JobLifecycleTransition, RetentionBatchResult
from src.ports.lifecycle_telemetry_port import LifecycleTelemetryPort

logger = logging.getLogger("jobradar.lifecycle")


class StructuredLifecycleTelemetryAdapter(LifecycleTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "transitions_total": 0,
            "retention_archived_total": 0,
        }
        self._transitions_by_state: dict[str, int] = {}

    def record_transition(self, transition: JobLifecycleTransition) -> None:
        self._metrics["transitions_total"] += 1
        state_key = f"transitions_to_{transition.to_state.value}_total"
        self._transitions_by_state[state_key] = self._transitions_by_state.get(state_key, 0) + 1
        payload = {
            "event": "job_lifecycle_transition",
            "job_posting_id": transition.job_posting_id,
            "from_state": transition.from_state.value if transition.from_state else None,
            "to_state": transition.to_state.value,
            "reason": transition.reason,
            "correlation_id": transition.correlation_id,
            "transitioned_at": transition.transitioned_at.isoformat(),
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_retention_batch(self, result: RetentionBatchResult) -> None:
        self._metrics["retention_archived_total"] += result.archived_count
        payload = {
            "event": "job_retention_batch",
            "archived_count": result.archived_count,
            "correlation_id": result.correlation_id,
            "evaluated_at": result.evaluated_at.isoformat(),
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return {**self._metrics, **self._transitions_by_state}
