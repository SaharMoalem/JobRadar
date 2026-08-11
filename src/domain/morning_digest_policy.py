from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from src.domain.job_posting import JobPosting
from src.domain.lifecycle import JobLifecycleState, JobLifecycleTransition
from src.domain.morning_digest import DigestJobItem, MorningDigestConfig, MorningDigestValidationError
from src.domain.precision_policy import TopRecommendation


DIGEST_CHANGE_STATES = frozenset(
    {
        JobLifecycleState.NEW,
        JobLifecycleState.UPDATED,
        JobLifecycleState.EXPIRED,
    }
)
MAX_DIGEST_WINDOW_HOURS = 8760  # 365 days
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_digest_config(config: MorningDigestConfig) -> None:
    if not 0 <= config.digest_threshold <= 100:
        raise MorningDigestValidationError(
            "DIGEST_THRESHOLD_OUT_OF_RANGE",
            "Digest threshold must be between 0 and 100.",
        )
    if not 1 <= config.digest_window_hours <= MAX_DIGEST_WINDOW_HOURS:
        raise MorningDigestValidationError(
            "DIGEST_WINDOW_INVALID",
            f"Digest window hours must be between 1 and {MAX_DIGEST_WINDOW_HOURS}.",
        )
    if not 1 <= config.top_n <= 10:
        raise MorningDigestValidationError(
            "DIGEST_TOP_N_OUT_OF_RANGE",
            "Digest top_n must be between 1 and 10.",
        )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_role_summary(posting: JobPosting) -> str:
    return f"{posting.title} at {posting.company} ({posting.location})"


def build_deep_link(job_posting_id: str) -> str:
    return f"/job-postings/{job_posting_id}"


def default_run_context(*, now: datetime | None = None) -> str:
    current = ensure_utc(now or datetime.now(timezone.utc))
    return current.date().isoformat()


def resolve_digest_date(*, run_context: str, evaluated_at: datetime) -> str:
    if _ISO_DATE.fullmatch(run_context):
        return run_context
    return ensure_utc(evaluated_at).date().isoformat()


def window_start(*, window_hours: int, now: datetime) -> datetime:
    return ensure_utc(now) - timedelta(hours=window_hours)


def transitions_in_window(
    transitions: list[JobLifecycleTransition],
    *,
    window_start_at: datetime,
    window_end_at: datetime,
) -> list[JobLifecycleTransition]:
    """Return all transitions in the inclusive UTC window (any lifecycle state)."""
    start = ensure_utc(window_start_at)
    end = ensure_utc(window_end_at)
    selected: list[JobLifecycleTransition] = []
    for transition in transitions:
        at = ensure_utc(transition.transitioned_at)
        if start <= at <= end:
            selected.append(transition)
    return selected


def latest_change_transitions(
    transitions: list[JobLifecycleTransition],
) -> list[JobLifecycleTransition]:
    """
    Keep the latest in-window transition per posting (any state).
    Include only when that latest `to_state` is NEW/UPDATED/EXPIRED.
    Same-timestamp ties break by to_state value then job_posting_id.
    """
    ordered = sorted(
        transitions,
        key=lambda item: (
            ensure_utc(item.transitioned_at),
            item.to_state.value,
            item.job_posting_id,
        ),
        reverse=True,
    )
    selected: list[JobLifecycleTransition] = []
    seen: set[str] = set()
    for transition in ordered:
        if transition.job_posting_id in seen:
            continue
        seen.add(transition.job_posting_id)
        if transition.to_state in DIGEST_CHANGE_STATES:
            selected.append(transition)
    return selected


def bucket_transitions(
    transitions: list[JobLifecycleTransition],
) -> dict[JobLifecycleState, list[JobLifecycleTransition]]:
    buckets: dict[JobLifecycleState, list[JobLifecycleTransition]] = {
        JobLifecycleState.NEW: [],
        JobLifecycleState.UPDATED: [],
        JobLifecycleState.EXPIRED: [],
    }
    for transition in transitions:
        if transition.to_state in buckets:
            buckets[transition.to_state].append(transition)
    for state in buckets:
        buckets[state] = sorted(
            buckets[state],
            key=lambda item: (
                -ensure_utc(item.transitioned_at).timestamp(),
                item.to_state.value,
                item.job_posting_id,
            ),
        )
    return buckets


def qualifies_for_change_section(*, match_score: int | None, threshold: int) -> bool:
    return match_score is not None and match_score >= threshold


def select_top_recommendations(
    recommendations: list[TopRecommendation],
    *,
    top_n: int,
    available_posting_ids: set[str],
) -> tuple[list[TopRecommendation], int]:
    """
    Preserve precision list_top order; fill up to top_n with available postings.
    Returns (selected, skipped_missing_posting_count among inspected candidates).
    """
    selected: list[TopRecommendation] = []
    skipped_missing = 0
    for recommendation in recommendations:
        if len(selected) >= top_n:
            break
        if recommendation.job_posting_id not in available_posting_ids:
            skipped_missing += 1
            continue
        selected.append(recommendation)
    return selected, skipped_missing


def build_change_item(
    *,
    posting: JobPosting,
    match_score: int,
    lifecycle_state: JobLifecycleState,
    transitioned_at: datetime,
) -> DigestJobItem:
    return DigestJobItem(
        job_posting_id=posting.id,
        role_summary=build_role_summary(posting),
        match_score=match_score,
        deep_link=build_deep_link(posting.id),
        lifecycle_state=lifecycle_state.value,
        transitioned_at=ensure_utc(transitioned_at),
        rank=None,
    )


def build_top_item(
    *,
    posting: JobPosting,
    recommendation: TopRecommendation,
) -> DigestJobItem:
    return DigestJobItem(
        job_posting_id=posting.id,
        role_summary=build_role_summary(posting),
        match_score=recommendation.match_score,
        deep_link=build_deep_link(posting.id),
        lifecycle_state=posting.lifecycle_state.value,
        transitioned_at=None,
        rank=recommendation.rank,
    )
