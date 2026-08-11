from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.domain.draft_artifact import (
    DraftArtifact,
    DraftArtifactKind,
    DraftArtifactStatus,
    DraftArtifactValidationError,
    DraftGenerationFailure,
)
from src.domain.draft_artifact_policy import build_source_reference, validate_draft_context
from src.ports.application_tracker_port import ApplicationTrackerRepositoryPort
from src.ports.draft_artifact_port import (
    DraftArtifactGeneratorPort,
    DraftArtifactRepositoryPort,
    DraftArtifactTelemetryPort,
)
from src.ports.job_posting_port import JobPostingRepositoryPort
from src.ports.match_scoring_port import UserProfileRepositoryPort


@dataclass(slots=True)
class GenerateDraftArtifactUseCase:
    job_posting_repository: JobPostingRepositoryPort
    tracker_repository: ApplicationTrackerRepositoryPort
    profile_repository: UserProfileRepositoryPort
    draft_repository: DraftArtifactRepositoryPort
    generator: DraftArtifactGeneratorPort
    telemetry: DraftArtifactTelemetryPort

    def generate(
        self,
        *,
        job_posting_id: str,
        kind: DraftArtifactKind,
        correlation_id: str = "local",
    ) -> DraftArtifact:
        posting = next(
            (
                item
                for item in self.job_posting_repository.list_complete()
                if item.id == job_posting_id
            ),
            None,
        )
        tracked = self.tracker_repository.get(job_posting_id)
        try:
            validate_draft_context(posting=posting, tracked=tracked)
            assert posting is not None
            profile = self.profile_repository.get_profile()
            try:
                content = self.generator.generate(kind=kind, posting=posting, profile=profile)
            except DraftArtifactValidationError:
                raise
            except Exception as exc:  # noqa: BLE001 - convert generator failures to typed errors
                raise DraftArtifactValidationError(
                    "DRAFT_GENERATION_FAILED",
                    f"Draft generator failed: {type(exc).__name__}",
                ) from exc
            if not content.strip():
                raise DraftArtifactValidationError(
                    "DRAFT_GENERATION_FAILED",
                    "Draft generator returned empty content.",
                )
            artifact = DraftArtifact(
                id=f"draft-{uuid4().hex[:12]}",
                job_posting_id=job_posting_id,
                kind=kind,
                content=content,
                source_reference=build_source_reference(posting),
                status=DraftArtifactStatus.DRAFT,
                is_latest=True,
                correlation_id=correlation_id,
            )
            saved = self.draft_repository.save(artifact)
            self.draft_repository.mark_previous_not_latest(
                job_posting_id,
                kind,
                except_id=saved.id,
            )
            self.telemetry.record_generated(saved)
            return saved
        except DraftArtifactValidationError as exc:
            self.telemetry.record_failure(
                DraftGenerationFailure(
                    code=exc.code,
                    message=str(exc),
                    correlation_id=correlation_id,
                )
            )
            raise

    def list_for_posting(
        self,
        job_posting_id: str,
        *,
        kind: DraftArtifactKind | None = None,
    ) -> list[DraftArtifact]:
        return self.draft_repository.list_for_posting(job_posting_id, kind=kind)

    def list_latest_for_posting(self, job_posting_id: str) -> list[DraftArtifact]:
        return self.draft_repository.list_latest_for_posting(job_posting_id)

    def get(self, artifact_id: str) -> DraftArtifact | None:
        return self.draft_repository.get(artifact_id)
