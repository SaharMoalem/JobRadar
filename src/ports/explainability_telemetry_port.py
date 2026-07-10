from __future__ import annotations

from typing import Protocol

from src.domain.explainability import ExplainabilityBatchResult, ExplainabilityFailure


class ExplainabilityTelemetryPort(Protocol):
    def record_batch(self, result: ExplainabilityBatchResult) -> None: ...

    def record_failure(self, failure: ExplainabilityFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
