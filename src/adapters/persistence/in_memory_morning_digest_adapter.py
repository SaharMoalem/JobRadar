from __future__ import annotations

from src.domain.morning_digest import MorningDigest, MorningDigestConfig
from src.ports.morning_digest_port import (
    MorningDigestConfigRepositoryPort,
    MorningDigestRepositoryPort,
)


class InMemoryMorningDigestConfigAdapter(MorningDigestConfigRepositoryPort):
    def __init__(self) -> None:
        self._config: MorningDigestConfig | None = None

    def get_config(self) -> MorningDigestConfig | None:
        return self._config

    def save_config(self, config: MorningDigestConfig) -> MorningDigestConfig:
        self._config = config
        return config


class InMemoryMorningDigestAdapter(MorningDigestRepositoryPort):
    def __init__(self) -> None:
        self._digests: dict[str, MorningDigest] = {}

    def list_digests(self) -> list[MorningDigest]:
        return sorted(self._digests.values(), key=lambda item: item.created_at, reverse=True)

    def get_by_run_context(self, run_context: str) -> MorningDigest | None:
        return self._digests.get(run_context)

    def replace_for_run_context(self, digest: MorningDigest) -> MorningDigest:
        self._digests[digest.run_context] = digest
        return digest
