from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CareerSourceStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ComplianceStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CareerSource:
    id: str
    name: str
    base_url: str
    plugin_id: str = "generic"
    status: CareerSourceStatus = CareerSourceStatus.DISABLED
    compliance_status: ComplianceStatus = ComplianceStatus.PENDING
    compliance_reason: str | None = None
    robots_check_passed: bool | None = None
    compliance_reviewed_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def set_status(self, status: CareerSourceStatus) -> None:
        self.status = status
        self.touch()

    def set_compliance(
        self,
        *,
        status: ComplianceStatus,
        reason: str | None,
        robots_check_passed: bool | None,
    ) -> None:
        self.compliance_status = status
        self.compliance_reason = reason
        self.robots_check_passed = robots_check_passed
        self.compliance_reviewed_at = _utc_now()
        self.touch()
