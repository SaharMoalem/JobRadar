from __future__ import annotations

import math
from datetime import datetime, timezone

from src.domain.job_posting import JobPosting
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.recommendation_gating import (
    GateTraceEntry,
    GatedRecommendation,
    GatingValidationError,
    RecommendationGateConfig,
)
from src.domain.user_profile import UserProfile

ACTIONABLE_LIFECYCLE_STATES = frozenset(
    {
        JobLifecycleState.NEW,
        JobLifecycleState.UPDATED,
        JobLifecycleState.ACTIVE,
    }
)


def validate_gate_config(config: RecommendationGateConfig) -> None:
    if not 60 <= config.global_threshold <= 95:
        raise GatingValidationError(
            "GATE_THRESHOLD_OUT_OF_RANGE",
            "Global threshold must be between 60 and 95.",
        )
    if not 0 <= config.skill_overlap_min_pct <= 100:
        raise GatingValidationError(
            "GATE_SKILL_OVERLAP_OUT_OF_RANGE",
            "Skill overlap minimum must be between 0 and 100.",
        )
    if config.recency_window_days < 1:
        raise GatingValidationError(
            "GATE_RECENCY_WINDOW_INVALID",
            "Recency window must be at least 1 day.",
        )


def _normalize_text(value: str) -> str:
    return value.casefold()


def _skill_overlap_ratio(profile: UserProfile, posting: JobPosting) -> float:
    if not profile.skills:
        return 0.0
    haystack = _normalize_text(f"{posting.title} {posting.company}")
    matched = sum(1 for skill in profile.skills if _normalize_text(skill) in haystack)
    return matched / len(profile.skills)


def _is_active_link(posting: JobPosting) -> bool:
    url = posting.url.strip()
    return url.startswith("http://") or url.startswith("https://")


def evaluate_gates(
    profile: UserProfile,
    posting: JobPosting,
    match_score: MatchScore,
    *,
    config: RecommendationGateConfig | None = None,
    now: datetime | None = None,
) -> GatedRecommendation:
    gate_config = config or RecommendationGateConfig()
    validate_gate_config(gate_config)
    evaluated_at = now or datetime.now(timezone.utc)
    trace: list[GateTraceEntry] = []

    threshold_passed = match_score.score >= gate_config.global_threshold
    trace.append(
        GateTraceEntry(
            gate="threshold",
            passed=threshold_passed,
            message=(
                f"Match score {match_score.score} meets threshold {gate_config.global_threshold}."
                if threshold_passed
                else f"Match score {match_score.score} below threshold {gate_config.global_threshold}."
            ),
        )
    )

    if gate_config.enforce_seniority:
        seniority = _normalize_text(profile.target_seniority)
        haystack = _normalize_text(posting.title)
        seniority_passed = bool(seniority) and seniority in haystack
        trace.append(
            GateTraceEntry(
                gate="seniority",
                passed=seniority_passed,
                message=(
                    f"Title contains target seniority '{profile.target_seniority}'."
                    if seniority_passed
                    else f"Title does not contain target seniority '{profile.target_seniority}'."
                ),
            )
        )

    if gate_config.enforce_skill_overlap:
        overlap_pct = math.floor(_skill_overlap_ratio(profile, posting) * 100)
        overlap_passed = overlap_pct >= gate_config.skill_overlap_min_pct
        trace.append(
            GateTraceEntry(
                gate="skill_overlap",
                passed=overlap_passed,
                message=(
                    f"Skill overlap {overlap_pct}% meets minimum {gate_config.skill_overlap_min_pct}%."
                    if overlap_passed
                    else f"Skill overlap {overlap_pct}% below minimum {gate_config.skill_overlap_min_pct}%."
                ),
            )
        )

    if gate_config.enforce_language and profile.preferred_languages:
        haystack = _normalize_text(f"{posting.title} {posting.location}")
        language_passed = any(
            _normalize_text(language) in haystack for language in profile.preferred_languages
        )
        trace.append(
            GateTraceEntry(
                gate="language",
                passed=language_passed,
                message=(
                    "Posting matches a preferred language."
                    if language_passed
                    else "Posting does not match any preferred language."
                ),
            )
        )

    if gate_config.enforce_region:
        location = _normalize_text(posting.location)
        region_passed = any(
            _normalize_text(preferred) in location for preferred in profile.preferred_locations
        )
        trace.append(
            GateTraceEntry(
                gate="region",
                passed=region_passed,
                message=(
                    "Posting location matches a preferred region."
                    if region_passed
                    else "Posting location does not match any preferred region."
                ),
            )
        )

    if gate_config.enforce_recency:
        recency_passed = False
        if posting.posted_at is not None:
            posted_at = posting.posted_at
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            age_days = (evaluated_at - posted_at).days
            recency_passed = age_days <= gate_config.recency_window_days
        trace.append(
            GateTraceEntry(
                gate="recency",
                passed=recency_passed,
                message=(
                    f"Posting is within {gate_config.recency_window_days} day recency window."
                    if recency_passed
                    else f"Posting is outside {gate_config.recency_window_days} day recency window."
                ),
            )
        )

    if gate_config.enforce_active_link:
        active_link_passed = (
            posting.lifecycle_state in ACTIONABLE_LIFECYCLE_STATES and _is_active_link(posting)
        )
        trace.append(
            GateTraceEntry(
                gate="active_link",
                passed=active_link_passed,
                message=(
                    "Posting has an active lifecycle state and valid URL."
                    if active_link_passed
                    else "Posting is not eligible as an active link."
                ),
            )
        )

    actionable = all(entry.passed for entry in trace)
    return GatedRecommendation(
        job_posting_id=posting.id,
        match_score=match_score.score,
        profile_version=match_score.profile_version,
        config_version=gate_config.config_version,
        actionable=actionable,
        gate_trace=tuple(trace),
        evaluated_at=evaluated_at,
    )
