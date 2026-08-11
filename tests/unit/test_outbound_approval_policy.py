import pytest

from src.domain.draft_artifact import DraftArtifact, DraftArtifactKind, DraftArtifactStatus
from src.domain.outbound_approval import OutboundApproval, OutboundValidationError
from src.domain.outbound_approval_policy import require_outbound_approval, validate_artifact_for_approval


def _artifact(*, artifact_id: str = "draft-1") -> DraftArtifact:
    return DraftArtifact(
        id=artifact_id,
        job_posting_id="job-1",
        kind=DraftArtifactKind.RECRUITER_MESSAGE,
        content="[DRAFT] hello",
        source_reference="Backend @ Acme",
        status=DraftArtifactStatus.DRAFT,
    )


def test_require_approval_blocks_without_approval():
    with pytest.raises(OutboundValidationError) as exc:
        require_outbound_approval(artifact=_artifact(), approval=None)
    assert exc.value.code == "OUTBOUND_APPROVAL_REQUIRED"


def test_require_approval_passes_with_matching_approval():
    artifact = _artifact()
    approval = OutboundApproval(id="approval-1", artifact_id=artifact.id, correlation_id="c1")
    validated_artifact, validated_approval = require_outbound_approval(
        artifact=artifact,
        approval=approval,
    )
    assert validated_artifact.id == artifact.id
    assert validated_approval.id == approval.id


def test_validate_artifact_for_approval_requires_existing_draft():
    with pytest.raises(OutboundValidationError) as exc:
        validate_artifact_for_approval(None)
    assert exc.value.code == "OUTBOUND_ARTIFACT_NOT_FOUND"
