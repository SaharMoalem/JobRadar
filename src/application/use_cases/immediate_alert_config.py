from __future__ import annotations

from dataclasses import dataclass

from src.domain.immediate_alert import ImmediateAlertConfig
from src.domain.immediate_alert_policy import validate_alert_config
from src.ports.immediate_alert_port import ImmediateAlertConfigRepositoryPort


@dataclass(slots=True)
class ImmediateAlertConfigService:
    repository: ImmediateAlertConfigRepositoryPort

    def get(self) -> ImmediateAlertConfig:
        return self.repository.get_config() or ImmediateAlertConfig()

    def save(
        self,
        *,
        alert_threshold: int,
        config_version: str = "v1",
    ) -> ImmediateAlertConfig:
        config = ImmediateAlertConfig(
            config_version=config_version,
            alert_threshold=alert_threshold,
        )
        validate_alert_config(config)
        return self.repository.save_config(config)
