from __future__ import annotations

from typing import Protocol

from src.domain.recommendation_gating import GatingBatchResult, GatingFailure


class GatingTelemetryPort(Protocol):
    def record_batch(self, result: GatingBatchResult) -> None: ...

    def record_failure(self, failure: GatingFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
