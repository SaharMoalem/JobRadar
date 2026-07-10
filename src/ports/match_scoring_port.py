from __future__ import annotations

from typing import Protocol

from src.domain.match_scoring import MatchScore
from src.domain.user_profile import UserProfile


class UserProfileRepositoryPort(Protocol):
    def get_profile(self) -> UserProfile | None: ...

    def save_profile(self, profile: UserProfile) -> UserProfile: ...


class MatchScoreRepositoryPort(Protocol):
    def save_score(self, score: MatchScore) -> MatchScore: ...

    def get_score(self, job_posting_id: str) -> MatchScore | None: ...

    def list_scores(self) -> list[MatchScore]: ...

    def replace_scores(self, scores: list[MatchScore]) -> list[MatchScore]: ...
