from __future__ import annotations

from typing import Protocol

from src.domain.draft_artifact import DraftArtifact
from src.domain.outbound_approval import OutboundApproval, OutboundDelivery, OutboundPolicyBlock


class OutboundApprovalRepositoryPort(Protocol):
    def save_approval(self, approval: OutboundApproval) -> OutboundApproval: ...

    def get_latest_for_artifact(self, artifact_id: str) -> OutboundApproval | None: ...

    def consume_latest_for_artifact(self, artifact_id: str) -> OutboundApproval | None: ...

    def list_approvals(self) -> list[OutboundApproval]: ...


class OutboundDeliveryRepositoryPort(Protocol):
    def save_delivery(self, delivery: OutboundDelivery) -> OutboundDelivery: ...

    def list_deliveries(self) -> list[OutboundDelivery]: ...


class OutboundDeliveryPort(Protocol):
    def deliver(
        self,
        *,
        artifact: DraftArtifact,
        approval: OutboundApproval,
        channel: str,
        correlation_id: str,
    ) -> OutboundDelivery: ...


class OutboundTelemetryPort(Protocol):
    def record_approval(self, approval: OutboundApproval) -> None: ...

    def record_delivery(self, delivery: OutboundDelivery) -> None: ...

    def record_block(self, block: OutboundPolicyBlock) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
