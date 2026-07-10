from __future__ import annotations

import json
import logging

from src.domain.match_scoring import ScoringBatchResult, ScoringFailure
from src.ports.scoring_telemetry_port import ScoringTelemetryPort

logger = logging.getLogger("jobradar.scoring")


class StructuredScoringTelemetryAdapter(ScoringTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "scoring_runs_total": 0,
            "scores_persisted_total": 0,
            "scoring_failures_total": 0,
        }

    def record_batch(self, result: ScoringBatchResult) -> None:
        self._metrics["scoring_runs_total"] += 1
        self._metrics["scores_persisted_total"] += result.scored_count
        payload = {
            "event": "match_scoring_batch",
            "correlation_id": result.correlation_id,
            "scored_count": result.scored_count,
            "skipped_count": result.skipped_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: ScoringFailure) -> None:
        self._metrics["scoring_failures_total"] += 1
        payload = {
            "event": "match_scoring_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
