from __future__ import annotations

from dataclasses import dataclass

from src.domain.precision_policy import PrecisionPolicyConfig
from src.domain.precision_ranking_policy import validate_precision_config
from src.ports.precision_policy_port import PrecisionPolicyConfigRepositoryPort


@dataclass(slots=True)
class PrecisionPolicyConfigService:
    repository: PrecisionPolicyConfigRepositoryPort

    def get(self) -> PrecisionPolicyConfig:
        return self.repository.get_config() or PrecisionPolicyConfig()

    def save(
        self,
        *,
        min_confidence_for_top: int,
        max_top_count: int,
        config_version: str = "v1",
    ) -> PrecisionPolicyConfig:
        config = PrecisionPolicyConfig(
            config_version=config_version,
            min_confidence_for_top=min_confidence_for_top,
            max_top_count=max_top_count,
        )
        validate_precision_config(config)
        return self.repository.save_config(config)
