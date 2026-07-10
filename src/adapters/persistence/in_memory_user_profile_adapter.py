from __future__ import annotations

from src.domain.user_profile import UserProfile
from src.ports.match_scoring_port import UserProfileRepositoryPort


class InMemoryUserProfileAdapter(UserProfileRepositoryPort):
    def __init__(self) -> None:
        self._profile: UserProfile | None = None

    def get_profile(self) -> UserProfile | None:
        return self._profile

    def save_profile(self, profile: UserProfile) -> UserProfile:
        self._profile = profile
        return profile
