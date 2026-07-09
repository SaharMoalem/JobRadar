from __future__ import annotations

from dataclasses import dataclass

from src.application.discovery.execution_gate import gate_source_execution
from src.domain.career_source import CareerSource, CareerSourceStatus, ComplianceStatus
from src.domain.source_policy import SourceValidationError
from src.ports.career_source_port import CareerSourceRepositoryPort
from src.ports.compliance_check_port import ComplianceCheckPort


@dataclass(slots=True)
class SourceComplianceService:
    repository: CareerSourceRepositoryPort
    compliance_checker: ComplianceCheckPort

    def approve(self, source_id: str) -> CareerSource:
        source = self._get_source(source_id)
        if source.compliance_status == ComplianceStatus.APPROVED:
            return source

        check = self.compliance_checker.evaluate(source.base_url)
        if not check.passed:
            source.set_compliance(
                status=ComplianceStatus.REJECTED,
                reason=check.reason,
                robots_check_passed=False,
            )
            self.repository.update(source)
            raise SourceValidationError(
                "SOURCE_COMPLIANCE_CHECK_FAILED",
                f"Compliance check failed: {check.reason}",
            )

        source.set_compliance(
            status=ComplianceStatus.APPROVED,
            reason=check.reason,
            robots_check_passed=True,
        )
        return self.repository.update(source)

    def reject(self, source_id: str, *, reason: str = "manual_rejection") -> CareerSource:
        source = self._get_source(source_id)
        source.set_compliance(
            status=ComplianceStatus.REJECTED,
            reason=reason,
            robots_check_passed=False,
        )
        if source.status == CareerSourceStatus.ENABLED:
            source.set_status(CareerSourceStatus.DISABLED)
        return self.repository.update(source)

    def attempt_execution(self, source_id: str, *, correlation_id: str) -> CareerSource:
        source = self._get_source(source_id)
        gate_source_execution(source, correlation_id=correlation_id)
        return source

    def _get_source(self, source_id: str) -> CareerSource:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceValidationError("SOURCE_NOT_FOUND", "Career source not found.")
        return source
