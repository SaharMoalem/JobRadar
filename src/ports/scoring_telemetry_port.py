from __future__ import annotations

from typing import Protocol

from src.domain.match_scoring import ScoringBatchResult, ScoringFailure


class ScoringTelemetryPort(Protocol):
    def record_batch(self, result: ScoringBatchResult) -> None: ...

    def record_failure(self, failure: ScoringFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
