from __future__ import annotations

from typing import Protocol

from src.domain.recommendation_gating import GatedRecommendation, RecommendationGateConfig


class RecommendationGateConfigRepositoryPort(Protocol):
    def get_config(self) -> RecommendationGateConfig | None: ...

    def save_config(self, config: RecommendationGateConfig) -> RecommendationGateConfig: ...


class GatedRecommendationRepositoryPort(Protocol):
    def list_recommendations(self) -> list[GatedRecommendation]: ...

    def list_actionable(self) -> list[GatedRecommendation]: ...

    def replace_recommendations(
        self,
        recommendations: list[GatedRecommendation],
    ) -> list[GatedRecommendation]: ...
