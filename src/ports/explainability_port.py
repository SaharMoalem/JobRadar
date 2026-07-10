from __future__ import annotations

from typing import Protocol

from src.domain.explainability import ExplainabilityNote, ExplainableRecommendation
from src.domain.job_posting import JobPosting
from src.domain.match_scoring import MatchScore
from src.domain.recommendation_gating import GatedRecommendation
from src.domain.user_profile import UserProfile


class ExplainabilityGeneratorPort(Protocol):
    def generate(
        self,
        profile: UserProfile,
        posting: JobPosting,
        match_score: MatchScore,
        gated_recommendation: GatedRecommendation,
    ) -> ExplainabilityNote: ...


class ExplainableRecommendationRepositoryPort(Protocol):
    def list_all(self) -> list[ExplainableRecommendation]: ...

    def list_promoted(self) -> list[ExplainableRecommendation]: ...

    def replace_recommendations(
        self,
        recommendations: list[ExplainableRecommendation],
    ) -> list[ExplainableRecommendation]: ...
