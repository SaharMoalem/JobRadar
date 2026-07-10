from __future__ import annotations

from src.domain.recommendation_gating import RecommendationGateConfig
from src.ports.recommendation_gating_port import RecommendationGateConfigRepositoryPort


class InMemoryRecommendationGateConfigAdapter(RecommendationGateConfigRepositoryPort):
    def __init__(self) -> None:
        self._config: RecommendationGateConfig | None = None

    def get_config(self) -> RecommendationGateConfig | None:
        return self._config

    def save_config(self, config: RecommendationGateConfig) -> RecommendationGateConfig:
        self._config = config
        return config
