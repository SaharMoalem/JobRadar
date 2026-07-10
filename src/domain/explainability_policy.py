from __future__ import annotations

from datetime import datetime

from src.domain.explainability import (
    ExplainabilityNote,
    ExplainabilityQualityError,
    ExplainableRecommendation,
)
from src.domain.job_posting import JobPosting
from src.domain.match_scoring import MatchScore
from src.domain.precision_policy import TopRecommendation
from src.domain.recommendation_gating import GatedRecommendation
from src.domain.user_profile import UserProfile

VALID_EFFORT_ESTIMATES = frozenset({"low", "medium", "high"})


def _normalize_text(value: str) -> str:
    return value.casefold()


def _missing_skills(profile: UserProfile, posting: JobPosting) -> tuple[str, ...]:
    haystack = _normalize_text(f"{posting.title} {posting.company}")
    return tuple(skill for skill in profile.skills if _normalize_text(skill) not in haystack)


def _effort_estimate(missing_skill_count: int) -> str:
    if missing_skill_count == 0:
        return "low"
    if missing_skill_count == 1:
        return "medium"
    return "high"


def _interview_probability_pct(match_score: int, missing_skill_count: int) -> int:
    penalty = min(25, missing_skill_count * 8)
    return max(0, min(100, match_score - penalty))


def _match_rationale(
    *,
    posting: JobPosting,
    gated_recommendation: GatedRecommendation,
    match_score: MatchScore,
) -> str:
    passed_gates = [entry.gate for entry in gated_recommendation.gate_trace if entry.passed]
    breakdown = ", ".join(f"{key}={value}" for key, value in sorted(match_score.signal_breakdown.items()))
    gates = ", ".join(passed_gates) if passed_gates else "none"
    return (
        f"Role '{posting.title}' at {posting.company} scored {match_score.score}/100 "
        f"with signals [{breakdown}] and passed gates [{gates}]."
    )


def generate_explainability_note(
    profile: UserProfile,
    posting: JobPosting,
    match_score: MatchScore,
    gated_recommendation: GatedRecommendation,
) -> ExplainabilityNote:
    missing = _missing_skills(profile, posting)
    return ExplainabilityNote(
        match_rationale=_match_rationale(
            posting=posting,
            gated_recommendation=gated_recommendation,
            match_score=match_score,
        ),
        missing_skills=missing,
        interview_probability_pct=_interview_probability_pct(match_score.score, len(missing)),
        effort_estimate=_effort_estimate(len(missing)),
    )


def validate_explainability_note(note: ExplainabilityNote) -> None:
    if not note.match_rationale.strip():
        raise ExplainabilityQualityError(
            "EXPLAINABILITY_RATIONALE_REQUIRED",
            "Explainability note must include match rationale.",
        )
    if not 0 <= note.interview_probability_pct <= 100:
        raise ExplainabilityQualityError(
            "EXPLAINABILITY_INTERVIEW_PROBABILITY_INVALID",
            "Interview probability must be between 0 and 100.",
        )
    if note.effort_estimate not in VALID_EFFORT_ESTIMATES:
        raise ExplainabilityQualityError(
            "EXPLAINABILITY_EFFORT_INVALID",
            "Effort estimate must be low, medium, or high.",
        )


def build_explainable_recommendation(
    *,
    top_recommendation: TopRecommendation,
    match_score: MatchScore,
    gated_recommendation: GatedRecommendation,
    note: ExplainabilityNote,
    generated_at: datetime,
) -> ExplainableRecommendation:
    validate_explainability_note(note)
    return ExplainableRecommendation(
        job_posting_id=top_recommendation.job_posting_id,
        match_score=top_recommendation.match_score,
        profile_version=top_recommendation.profile_version,
        scoring_config_version=match_score.config_version,
        gate_config_version=top_recommendation.gate_config_version,
        policy_version=top_recommendation.policy_version,
        promoted=True,
        note=note,
        failure_code=None,
        failure_reason=None,
        generated_at=generated_at,
    )


def build_failed_explainable_recommendation(
    *,
    top_recommendation: TopRecommendation,
    match_score: MatchScore | None,
    code: str,
    reason: str,
    generated_at: datetime,
) -> ExplainableRecommendation:
    return ExplainableRecommendation(
        job_posting_id=top_recommendation.job_posting_id,
        match_score=top_recommendation.match_score,
        profile_version=top_recommendation.profile_version,
        scoring_config_version=match_score.config_version if match_score else "unknown",
        gate_config_version=top_recommendation.gate_config_version,
        policy_version=top_recommendation.policy_version,
        promoted=False,
        note=None,
        failure_code=code,
        failure_reason=reason,
        generated_at=generated_at,
    )
