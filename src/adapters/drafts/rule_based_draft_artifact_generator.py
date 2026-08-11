from __future__ import annotations

from src.domain.draft_artifact import DraftArtifactKind
from src.domain.draft_artifact_policy import generate_draft_content
from src.domain.job_posting import JobPosting
from src.domain.user_profile import UserProfile
from src.ports.draft_artifact_port import DraftArtifactGeneratorPort


class RuleBasedDraftArtifactGeneratorAdapter(DraftArtifactGeneratorPort):
    def generate(
        self,
        *,
        kind: DraftArtifactKind,
        posting: JobPosting,
        profile: UserProfile | None,
    ) -> str:
        return generate_draft_content(kind=kind, posting=posting, profile=profile)
