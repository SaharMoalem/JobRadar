from __future__ import annotations

from typing import Protocol

from src.domain.precision_policy import PrecisionPolicyConfig, TopRecommendation


class PrecisionPolicyConfigRepositoryPort(Protocol):
    def get_config(self) -> PrecisionPolicyConfig | None: ...

    def save_config(self, config: PrecisionPolicyConfig) -> PrecisionPolicyConfig: ...


class TopRecommendationRepositoryPort(Protocol):
    def list_all(self) -> list[TopRecommendation]: ...

    def list_top(self) -> list[TopRecommendation]: ...

    def replace_recommendations(
        self,
        recommendations: list[TopRecommendation],
    ) -> list[TopRecommendation]: ...
