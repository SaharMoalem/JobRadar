from datetime import datetime, timezone

import pytest

from src.domain.application_tracker import TrackedOpportunity, TrackerState
from src.domain.draft_artifact import DraftArtifactKind, DraftArtifactValidationError
from src.domain.draft_artifact_policy import generate_draft_content, validate_draft_context
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState


def _posting() -> JobPosting:
    return JobPosting(
        id="job-1",
        title="Backend Engineer",
        company="Acme",
        location="Tel Aviv",
        url="https://jobs.example.com/1",
        posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id="ext-1",
        plugin_id="generic",
        lifecycle_state=JobLifecycleState.ACTIVE,
        completeness=JobPostingCompleteness.COMPLETE,
    )


def test_validate_draft_context_requires_review_or_apply():
    with pytest.raises(DraftArtifactValidationError) as exc:
        validate_draft_context(
            posting=_posting(),
            tracked=TrackedOpportunity(job_posting_id="job-1", tracker_state=TrackerState.NEW),
        )
    assert exc.value.code == "DRAFT_TRACKER_CONTEXT_INVALID"


def test_generate_draft_content_marks_draft_and_references_role():
    content = generate_draft_content(
        kind=DraftArtifactKind.RECRUITER_MESSAGE,
        posting=_posting(),
        profile=None,
    )
    assert content.startswith("[DRAFT]")
    assert "Backend Engineer" in content
    assert "Acme" in content
