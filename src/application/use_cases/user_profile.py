from __future__ import annotations

from dataclasses import dataclass

from src.domain.user_profile import UserProfile
from src.ports.match_scoring_port import UserProfileRepositoryPort


@dataclass(slots=True)
class UserProfileService:
    repository: UserProfileRepositoryPort

    def get(self) -> UserProfile | None:
        return self.repository.get_profile()

    def save(
        self,
        *,
        skills: list[str],
        preferred_locations: list[str],
        preferred_languages: list[str],
        target_seniority: str,
    ) -> UserProfile:
        existing = self.repository.get_profile()
        profile = UserProfile(
            id=existing.id if existing else "default",
            skills=tuple(skill.strip() for skill in skills if skill.strip()),
            preferred_locations=tuple(location.strip() for location in preferred_locations if location.strip()),
            preferred_languages=tuple(language.strip() for language in preferred_languages if language.strip()),
            target_seniority=target_seniority.strip(),
            profile_version=existing.profile_version if existing else "v1",
        )
        profile.touch()
        return self.repository.save_profile(profile)
