from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.job_posting import JobPosting
from src.domain.lifecycle import JobLifecycleState

RETENTION_DAYS = 180

_TRACKED_FIELDS = ("title", "company", "location", "url", "posted_at")


def has_material_change(before: JobPosting, after: JobPosting) -> bool:
    return any(getattr(before, field) != getattr(after, field) for field in _TRACKED_FIELDS)


def next_state_on_observation(
    *,
    existing: JobPosting | None,
    observed: JobPosting,
) -> tuple[JobLifecycleState, str]:
    if existing is None:
        return JobLifecycleState.NEW, "first_observed"
    if has_material_change(existing, observed):
        return JobLifecycleState.UPDATED, "material_change"
    return JobLifecycleState.ACTIVE, "reobserved"


def retention_deadline(expired_at: datetime, *, retention_days: int = RETENTION_DAYS) -> datetime:
    return expired_at + timedelta(days=retention_days)


def should_archive(
    expired_at: datetime | None,
    now: datetime,
    *,
    retention_days: int = RETENTION_DAYS,
) -> bool:
    if expired_at is None:
        return False
    return now >= retention_deadline(expired_at, retention_days=retention_days)
