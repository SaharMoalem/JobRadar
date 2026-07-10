from __future__ import annotations

from src.domain.precision_policy import PrecisionPolicyConfig
from src.ports.precision_policy_port import PrecisionPolicyConfigRepositoryPort


class InMemoryPrecisionPolicyConfigAdapter(PrecisionPolicyConfigRepositoryPort):
    def __init__(self) -> None:
        self._config: PrecisionPolicyConfig | None = None

    def get_config(self) -> PrecisionPolicyConfig | None:
        return self._config

    def save_config(self, config: PrecisionPolicyConfig) -> PrecisionPolicyConfig:
        self._config = config
        return config
