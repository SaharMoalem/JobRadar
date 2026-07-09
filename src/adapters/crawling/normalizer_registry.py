from __future__ import annotations

from src.domain.career_source import CareerSource
from src.ports.crawl_normalizer_port import CrawlNormalizerPort


class InMemoryCrawlNormalizerRegistry:
    def __init__(self, normalizers: dict[str, CrawlNormalizerPort]) -> None:
        self._normalizers = normalizers

    def register(self, normalizer: CrawlNormalizerPort) -> None:
        self._normalizers[normalizer.plugin_id] = normalizer

    def resolve(self, source: CareerSource) -> CrawlNormalizerPort:
        normalizer = self._normalizers.get(source.plugin_id)
        if normalizer is None:
            raise KeyError(f"No crawl normalizer registered for plugin_id={source.plugin_id!r}")
        return normalizer
