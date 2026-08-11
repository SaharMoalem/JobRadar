from datetime import datetime, timezone

import pytest

from src.adapters.observability.structured_outbound_telemetry_adapter import (
    StructuredOutboundTelemetryAdapter,
)
from src.adapters.persistence.in_memory_application_tracker_adapter import (
    InMemoryApplicationTrackerAdapter,
)
from src.adapters.persistence.in_memory_draft_artifact_adapter import InMemoryDraftArtifactAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_outbound_adapter import (
    InMemoryOutboundApprovalAdapter,
    InMemoryOutboundDeliveryAdapter,
    RecordingOutboundDeliveryAdapter,
)
from src.adapters.persistence.in_memory_user_profile_adapter import InMemoryUserProfileAdapter
from src.adapters.drafts.rule_based_draft_artifact_generator import (
    RuleBasedDraftArtifactGeneratorAdapter,
)
from src.adapters.observability.structured_draft_artifact_telemetry_adapter import (
    StructuredDraftArtifactTelemetryAdapter,
)
from src.application.use_cases.application_tracker import ApplicationTrackerUseCase
from src.application.use_cases.generate_draft_artifact import GenerateDraftArtifactUseCase
from src.application.use_cases.outbound_approval import ApproveOutboundUseCase, DeliverOutboundUseCase
from src.domain.application_tracker import TrackerState
from src.domain.draft_artifact import DraftArtifactKind
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.outbound_approval import OutboundValidationError


def _seed_draft() -> tuple[str, ApproveOutboundUseCase, DeliverOutboundUseCase, StructuredOutboundTelemetryAdapter]:
    postings = InMemoryJobPostingAdapter()
    postings.save_posting(
        JobPosting(
            id="job-1",
            title="Backend Engineer",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/out-1",
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
    drafts = InMemoryDraftArtifactAdapter()
    approvals = InMemoryOutboundApprovalAdapter()
    deliveries = InMemoryOutboundDeliveryAdapter()
    outbound_telemetry = StructuredOutboundTelemetryAdapter()
    tracker = ApplicationTrackerUseCase(tracker_repository=trackers, job_posting_repository=postings)
    draft_service = GenerateDraftArtifactUseCase(
        job_posting_repository=postings,
        tracker_repository=trackers,
        profile_repository=InMemoryUserProfileAdapter(),
        draft_repository=drafts,
        generator=RuleBasedDraftArtifactGeneratorAdapter(),
        telemetry=StructuredDraftArtifactTelemetryAdapter(),
    )
    tracker.bookmark(posting_id)
    tracker.transition(posting_id, to_state=TrackerState.REVIEW)
    artifact = draft_service.generate(
        job_posting_id=posting_id,
        kind=DraftArtifactKind.RECRUITER_MESSAGE,
        correlation_id="draft-out",
    )
    approve = ApproveOutboundUseCase(
        draft_repository=drafts,
        approval_repository=approvals,
        telemetry=outbound_telemetry,
    )
    deliver = DeliverOutboundUseCase(
        draft_repository=drafts,
        approval_repository=approvals,
        delivery_port=RecordingOutboundDeliveryAdapter(),
        delivery_repository=deliveries,
        telemetry=outbound_telemetry,
    )
    return artifact.id, approve, deliver, outbound_telemetry


def test_deliver_without_approval_is_blocked_and_logged():
    artifact_id, _, deliver, telemetry = _seed_draft()
    with pytest.raises(OutboundValidationError) as exc:
        deliver.deliver(artifact_id, correlation_id="block-1")
    assert exc.value.code == "OUTBOUND_APPROVAL_REQUIRED"
    assert telemetry.snapshot_metrics()["outbound_policy_blocks_total"] == 1
    assert deliver.list_deliveries() == []


def test_approve_then_deliver_succeeds():
    artifact_id, approve, deliver, telemetry = _seed_draft()
    approval = approve.approve(artifact_id, correlation_id="approve-1")
    delivery = deliver.deliver(artifact_id, channel="manual_export", correlation_id="deliver-1")
    assert delivery.approval_id == approval.id
    assert delivery.artifact_id == artifact_id
    assert len(deliver.list_deliveries()) == 1
    assert telemetry.snapshot_metrics()["outbound_approvals_total"] == 1
    assert telemetry.snapshot_metrics()["outbound_deliveries_total"] == 1


def test_approval_is_consumed_after_deliver():
    artifact_id, approve, deliver, telemetry = _seed_draft()
    approve.approve(artifact_id, correlation_id="approve-once")
    deliver.deliver(artifact_id, correlation_id="deliver-once")

    with pytest.raises(OutboundValidationError) as exc:
        deliver.deliver(artifact_id, correlation_id="deliver-again")

    assert exc.value.code == "OUTBOUND_APPROVAL_REQUIRED"
    assert len(deliver.list_deliveries()) == 1
    assert telemetry.snapshot_metrics()["outbound_policy_blocks_total"] == 1


def test_approve_missing_artifact_is_blocked():
    _, approve, _, telemetry = _seed_draft()
    with pytest.raises(OutboundValidationError) as exc:
        approve.approve("missing-draft", correlation_id="missing-approve")
    assert exc.value.code == "OUTBOUND_ARTIFACT_NOT_FOUND"
    assert telemetry.snapshot_metrics()["outbound_policy_blocks_total"] == 1
