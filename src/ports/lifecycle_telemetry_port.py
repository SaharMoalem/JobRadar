from __future__ import annotations

from typing import Protocol

from src.domain.lifecycle import JobLifecycleTransition, RetentionBatchResult


class LifecycleTelemetryPort(Protocol):
    def record_transition(self, transition: JobLifecycleTransition) -> None: ...

    def record_retention_batch(self, result: RetentionBatchResult) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
