from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.dedup_policy import JobDuplicateLink
from src.domain.job_posting import JobPosting
from src.domain.lifecycle import JobLifecycleTransition, RetentionBatchResult
from src.domain.normalization import NormalizationRejection


class JobPostingRepositoryPort(Protocol):
    def save_posting(self, posting: JobPosting) -> JobPosting: ...

    def save_rejection(self, rejection: NormalizationRejection) -> NormalizationRejection: ...

    def list_complete(self) -> list[JobPosting]: ...

    def list_rejections(self) -> list[NormalizationRejection]: ...

    def list_duplicate_links(self) -> list[JobDuplicateLink]: ...

    def list_lifecycle_transitions(self, job_posting_id: str | None = None) -> list[JobLifecycleTransition]: ...

    def expire_unseen_for_source(
        self,
        source_id: str,
        seen_posting_ids: set[str],
        *,
        correlation_id: str,
    ) -> list[JobLifecycleTransition]: ...

    def apply_retention_policy(
        self,
        evaluated_at: datetime,
        *,
        correlation_id: str,
    ) -> RetentionBatchResult: ...
