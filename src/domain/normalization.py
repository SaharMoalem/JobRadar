from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.job_posting import JobPosting


@dataclass(frozen=True, slots=True)
class NormalizationRejection:
    external_id: str
    career_source_id: str
    plugin_id: str
    reason: str
    missing_fields: tuple[str, ...] = ()
    raw_payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizationBatchResult:
    accepted: list[JobPosting]
    rejected: list[NormalizationRejection]

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)
