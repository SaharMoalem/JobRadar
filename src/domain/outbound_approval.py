from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OutboundApproval:
    id: str
    artifact_id: str
    correlation_id: str
    approved_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class OutboundDelivery:
    id: str
    artifact_id: str
    approval_id: str
    channel: str
    correlation_id: str
    content_snapshot: str
    delivered_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class OutboundPolicyBlock:
    code: str
    message: str
    artifact_id: str | None
    correlation_id: str


class OutboundValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
