from __future__ import annotations

from uuid import uuid4

from src.domain.draft_artifact import DraftArtifact
from src.domain.outbound_approval import OutboundApproval, OutboundDelivery
from src.ports.outbound_approval_port import (
    OutboundApprovalRepositoryPort,
    OutboundDeliveryPort,
    OutboundDeliveryRepositoryPort,
)


class InMemoryOutboundApprovalAdapter(OutboundApprovalRepositoryPort):
    def __init__(self) -> None:
        self._approvals: dict[str, OutboundApproval] = {}
        self._latest_by_artifact: dict[str, str] = {}

    def save_approval(self, approval: OutboundApproval) -> OutboundApproval:
        self._approvals[approval.id] = approval
        self._latest_by_artifact[approval.artifact_id] = approval.id
        return approval

    def get_latest_for_artifact(self, artifact_id: str) -> OutboundApproval | None:
        approval_id = self._latest_by_artifact.get(artifact_id)
        if approval_id is None:
            return None
        return self._approvals.get(approval_id)

    def consume_latest_for_artifact(self, artifact_id: str) -> OutboundApproval | None:
        approval_id = self._latest_by_artifact.pop(artifact_id, None)
        if approval_id is None:
            return None
        return self._approvals.get(approval_id)

    def list_approvals(self) -> list[OutboundApproval]:
        return sorted(self._approvals.values(), key=lambda item: item.approved_at)


class InMemoryOutboundDeliveryAdapter(OutboundDeliveryRepositoryPort):
    def __init__(self) -> None:
        self._deliveries: list[OutboundDelivery] = []

    def save_delivery(self, delivery: OutboundDelivery) -> OutboundDelivery:
        self._deliveries.append(delivery)
        return delivery

    def list_deliveries(self) -> list[OutboundDelivery]:
        return sorted(self._deliveries, key=lambda item: item.delivered_at)


class RecordingOutboundDeliveryAdapter(OutboundDeliveryPort):
    """Local-only outbound adapter — builds a delivery record, never auto-sends externally."""

    def deliver(
        self,
        *,
        artifact: DraftArtifact,
        approval: OutboundApproval,
        channel: str,
        correlation_id: str,
    ) -> OutboundDelivery:
        return OutboundDelivery(
            id=f"outbound-{uuid4().hex[:12]}",
            artifact_id=artifact.id,
            approval_id=approval.id,
            channel=channel,
            correlation_id=correlation_id,
            content_snapshot=artifact.content,
        )
