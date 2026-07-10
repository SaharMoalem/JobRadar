from __future__ import annotations

from datetime import datetime, timezone

from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScoringConfig, MatchScore, ScoringValidationError
from src.domain.user_profile import UserProfile

SCORABLE_LIFECYCLE_STATES = frozenset(
    {
        JobLifecycleState.NEW,
        JobLifecycleState.UPDATED,
        JobLifecycleState.ACTIVE,
    }
)


def validate_profile_for_scoring(profile: UserProfile) -> None:
    if not profile.skills:
        raise ScoringValidationError("PROFILE_SKILLS_REQUIRED", "User profile must include at least one skill.")
    if not profile.preferred_locations:
        raise ScoringValidationError(
            "PROFILE_LOCATIONS_REQUIRED",
            "User profile must include at least one preferred location.",
        )
    if not profile.target_seniority.strip():
        raise ScoringValidationError(
            "PROFILE_SENIORITY_REQUIRED",
            "User profile must include a target seniority.",
        )


def is_scorable_posting(posting: JobPosting) -> bool:
    return (
        posting.completeness == JobPostingCompleteness.COMPLETE
        and posting.lifecycle_state in SCORABLE_LIFECYCLE_STATES
    )


def _normalize_text(value: str) -> str:
    return value.casefold()


def _skill_overlap_points(profile: UserProfile, posting: JobPosting, *, weight: int) -> int:
    haystack = _normalize_text(f"{posting.title} {posting.company}")
    matched = sum(1 for skill in profile.skills if _normalize_text(skill) in haystack)
    if not profile.skills:
        return 0
    ratio = matched / len(profile.skills)
    return round(weight * ratio)


def _location_points(profile: UserProfile, posting: JobPosting, *, weight: int) -> int:
    location = _normalize_text(posting.location)
    if any(_normalize_text(preferred) in location for preferred in profile.preferred_locations):
        return weight
    return 0


def _language_points(profile: UserProfile, posting: JobPosting, *, weight: int) -> int:
    if not profile.preferred_languages:
        return 0
    haystack = _normalize_text(f"{posting.title} {posting.location}")
    if any(_normalize_text(language) in haystack for language in profile.preferred_languages):
        return weight
    return 0


def _recency_points(
    posting: JobPosting,
    *,
    weight: int,
    recency_window_days: int,
    now: datetime,
) -> int:
    if posting.posted_at is None:
        return 0
    posted_at = posting.posted_at
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    age_days = (now - posted_at).days
    if age_days <= recency_window_days:
        return weight
    return 0


def compute_match_score(
    profile: UserProfile,
    posting: JobPosting,
    *,
    config: MatchScoringConfig | None = None,
    now: datetime | None = None,
) -> MatchScore:
    validate_profile_for_scoring(profile)
    if not is_scorable_posting(posting):
        raise ScoringValidationError(
            "POSTING_NOT_SCORABLE",
            "Job posting is not eligible for match scoring.",
        )

    scoring_config = config or MatchScoringConfig()
    evaluated_at = now or datetime.now(timezone.utc)
    breakdown = {
        "skills": _skill_overlap_points(profile, posting, weight=scoring_config.skill_weight),
        "location": _location_points(profile, posting, weight=scoring_config.location_weight),
        "language": _language_points(profile, posting, weight=scoring_config.language_weight),
        "recency": _recency_points(
            posting,
            weight=scoring_config.recency_weight,
            recency_window_days=scoring_config.recency_window_days,
            now=evaluated_at,
        ),
    }
    total = min(100, max(0, sum(breakdown.values())))
    return MatchScore(
        job_posting_id=posting.id,
        score=total,
        profile_version=profile.profile_version,
        config_version=scoring_config.config_version,
        signal_breakdown=breakdown,
        computed_at=evaluated_at,
    )
