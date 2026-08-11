from __future__ import annotations

from dataclasses import dataclass

from src.domain.morning_digest import MorningDigestConfig
from src.domain.morning_digest_policy import validate_digest_config
from src.ports.morning_digest_port import MorningDigestConfigRepositoryPort


@dataclass(slots=True)
class MorningDigestConfigService:
    repository: MorningDigestConfigRepositoryPort

    def get(self) -> MorningDigestConfig:
        return self.repository.get_config() or MorningDigestConfig()

    def save(
        self,
        *,
        digest_threshold: int,
        digest_window_hours: int = 24,
        top_n: int = 5,
        config_version: str = "v1",
    ) -> MorningDigestConfig:
        config = MorningDigestConfig(
            config_version=config_version,
            digest_threshold=digest_threshold,
            digest_window_hours=digest_window_hours,
            top_n=top_n,
        )
        validate_digest_config(config)
        return self.repository.save_config(config)
