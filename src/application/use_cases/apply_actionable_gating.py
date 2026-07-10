from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.match_scoring import ScoringValidationError
from src.domain.match_scoring_policy import validate_profile_for_scoring
from src.domain.recommendation_gating import (
    GatingBatchResult,
    GatingFailure,
    GatingValidationError,
    RecommendationGateConfig,
)
from src.domain.recommendation_policy import evaluate_gates, validate_gate_config
from src.ports.gating_telemetry_port import GatingTelemetryPort
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.match_scoring_port import MatchScoreRepositoryPort, UserProfileRepositoryPort
from src.ports.recommendation_gating_port import (
    GatedRecommendationRepositoryPort,
    RecommendationGateConfigRepositoryPort,
)


@dataclass(slots=True)
class ApplyActionableGatingUseCase:
    profile_repository: UserProfileRepositoryPort
    job_posting_repository: JobPostingRepositoryPort
    match_score_repository: MatchScoreRepositoryPort
    gate_config_repository: RecommendationGateConfigRepositoryPort
    gated_recommendation_repository: GatedRecommendationRepositoryPort
    telemetry: GatingTelemetryPort
    default_config: RecommendationGateConfig | None = None

    def run_gating(
        self,
        *,
        correlation_id: str,
        evaluated_at: datetime | None = None,
    ) -> GatingBatchResult | GatingFailure:
        profile = self.profile_repository.get_profile()
        if profile is None:
            failure = GatingFailure(
                code="PROFILE_NOT_CONFIGURED",
                message="User profile is not configured.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        try:
            validate_profile_for_scoring(profile)
        except ScoringValidationError as exc:
            failure = GatingFailure(code=exc.code, message=str(exc), correlation_id=correlation_id)
            self.telemetry.record_failure(failure)
            return failure

        gate_config = self.gate_config_repository.get_config() or self.default_config or RecommendationGateConfig()
        try:
            validate_gate_config(gate_config)
        except GatingValidationError as exc:
            failure = GatingFailure(code=exc.code, message=str(exc), correlation_id=correlation_id)
            self.telemetry.record_failure(failure)
            return failure

        evaluated = evaluated_at or datetime.now(timezone.utc)
        postings_by_id = {posting.id: posting for posting in self.job_posting_repository.list_complete()}
        recommendations = []
        skipped_count = 0
        for match_score in self.match_score_repository.list_scores():
            posting = postings_by_id.get(match_score.job_posting_id)
            if posting is None:
                skipped_count += 1
                continue
            recommendations.append(
                evaluate_gates(
                    profile,
                    posting,
                    match_score,
                    config=gate_config,
                    now=evaluated,
                )
            )

        saved = self.gated_recommendation_repository.replace_recommendations(recommendations)
        actionable_count = sum(1 for item in saved if item.actionable)
        result = GatingBatchResult(
            recommendations=tuple(saved),
            actionable_count=actionable_count,
            non_actionable_count=len(saved) - actionable_count,
            skipped_count=skipped_count,
            correlation_id=correlation_id,
        )
        self.telemetry.record_batch(result)
        return result
