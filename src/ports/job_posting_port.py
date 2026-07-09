from __future__ import annotations

from typing import Protocol

from src.domain.job_posting import JobPosting
from src.domain.normalization import NormalizationRejection


class JobPostingRepositoryPort(Protocol):
    def save_posting(self, posting: JobPosting) -> JobPosting: ...

    def save_rejection(self, rejection: NormalizationRejection) -> NormalizationRejection: ...

    def list_complete(self) -> list[JobPosting]: ...

    def list_rejections(self) -> list[NormalizationRejection]: ...
