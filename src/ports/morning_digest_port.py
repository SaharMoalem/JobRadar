from __future__ import annotations

from typing import Protocol

from src.domain.morning_digest import (
    MorningDigest,
    MorningDigestConfig,
    MorningDigestFailure,
    MorningDigestResult,
)


class MorningDigestConfigRepositoryPort(Protocol):
    def get_config(self) -> MorningDigestConfig | None: ...

    def save_config(self, config: MorningDigestConfig) -> MorningDigestConfig: ...


class MorningDigestRepositoryPort(Protocol):
    def list_digests(self) -> list[MorningDigest]: ...

    def get_by_run_context(self, run_context: str) -> MorningDigest | None: ...

    def replace_for_run_context(self, digest: MorningDigest) -> MorningDigest: ...


class MorningDigestTelemetryPort(Protocol):
    def record_result(self, result: MorningDigestResult) -> None: ...

    def record_failure(self, failure: MorningDigestFailure) -> None: ...

    def snapshot_metrics(self) -> dict[str, int]: ...
