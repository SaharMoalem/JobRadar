from __future__ import annotations

from dataclasses import replace

from src.domain.draft_artifact import DraftArtifact, DraftArtifactKind
from src.ports.draft_artifact_port import DraftArtifactRepositoryPort


class InMemoryDraftArtifactAdapter(DraftArtifactRepositoryPort):
    def __init__(self) -> None:
        self._artifacts: dict[str, DraftArtifact] = {}

    def save(self, artifact: DraftArtifact) -> DraftArtifact:
        self._artifacts[artifact.id] = artifact
        return artifact

    def get(self, artifact_id: str) -> DraftArtifact | None:
        return self._artifacts.get(artifact_id)

    def list_for_posting(
        self,
        job_posting_id: str,
        *,
        kind: DraftArtifactKind | None = None,
    ) -> list[DraftArtifact]:
        items = [
            artifact
            for artifact in self._artifacts.values()
            if artifact.job_posting_id == job_posting_id
            and (kind is None or artifact.kind == kind)
        ]
        return sorted(items, key=lambda item: item.created_at)

    def list_latest_for_posting(self, job_posting_id: str) -> list[DraftArtifact]:
        return [
            artifact
            for artifact in self.list_for_posting(job_posting_id)
            if artifact.is_latest
        ]

    def mark_previous_not_latest(
        self,
        job_posting_id: str,
        kind: DraftArtifactKind,
        *,
        except_id: str | None = None,
    ) -> None:
        for artifact_id, artifact in list(self._artifacts.items()):
            if except_id is not None and artifact_id == except_id:
                continue
            if (
                artifact.job_posting_id == job_posting_id
                and artifact.kind == kind
                and artifact.is_latest
            ):
                self._artifacts[artifact_id] = replace(artifact, is_latest=False)
