from __future__ import annotations

from src.domain.match_scoring import MatchScore
from src.ports.match_scoring_port import MatchScoreRepositoryPort


class InMemoryMatchScoreAdapter(MatchScoreRepositoryPort):
    def __init__(self) -> None:
        self._scores: dict[str, MatchScore] = {}

    def save_score(self, score: MatchScore) -> MatchScore:
        self._scores[score.job_posting_id] = score
        return score

    def get_score(self, job_posting_id: str) -> MatchScore | None:
        return self._scores.get(job_posting_id)

    def list_scores(self) -> list[MatchScore]:
        return list(self._scores.values())

    def replace_scores(self, scores: list[MatchScore]) -> list[MatchScore]:
        self._scores = {score.job_posting_id: score for score in scores}
        return list(self._scores.values())
