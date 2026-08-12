from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.domain.immediate_alert import ImmediateAlert
    from src.domain.morning_digest import MorningDigest


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


NotificationKind = Literal["immediate_alert", "morning_digest"]


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    kind: NotificationKind
    correlation_id: str
    run_context: str
    alert: ImmediateAlert | None = None
    digest: MorningDigest | None = None

    @property
    def source_id(self) -> str:
        if self.kind == "immediate_alert" and self.alert is not None:
            return self.alert.id
        if self.kind == "morning_digest" and self.digest is not None:
            return self.digest.id
        raise NotificationValidationError(
            "NOTIFICATION_PAYLOAD_INVALID",
            "Notification payload is missing its source artifact.",
        )


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    id: str
    channel_id: str
    kind: NotificationKind
    source_id: str
    correlation_id: str
    run_context: str
    status: str
    detail: str
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class NotificationDeliveryBatchResult:
    deliveries: tuple[NotificationDelivery, ...]
    delivered_count: int
    failed_count: int
    skipped_missing_source_count: int
    correlation_id: str
    run_context: str
    kind: NotificationKind


@dataclass(frozen=True, slots=True)
class NotificationDeliveryFailure:
    code: str
    message: str
    correlation_id: str


class NotificationValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
