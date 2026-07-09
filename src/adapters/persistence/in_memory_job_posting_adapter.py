from __future__ import annotations

from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.normalization import NormalizationRejection
from src.ports.job_posting_port import JobPostingRepositoryPort


class InMemoryJobPostingAdapter(JobPostingRepositoryPort):
    def __init__(self) -> None:
        self._postings: dict[str, JobPosting] = {}
        self._rejections: list[NormalizationRejection] = []

    def save_posting(self, posting: JobPosting) -> JobPosting:
        self._postings[posting.id] = posting
        return posting

    def save_rejection(self, rejection: NormalizationRejection) -> NormalizationRejection:
        self._rejections.append(rejection)
        return rejection

    def list_complete(self) -> list[JobPosting]:
        return [
            posting
            for posting in self._postings.values()
            if posting.completeness == JobPostingCompleteness.COMPLETE
        ]

    def list_rejections(self) -> list[NormalizationRejection]:
        return list(self._rejections)
