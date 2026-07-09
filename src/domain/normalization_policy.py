from __future__ import annotations

from datetime import datetime

from src.domain.job_posting import JobPosting, JobPostingCompleteness


REQUIRED_FIELDS = ("title", "company", "location", "url", "posted_at")


def find_missing_required_fields(
    *,
    title: str,
    company: str,
    location: str,
    url: str,
    posted_at: datetime | None,
) -> list[str]:
    missing: list[str] = []
    if not title.strip():
        missing.append("title")
    if not company.strip():
        missing.append("company")
    if not location.strip():
        missing.append("location")
    if not url.strip():
        missing.append("url")
    if posted_at is None:
        missing.append("posted_at")
    return missing


def apply_completeness(posting: JobPosting) -> JobPosting:
    missing = find_missing_required_fields(
        title=posting.title,
        company=posting.company,
        location=posting.location,
        url=posting.url,
        posted_at=posting.posted_at,
    )
    if missing:
        posting.completeness = JobPostingCompleteness.INCOMPLETE
        posting.rejection_reason = f"missing_required_fields:{','.join(missing)}"
    else:
        posting.completeness = JobPostingCompleteness.COMPLETE
        posting.rejection_reason = None
    return posting
