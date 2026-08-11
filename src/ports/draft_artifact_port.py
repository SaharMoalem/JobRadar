from __future__ import annotations

from typing import Protocol

from src.domain.draft_artifact import DraftArtifact, DraftArtifactKind, DraftGenerationFailure
from src.domain.job_posting import JobPosting
from src.domain.user_profile import UserProfile


class DraftArtifactGeneratorPort(Protocol):
    def generate(
        self,
        *,
        kind: DraftArtifactKind,
        posting: JobPosting,
        profile: UserProfile | None,
    ) -> str: ...


class DraftArtifactRepositoryPort(Protocol):
    def save(self, artifact: DraftArtifact) -> DraftArtifact: ...

    def get(self, artifact_id: str) -> DraftArtifact | None: ...

    def list_for_posting(
        self,
        job_posting_id: str,
        *,
        kind: DraftArtifactKind | None = None,
    ) -> list[DraftArtifact]: ...

    def list_latest_for_posting(self, job_posting_id: str) -> list[DraftArtifact]: ...

    def mark_previous_not_latest(
        self,
        job_posting_id: str,
        kind: DraftArtifactKind,
        *,
        except_id: str | None = None,
    ) -> None: ...


class DraftArtifactTelemetryPort(Protocol):
    def record_generated(self, artifact: DraftArtifact) -> None: ...

    def record_failure(self, failure: DraftGenerationFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
