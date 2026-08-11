from __future__ import annotations

from typing import Protocol

from src.domain.immediate_alert import (
    ImmediateAlert,
    ImmediateAlertBatchResult,
    ImmediateAlertConfig,
    ImmediateAlertFailure,
)


class ImmediateAlertConfigRepositoryPort(Protocol):
    def get_config(self) -> ImmediateAlertConfig | None: ...

    def save_config(self, config: ImmediateAlertConfig) -> ImmediateAlertConfig: ...


class ImmediateAlertRepositoryPort(Protocol):
    def save_alerts(self, alerts: list[ImmediateAlert]) -> list[ImmediateAlert]: ...

    def list_alerts(self) -> list[ImmediateAlert]: ...

    def list_for_run_context(self, run_context: str) -> list[ImmediateAlert]: ...

    def has_alert(self, *, run_context: str, job_posting_id: str) -> bool: ...


class ImmediateAlertTelemetryPort(Protocol):
    def record_batch(self, result: ImmediateAlertBatchResult) -> None: ...

    def record_failure(self, failure: ImmediateAlertFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
