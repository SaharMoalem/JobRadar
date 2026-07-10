from __future__ import annotations

from src.domain.recommendation_gating import GatedRecommendation
from src.ports.recommendation_gating_port import GatedRecommendationRepositoryPort


class InMemoryGatedRecommendationAdapter(GatedRecommendationRepositoryPort):
    def __init__(self) -> None:
        self._recommendations: dict[str, GatedRecommendation] = {}

    def list_recommendations(self) -> list[GatedRecommendation]:
        return list(self._recommendations.values())

    def list_actionable(self) -> list[GatedRecommendation]:
        return [item for item in self._recommendations.values() if item.actionable]

    def replace_recommendations(
        self,
        recommendations: list[GatedRecommendation],
    ) -> list[GatedRecommendation]:
        self._recommendations = {
            recommendation.job_posting_id: recommendation for recommendation in recommendations
        }
        return list(self._recommendations.values())
