from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.lifecycle import JobLifecycleTransition, RetentionBatchResult
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.lifecycle_telemetry_port import LifecycleTelemetryPort


@dataclass(slots=True)
class JobLifecycleService:
    repository: JobPostingRepositoryPort
    telemetry: LifecycleTelemetryPort

    def finalize_source_crawl(
        self,
        source_id: str,
        seen_posting_ids: set[str],
        *,
        correlation_id: str,
    ) -> list[JobLifecycleTransition]:
        transitions = self.repository.expire_unseen_for_source(
            source_id,
            seen_posting_ids,
            correlation_id=correlation_id,
        )
        return transitions

    def apply_retention(
        self,
        *,
        correlation_id: str,
        evaluated_at: datetime | None = None,
    ) -> RetentionBatchResult:
        result = self.repository.apply_retention_policy(
            evaluated_at or datetime.now(timezone.utc),
            correlation_id=correlation_id,
        )
        if result.archived_count:
            self.telemetry.record_retention_batch(result)
        return result
