from __future__ import annotations

from src.domain.career_source import CareerSource, ComplianceStatus


def require_compliance_approved(source: CareerSource) -> None:
    from src.domain.source_policy import SourceValidationError

    if source.compliance_status != ComplianceStatus.APPROVED:
        raise SourceValidationError(
            "SOURCE_COMPLIANCE_NOT_APPROVED",
            "Career source must pass manual compliance approval before it can run.",
        )


def require_runnable(source: CareerSource) -> None:
    from src.domain.career_source import CareerSourceStatus
    from src.domain.source_policy import SourceValidationError

    require_compliance_approved(source)
    if source.status != CareerSourceStatus.ENABLED:
        raise SourceValidationError(
            "SOURCE_NOT_ENABLED",
            "Career source must be enabled before execution.",
        )
