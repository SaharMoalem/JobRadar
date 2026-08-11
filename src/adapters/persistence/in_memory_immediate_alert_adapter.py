from __future__ import annotations

from src.domain.immediate_alert import ImmediateAlert, ImmediateAlertConfig
from src.ports.immediate_alert_port import (
    ImmediateAlertConfigRepositoryPort,
    ImmediateAlertRepositoryPort,
)


class InMemoryImmediateAlertConfigAdapter(ImmediateAlertConfigRepositoryPort):
    def __init__(self) -> None:
        self._config: ImmediateAlertConfig | None = None

    def get_config(self) -> ImmediateAlertConfig | None:
        return self._config

    def save_config(self, config: ImmediateAlertConfig) -> ImmediateAlertConfig:
        self._config = config
        return config


class InMemoryImmediateAlertAdapter(ImmediateAlertRepositoryPort):
    def __init__(self) -> None:
        self._alerts: list[ImmediateAlert] = []
        self._keys: set[tuple[str, str]] = set()

    def save_alerts(self, alerts: list[ImmediateAlert]) -> list[ImmediateAlert]:
        saved: list[ImmediateAlert] = []
        for alert in alerts:
            key = (alert.run_context, alert.job_posting_id)
            if key in self._keys:
                continue
            self._keys.add(key)
            self._alerts.append(alert)
            saved.append(alert)
        return saved

    def list_alerts(self) -> list[ImmediateAlert]:
        return sorted(self._alerts, key=lambda item: item.created_at)

    def list_for_run_context(self, run_context: str) -> list[ImmediateAlert]:
        return [
            alert
            for alert in self.list_alerts()
            if alert.run_context == run_context
        ]

    def has_alert(self, *, run_context: str, job_posting_id: str) -> bool:
        return (run_context, job_posting_id) in self._keys
