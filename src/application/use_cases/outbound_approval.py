from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.domain.outbound_approval import (
    OutboundApproval,
    OutboundDelivery,
    OutboundPolicyBlock,
    OutboundValidationError,
)
from src.domain.outbound_approval_policy import require_outbound_approval, validate_artifact_for_approval
from src.ports.draft_artifact_port import DraftArtifactRepositoryPort
from src.ports.outbound_approval_port import (
    OutboundApprovalRepositoryPort,
    OutboundDeliveryPort,
    OutboundDeliveryRepositoryPort,
    OutboundTelemetryPort,
)


@dataclass(slots=True)
class ApproveOutboundUseCase:
    draft_repository: DraftArtifactRepositoryPort
    approval_repository: OutboundApprovalRepositoryPort
    telemetry: OutboundTelemetryPort

    def approve(
        self,
        artifact_id: str,
        *,
        correlation_id: str = "local",
    ) -> OutboundApproval:
        artifact = self.draft_repository.get(artifact_id)
        try:
            validate_artifact_for_approval(artifact)
        except OutboundValidationError as exc:
            self.telemetry.record_block(
                OutboundPolicyBlock(
                    code=exc.code,
                    message=str(exc),
                    artifact_id=artifact_id,
                    correlation_id=correlation_id,
                )
            )
            raise
        approval = OutboundApproval(
            id=f"approval-{uuid4().hex[:12]}",
            artifact_id=artifact_id,
            correlation_id=correlation_id,
        )
        saved = self.approval_repository.save_approval(approval)
        self.telemetry.record_approval(saved)
        return saved


@dataclass(slots=True)
class DeliverOutboundUseCase:
    draft_repository: DraftArtifactRepositoryPort
    approval_repository: OutboundApprovalRepositoryPort
    delivery_port: OutboundDeliveryPort
    delivery_repository: OutboundDeliveryRepositoryPort
    telemetry: OutboundTelemetryPort

    def deliver(
        self,
        artifact_id: str,
        *,
        channel: str = "manual_export",
        correlation_id: str = "local",
    ) -> OutboundDelivery:
        artifact = self.draft_repository.get(artifact_id)
        approval = self.approval_repository.get_latest_for_artifact(artifact_id)
        try:
            validated_artifact, validated_approval = require_outbound_approval(
                artifact=artifact,
                approval=approval,
            )
        except OutboundValidationError as exc:
            self.telemetry.record_block(
                OutboundPolicyBlock(
                    code=exc.code,
                    message=str(exc),
                    artifact_id=artifact_id,
                    correlation_id=correlation_id,
                )
            )
            raise
        delivery = self.delivery_port.deliver(
            artifact=validated_artifact,
            approval=validated_approval,
            channel=channel,
            correlation_id=correlation_id,
        )
        saved = self.delivery_repository.save_delivery(delivery)
        self.approval_repository.consume_latest_for_artifact(artifact_id)
        self.telemetry.record_delivery(saved)
        return saved

    def list_deliveries(self) -> list[OutboundDelivery]:
        return self.delivery_repository.list_deliveries()
