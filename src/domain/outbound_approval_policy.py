from __future__ import annotations

from src.domain.draft_artifact import DraftArtifact, DraftArtifactStatus
from src.domain.outbound_approval import OutboundApproval, OutboundValidationError


def validate_artifact_for_approval(artifact: DraftArtifact | None) -> DraftArtifact:
    if artifact is None:
        raise OutboundValidationError(
            "OUTBOUND_ARTIFACT_NOT_FOUND",
            "Draft artifact was not found.",
        )
    if artifact.status != DraftArtifactStatus.DRAFT:
        raise OutboundValidationError(
            "OUTBOUND_ARTIFACT_NOT_DRAFT",
            "Only draft artifacts can be approved for outbound use.",
        )
    return artifact


def require_outbound_approval(
    *,
    artifact: DraftArtifact | None,
    approval: OutboundApproval | None,
) -> tuple[DraftArtifact, OutboundApproval]:
    validated = validate_artifact_for_approval(artifact)
    if approval is None:
        raise OutboundValidationError(
            "OUTBOUND_APPROVAL_REQUIRED",
            "Explicit approval is required before outbound delivery.",
        )
    if approval.artifact_id != validated.id:
        raise OutboundValidationError(
            "OUTBOUND_APPROVAL_MISMATCH",
            "Approval does not match the requested draft artifact.",
        )
    return validated, approval
