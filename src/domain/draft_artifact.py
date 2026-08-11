from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class DraftArtifactKind(str, Enum):
    RECRUITER_MESSAGE = "recruiter_message"
    CV_IMPROVEMENT = "cv_improvement"
    INTERVIEW_PREP = "interview_prep"


class DraftArtifactStatus(str, Enum):
    DRAFT = "draft"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class DraftArtifact:
    id: str
    job_posting_id: str
    kind: DraftArtifactKind
    content: str
    source_reference: str
    status: DraftArtifactStatus = DraftArtifactStatus.DRAFT
    is_latest: bool = True
    correlation_id: str = "local"
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class DraftGenerationFailure:
    code: str
    message: str
    correlation_id: str


class DraftArtifactValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
