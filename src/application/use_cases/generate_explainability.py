from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.explainability import (
    ExplainabilityBatchResult,
    ExplainabilityFailure,
    ExplainabilityQualityError,
)
from src.domain.explainability_policy import (
    build_explainable_recommendation,
    build_failed_explainable_recommendation,
    validate_explainability_note,
)
from src.ports.explainability_port import (
    ExplainabilityGeneratorPort,
    ExplainableRecommendationRepositoryPort,
)
from src.ports.explainability_telemetry_port import ExplainabilityTelemetryPort
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.match_scoring_port import MatchScoreRepositoryPort, UserProfileRepositoryPort
from src.ports.precision_policy_port import TopRecommendationRepositoryPort
from src.ports.recommendation_gating_port import GatedRecommendationRepositoryPort


@dataclass(slots=True)
class GenerateExplainabilityUseCase:
    profile_repository: UserProfileRepositoryPort
    job_posting_repository: JobPostingRepositoryPort
    match_score_repository: MatchScoreRepositoryPort
    gated_recommendation_repository: GatedRecommendationRepositoryPort
    top_recommendation_repository: TopRecommendationRepositoryPort
    explainable_recommendation_repository: ExplainableRecommendationRepositoryPort
    generator: ExplainabilityGeneratorPort
    telemetry: ExplainabilityTelemetryPort

    def run_explainability(
        self,
        *,
        correlation_id: str,
        generated_at: datetime | None = None,
    ) -> ExplainabilityBatchResult | ExplainabilityFailure:
        profile = self.profile_repository.get_profile()
        if profile is None:
            failure = ExplainabilityFailure(
                code="PROFILE_NOT_CONFIGURED",
                message="User profile is not configured.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        generated = generated_at or datetime.now(timezone.utc)
        postings_by_id = {posting.id: posting for posting in self.job_posting_repository.list_complete()}
        scores_by_id = {score.job_posting_id: score for score in self.match_score_repository.list_scores()}
        gated_by_id = {
            recommendation.job_posting_id: recommendation
            for recommendation in self.gated_recommendation_repository.list_recommendations()
        }

        results = []
        for top in self.top_recommendation_repository.list_top():
            posting = postings_by_id.get(top.job_posting_id)
            match_score = scores_by_id.get(top.job_posting_id)
            gated = gated_by_id.get(top.job_posting_id)
            if posting is None or match_score is None or gated is None:
                results.append(
                    build_failed_explainable_recommendation(
                        top_recommendation=top,
                        match_score=match_score,
                        code="EXPLAINABILITY_CONTEXT_MISSING",
                        reason="Job posting, match score, or gating context is missing.",
                        generated_at=generated,
                    )
                )
                continue

            try:
                note = self.generator.generate(profile, posting, match_score, gated)
                validate_explainability_note(note)
                results.append(
                    build_explainable_recommendation(
                        top_recommendation=top,
                        match_score=match_score,
                        gated_recommendation=gated,
                        note=note,
                        generated_at=generated,
                    )
                )
            except ExplainabilityQualityError as exc:
                results.append(
                    build_failed_explainable_recommendation(
                        top_recommendation=top,
                        match_score=match_score,
                        code=exc.code,
                        reason=str(exc),
                        generated_at=generated,
                    )
                )

        saved = self.explainable_recommendation_repository.replace_recommendations(results)
        promoted_count = sum(1 for item in saved if item.promoted)
        result = ExplainabilityBatchResult(
            recommendations=tuple(saved),
            promoted_count=promoted_count,
            failed_count=len(saved) - promoted_count,
            correlation_id=correlation_id,
        )
        self.telemetry.record_batch(result)
        return result
