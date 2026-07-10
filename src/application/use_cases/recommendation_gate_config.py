from __future__ import annotations

from dataclasses import dataclass

from src.domain.recommendation_gating import RecommendationGateConfig
from src.domain.recommendation_policy import validate_gate_config
from src.ports.recommendation_gating_port import RecommendationGateConfigRepositoryPort


@dataclass(slots=True)
class RecommendationGateConfigService:
    repository: RecommendationGateConfigRepositoryPort

    def get(self) -> RecommendationGateConfig:
        return self.repository.get_config() or RecommendationGateConfig()

    def save(
        self,
        *,
        global_threshold: int,
        skill_overlap_min_pct: int,
        recency_window_days: int,
        enforce_seniority: bool = True,
        enforce_skill_overlap: bool = True,
        enforce_language: bool = True,
        enforce_region: bool = True,
        enforce_recency: bool = True,
        enforce_active_link: bool = True,
        config_version: str = "v1",
    ) -> RecommendationGateConfig:
        config = RecommendationGateConfig(
            config_version=config_version,
            global_threshold=global_threshold,
            skill_overlap_min_pct=skill_overlap_min_pct,
            recency_window_days=recency_window_days,
            enforce_seniority=enforce_seniority,
            enforce_skill_overlap=enforce_skill_overlap,
            enforce_language=enforce_language,
            enforce_region=enforce_region,
            enforce_recency=enforce_recency,
            enforce_active_link=enforce_active_link,
        )
        validate_gate_config(config)
        return self.repository.save_config(config)

    def validate(self, config: RecommendationGateConfig) -> None:
        validate_gate_config(config)
