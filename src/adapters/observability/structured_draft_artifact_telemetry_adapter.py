from __future__ import annotations

import json
import logging

from src.domain.draft_artifact import DraftArtifact, DraftGenerationFailure
from src.ports.draft_artifact_port import DraftArtifactTelemetryPort

logger = logging.getLogger("jobradar.draft_artifacts")


class StructuredDraftArtifactTelemetryAdapter(DraftArtifactTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "draft_artifacts_generated_total": 0,
            "draft_generation_failures_total": 0,
        }

    def record_generated(self, artifact: DraftArtifact) -> None:
        self._metrics["draft_artifacts_generated_total"] += 1
        payload = {
            "event": "draft_artifact_generated",
            "artifact_id": artifact.id,
            "job_posting_id": artifact.job_posting_id,
            "kind": artifact.kind.value,
            "correlation_id": artifact.correlation_id,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: DraftGenerationFailure) -> None:
        self._metrics["draft_generation_failures_total"] += 1
        payload = {
            "event": "draft_generation_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
