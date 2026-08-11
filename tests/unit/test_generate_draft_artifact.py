from datetime import datetime, timezone

import pytest

from src.adapters.drafts.rule_based_draft_artifact_generator import (
    RuleBasedDraftArtifactGeneratorAdapter,
)
from src.adapters.observability.structured_draft_artifact_telemetry_adapter import (
    StructuredDraftArtifactTelemetryAdapter,
)
from src.adapters.persistence.in_memory_application_tracker_adapter import (
    InMemoryApplicationTrackerAdapter,
)
from src.adapters.persistence.in_memory_draft_artifact_adapter import InMemoryDraftArtifactAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_user_profile_adapter import InMemoryUserProfileAdapter
from src.application.use_cases.application_tracker import ApplicationTrackerUseCase
from src.application.use_cases.generate_draft_artifact import GenerateDraftArtifactUseCase
from src.domain.application_tracker import TrackerState
from src.domain.draft_artifact import DraftArtifactKind, DraftArtifactValidationError
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.user_profile import UserProfile


class FailingDraftGenerator:
    def generate(self, *, kind, posting, profile):
        return "   "


class ExplodingDraftGenerator:
    def generate(self, *, kind, posting, profile):
        raise RuntimeError("boom")


def _seed() -> tuple[GenerateDraftArtifactUseCase, ApplicationTrackerUseCase, str, StructuredDraftArtifactTelemetryAdapter]:
    postings = InMemoryJobPostingAdapter()
    postings.save_posting(
        JobPosting(
            id="job-1",
            title="Backend Engineer",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/draft-1",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="ext-1",
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.ACTIVE,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    posting_id = postings.list_complete()[0].id
    trackers = InMemoryApplicationTrackerAdapter()
    profiles = InMemoryUserProfileAdapter()
    profiles.save_profile(
        UserProfile(
            skills=("python",),
            preferred_locations=("Tel Aviv",),
            preferred_languages=(),
            target_seniority="senior",
        )
    )
    drafts = InMemoryDraftArtifactAdapter()
    telemetry = StructuredDraftArtifactTelemetryAdapter()
    tracker_use_case = ApplicationTrackerUseCase(
        tracker_repository=trackers,
        job_posting_repository=postings,
    )
    draft_use_case = GenerateDraftArtifactUseCase(
        job_posting_repository=postings,
        tracker_repository=trackers,
        profile_repository=profiles,
        draft_repository=drafts,
        generator=RuleBasedDraftArtifactGeneratorAdapter(),
        telemetry=telemetry,
    )
    return draft_use_case, tracker_use_case, posting_id, telemetry


def test_generate_draft_stores_timestamp_and_source_reference():
    draft_use_case, tracker_use_case, posting_id, _ = _seed()
    tracker_use_case.bookmark(posting_id)
    tracker_use_case.transition(posting_id, to_state=TrackerState.REVIEW)

    artifact = draft_use_case.generate(
        job_posting_id=posting_id,
        kind=DraftArtifactKind.CV_IMPROVEMENT,
        correlation_id="draft-1",
    )

    assert artifact.status.value == "draft"
    assert artifact.is_latest is True
    assert "Backend Engineer" in artifact.source_reference
    assert artifact.created_at.tzinfo is not None


def test_multiple_generations_keep_history_and_mark_latest():
    draft_use_case, tracker_use_case, posting_id, _ = _seed()
    tracker_use_case.bookmark(posting_id)
    tracker_use_case.transition(posting_id, to_state=TrackerState.REVIEW)
    tracker_use_case.transition(posting_id, to_state=TrackerState.APPLY)

    first = draft_use_case.generate(
        job_posting_id=posting_id,
        kind=DraftArtifactKind.INTERVIEW_PREP,
        correlation_id="d1",
    )
    second = draft_use_case.generate(
        job_posting_id=posting_id,
        kind=DraftArtifactKind.INTERVIEW_PREP,
        correlation_id="d2",
    )
    history = draft_use_case.list_for_posting(posting_id, kind=DraftArtifactKind.INTERVIEW_PREP)
    latest = draft_use_case.list_latest_for_posting(posting_id)

    assert len(history) == 2
    assert history[0].id == first.id
    assert history[0].is_latest is False
    assert history[1].id == second.id
    assert history[1].is_latest is True
    assert [item.id for item in latest] == [second.id]


def test_failed_generation_preserves_existing_artifacts_and_logs():
    draft_use_case, tracker_use_case, posting_id, telemetry = _seed()
    tracker_use_case.bookmark(posting_id)
    tracker_use_case.transition(posting_id, to_state=TrackerState.REVIEW)
    kept = draft_use_case.generate(
        job_posting_id=posting_id,
        kind=DraftArtifactKind.RECRUITER_MESSAGE,
        correlation_id="ok",
    )
    draft_use_case.generator = FailingDraftGenerator()

    with pytest.raises(DraftArtifactValidationError) as exc:
        draft_use_case.generate(
            job_posting_id=posting_id,
            kind=DraftArtifactKind.RECRUITER_MESSAGE,
            correlation_id="fail",
        )

    assert exc.value.code == "DRAFT_GENERATION_FAILED"
    assert [item.id for item in draft_use_case.list_for_posting(posting_id)] == [kept.id]
    assert telemetry.snapshot_metrics()["draft_generation_failures_total"] == 1
    assert draft_use_case.list_for_posting(posting_id)[0].is_latest is True


def test_unexpected_generator_error_is_typed_and_logged():
    draft_use_case, tracker_use_case, posting_id, telemetry = _seed()
    tracker_use_case.bookmark(posting_id)
    tracker_use_case.transition(posting_id, to_state=TrackerState.REVIEW)
    draft_use_case.generator = ExplodingDraftGenerator()

    with pytest.raises(DraftArtifactValidationError) as exc:
        draft_use_case.generate(
            job_posting_id=posting_id,
            kind=DraftArtifactKind.RECRUITER_MESSAGE,
            correlation_id="explode",
        )

    assert exc.value.code == "DRAFT_GENERATION_FAILED"
    assert telemetry.snapshot_metrics()["draft_generation_failures_total"] == 1
    assert draft_use_case.list_for_posting(posting_id) == []


def test_missing_posting_and_tracker_errors():
    draft_use_case, tracker_use_case, posting_id, telemetry = _seed()

    with pytest.raises(DraftArtifactValidationError) as missing_posting:
        draft_use_case.generate(
            job_posting_id="missing-job",
            kind=DraftArtifactKind.RECRUITER_MESSAGE,
        )
    assert missing_posting.value.code == "DRAFT_JOB_POSTING_NOT_FOUND"

    with pytest.raises(DraftArtifactValidationError) as missing_tracker:
        draft_use_case.generate(
            job_posting_id=posting_id,
            kind=DraftArtifactKind.RECRUITER_MESSAGE,
        )
    assert missing_tracker.value.code == "DRAFT_TRACKER_NOT_FOUND"
    assert telemetry.snapshot_metrics()["draft_generation_failures_total"] == 2
