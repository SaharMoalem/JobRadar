from __future__ import annotations

from src.domain.precision_policy import TopRecommendation
from src.ports.precision_policy_port import TopRecommendationRepositoryPort


class InMemoryTopRecommendationAdapter(TopRecommendationRepositoryPort):
    def __init__(self) -> None:
        self._recommendations: dict[str, TopRecommendation] = {}

    def list_all(self) -> list[TopRecommendation]:
        return sorted(
            self._recommendations.values(),
            key=lambda item: (
                item.rank is None,
                item.rank or 0,
                -item.match_score,
                item.job_posting_id,
            ),
        )

    def list_top(self) -> list[TopRecommendation]:
        top = [item for item in self._recommendations.values() if not item.suppressed and item.rank is not None]
        return sorted(top, key=lambda item: item.rank or 0)

    def replace_recommendations(
        self,
        recommendations: list[TopRecommendation],
    ) -> list[TopRecommendation]:
        self._recommendations = {
            recommendation.job_posting_id: recommendation for recommendation in recommendations
        }
        return list(self._recommendations.values())
