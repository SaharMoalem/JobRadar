from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.domain.career_source import CareerSource, CareerSourceStatus, ComplianceStatus
from src.domain.compliance_policy import require_compliance_approved
from src.domain.source_policy import (
    SourcePolicyConfig,
    SourceValidationError,
    enforce_enable_limit,
    validate_source_fields,
)
from src.ports.career_source_port import CareerSourceRepositoryPort


@dataclass(slots=True)
class CareerSourceService:
    repository: CareerSourceRepositoryPort
    config: SourcePolicyConfig

    def create(self, name: str, base_url: str, *, plugin_id: str = "generic") -> CareerSource:
        validate_source_fields(name, base_url)
        source = CareerSource(
            id=str(uuid4()),
            name=name.strip(),
            base_url=base_url.strip(),
            plugin_id=plugin_id.strip() or "generic",
        )
        return self.repository.create(source)

    def update(
        self,
        source_id: str,
        name: str,
        base_url: str,
        *,
        plugin_id: str | None = None,
    ) -> CareerSource:
        validate_source_fields(name, base_url)
        source = self.repository.get(source_id)
        if source is None:
            raise SourceValidationError("SOURCE_NOT_FOUND", "Career source not found.")
        normalized_url = base_url.strip()
        if normalized_url != source.base_url and source.compliance_status != ComplianceStatus.PENDING:
            source.set_compliance(
                status=ComplianceStatus.PENDING,
                reason="base_url_changed",
                robots_check_passed=None,
            )
            if source.status == CareerSourceStatus.ENABLED:
                source.set_status(CareerSourceStatus.DISABLED)
        if plugin_id is not None:
            source.plugin_id = plugin_id.strip() or "generic"
        source.name = name.strip()
        source.base_url = normalized_url
        source.touch()
        return self.repository.update(source)

    def enable(self, source_id: str) -> CareerSource:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceValidationError("SOURCE_NOT_FOUND", "Career source not found.")
        require_compliance_approved(source)
        enforce_enable_limit(
            current_enabled_count=self.repository.count_enabled(),
            source=source,
            config=self.config,
        )
        source.set_status(CareerSourceStatus.ENABLED)
        return self.repository.update(source)

    def disable(self, source_id: str) -> CareerSource:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceValidationError("SOURCE_NOT_FOUND", "Career source not found.")
        source.set_status(CareerSourceStatus.DISABLED)
        return self.repository.update(source)

    def list_all(self) -> list[CareerSource]:
        return self.repository.list_all()
