from __future__ import annotations

from src.domain.career_source import CareerSource, CareerSourceStatus
from src.ports.career_source_port import CareerSourceRepositoryPort


class InMemoryCareerSourceAdapter(CareerSourceRepositoryPort):
    def __init__(self) -> None:
        self._items: dict[str, CareerSource] = {}

    def create(self, source: CareerSource) -> CareerSource:
        self._items[source.id] = source
        return source

    def update(self, source: CareerSource) -> CareerSource:
        self._items[source.id] = source
        return source

    def get(self, source_id: str) -> CareerSource | None:
        return self._items.get(source_id)

    def list_all(self) -> list[CareerSource]:
        return list(self._items.values())

    def count_enabled(self) -> int:
        return sum(1 for item in self._items.values() if item.status == CareerSourceStatus.ENABLED)
