from __future__ import annotations

from src.domain.immediate_alert import ImmediateAlertConfig, ImmediateAlertValidationError
from src.domain.job_posting import JobPosting
from src.domain.recommendation_gating import GatedRecommendation


def validate_alert_config(config: ImmediateAlertConfig) -> None:
    if not 0 <= config.alert_threshold <= 100:
        raise ImmediateAlertValidationError(
            "ALERT_THRESHOLD_OUT_OF_RANGE",
            "Alert threshold must be between 0 and 100.",
        )


def build_role_summary(posting: JobPosting) -> str:
    return f"{posting.title} at {posting.company} ({posting.location})"


def build_deep_link(job_posting_id: str) -> str:
    return f"/job-postings/{job_posting_id}"


def qualifies_for_alert(
    recommendation: GatedRecommendation,
    *,
    threshold: int,
) -> bool:
    return recommendation.actionable and recommendation.match_score >= threshold


def select_alert_candidates(
    recommendations: list[GatedRecommendation],
    *,
    threshold: int,
) -> list[GatedRecommendation]:
    """Return qualifying candidates with highest-score-wins dedup by job_posting_id."""
    selected: list[GatedRecommendation] = []
    seen: set[str] = set()
    for recommendation in sorted(
        recommendations,
        key=lambda item: (-item.match_score, item.job_posting_id),
    ):
        if not qualifies_for_alert(recommendation, threshold=threshold):
            continue
        if recommendation.job_posting_id in seen:
            continue
        seen.add(recommendation.job_posting_id)
        selected.append(recommendation)
    return selected
