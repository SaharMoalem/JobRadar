from __future__ import annotations

from src.domain.explainability import ExplainableRecommendation
from src.domain.explainability_policy import generate_explainability_note
from src.domain.job_posting import JobPosting
from src.domain.match_scoring import MatchScore
from src.domain.recommendation_gating import GatedRecommendation
from src.domain.user_profile import UserProfile
from src.ports.explainability_port import (
    ExplainabilityGeneratorPort,
    ExplainableRecommendationRepositoryPort,
)


class RuleBasedExplainabilityGeneratorAdapter(ExplainabilityGeneratorPort):
    def generate(
        self,
        profile: UserProfile,
        posting: JobPosting,
        match_score: MatchScore,
        gated_recommendation: GatedRecommendation,
    ):
        return generate_explainability_note(profile, posting, match_score, gated_recommendation)


class InMemoryExplainableRecommendationAdapter(ExplainableRecommendationRepositoryPort):
    def __init__(self) -> None:
        self._recommendations: dict[str, ExplainableRecommendation] = {}

    def list_all(self) -> list[ExplainableRecommendation]:
        return sorted(self._recommendations.values(), key=lambda item: (-item.match_score, item.job_posting_id))

    def list_promoted(self) -> list[ExplainableRecommendation]:
        return [
            item
            for item in self.list_all()
            if item.promoted and item.note is not None
        ]

    def replace_recommendations(
        self,
        recommendations: list[ExplainableRecommendation],
    ) -> list[ExplainableRecommendation]:
        self._recommendations = {
            recommendation.job_posting_id: recommendation for recommendation in recommendations
        }
        return self.list_all()
