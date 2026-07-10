from __future__ import annotations

from typing import Protocol

from src.domain.precision_policy import PrecisionBatchResult, PrecisionFailure


class PrecisionTelemetryPort(Protocol):
    def record_batch(self, result: PrecisionBatchResult) -> None: ...

    def record_failure(self, failure: PrecisionFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
