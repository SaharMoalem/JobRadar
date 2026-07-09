from __future__ import annotations

from typing import Protocol

from src.domain.career_source import CareerSource


class CareerSourceRepositoryPort(Protocol):
    def create(self, source: CareerSource) -> CareerSource: ...

    def update(self, source: CareerSource) -> CareerSource: ...

    def get(self, source_id: str) -> CareerSource | None: ...

    def list_all(self) -> list[CareerSource]: ...

    def count_enabled(self) -> int: ...
