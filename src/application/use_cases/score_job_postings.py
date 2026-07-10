from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.match_scoring import (
    MatchScoringConfig,
    ScoringBatchResult,
    ScoringFailure,
    ScoringValidationError,
)
from src.domain.match_scoring_policy import compute_match_score, is_scorable_posting, validate_profile_for_scoring
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.match_scoring_port import MatchScoreRepositoryPort, UserProfileRepositoryPort
from src.ports.scoring_telemetry_port import ScoringTelemetryPort


@dataclass(slots=True)
class ScoreJobPostingsUseCase:
    profile_repository: UserProfileRepositoryPort
    job_posting_repository: JobPostingRepositoryPort
    match_score_repository: MatchScoreRepositoryPort
    telemetry: ScoringTelemetryPort
    config: MatchScoringConfig | None = None

    def score_all_eligible(
        self,
        *,
        correlation_id: str,
        evaluated_at: datetime | None = None,
    ) -> ScoringBatchResult | ScoringFailure:
        profile = self.profile_repository.get_profile()
        if profile is None:
            failure = ScoringFailure(
                code="PROFILE_NOT_CONFIGURED",
                message="User profile is not configured.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        try:
            validate_profile_for_scoring(profile)
        except ScoringValidationError as exc:
            failure = ScoringFailure(code=exc.code, message=str(exc), correlation_id=correlation_id)
            self.telemetry.record_failure(failure)
            return failure

        scoring_config = self.config or MatchScoringConfig()
        evaluated = evaluated_at or datetime.now(timezone.utc)
        scores = []
        skipped_count = 0
        for posting in self.job_posting_repository.list_complete():
            if not is_scorable_posting(posting):
                skipped_count += 1
                continue
            match_score = compute_match_score(
                profile,
                posting,
                config=scoring_config,
                now=evaluated,
            )
            scores.append(match_score)

        saved_scores = self.match_score_repository.replace_scores(scores)
        result = ScoringBatchResult(
            scores=tuple(saved_scores),
            scored_count=len(saved_scores),
            skipped_count=skipped_count,
            correlation_id=correlation_id,
        )
        self.telemetry.record_batch(result)
        return result
