from __future__ import annotations

import json
import logging

from src.domain.outbound_approval import OutboundApproval, OutboundDelivery, OutboundPolicyBlock
from src.ports.outbound_approval_port import OutboundTelemetryPort

logger = logging.getLogger("jobradar.outbound")


class StructuredOutboundTelemetryAdapter(OutboundTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "outbound_approvals_total": 0,
            "outbound_deliveries_total": 0,
            "outbound_policy_blocks_total": 0,
        }

    def record_approval(self, approval: OutboundApproval) -> None:
        self._metrics["outbound_approvals_total"] += 1
        payload = {
            "event": "outbound_approval",
            "approval_id": approval.id,
            "artifact_id": approval.artifact_id,
            "correlation_id": approval.correlation_id,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_delivery(self, delivery: OutboundDelivery) -> None:
        self._metrics["outbound_deliveries_total"] += 1
        payload = {
            "event": "outbound_delivery",
            "delivery_id": delivery.id,
            "artifact_id": delivery.artifact_id,
            "approval_id": delivery.approval_id,
            "channel": delivery.channel,
            "correlation_id": delivery.correlation_id,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_block(self, block: OutboundPolicyBlock) -> None:
        self._metrics["outbound_policy_blocks_total"] += 1
        payload = {
            "event": "outbound_policy_block",
            "code": block.code,
            "message": block.message,
            "artifact_id": block.artifact_id,
            "correlation_id": block.correlation_id,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
