from __future__ import annotations

from src.domain.application_tracker import TrackerState, TrackedOpportunity
from src.domain.draft_artifact import DraftArtifactKind, DraftArtifactValidationError
from src.domain.job_posting import JobPosting
from src.domain.user_profile import UserProfile

ALLOWED_TRACKER_STATES_FOR_DRAFTS = frozenset({TrackerState.REVIEW, TrackerState.APPLY})


def validate_draft_context(
    *,
    posting: JobPosting | None,
    tracked: TrackedOpportunity | None,
) -> None:
    if posting is None:
        raise DraftArtifactValidationError(
            "DRAFT_JOB_POSTING_NOT_FOUND",
            "Job posting was not found.",
        )
    if tracked is None:
        raise DraftArtifactValidationError(
            "DRAFT_TRACKER_NOT_FOUND",
            "Opportunity must be tracked before draft generation.",
        )
    if tracked.tracker_state not in ALLOWED_TRACKER_STATES_FOR_DRAFTS:
        raise DraftArtifactValidationError(
            "DRAFT_TRACKER_CONTEXT_INVALID",
            "Draft generation requires tracker state 'review' or 'apply'.",
        )


def build_source_reference(posting: JobPosting) -> str:
    return f"{posting.title} @ {posting.company} ({posting.url})"


def generate_draft_content(
    *,
    kind: DraftArtifactKind,
    posting: JobPosting,
    profile: UserProfile | None = None,
) -> str:
    skills = ", ".join(profile.skills) if profile and profile.skills else "your relevant skills"
    if kind == DraftArtifactKind.RECRUITER_MESSAGE:
        return (
            f"[DRAFT] Hello — I'm interested in the {posting.title} role at {posting.company}. "
            f"I can contribute with {skills}. I'd welcome a conversation about the opportunity."
        )
    if kind == DraftArtifactKind.CV_IMPROVEMENT:
        return (
            f"[DRAFT] For {posting.title} at {posting.company}, emphasize {skills}, "
            f"align location experience with {posting.location}, and quantify recent impact."
        )
    if kind == DraftArtifactKind.INTERVIEW_PREP:
        return (
            f"[DRAFT] Interview prep for {posting.title} at {posting.company}: "
            f"prepare stories that demonstrate {skills}, questions about the team, "
            f"and how you would succeed in {posting.location}."
        )
    raise DraftArtifactValidationError(
        "DRAFT_KIND_INVALID",
        f"Unsupported draft artifact kind: {kind}",
    )
