from __future__ import annotations

from typing import Protocol

from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult


class CrawlerPluginPort(Protocol):
    plugin_id: str

    def crawl(self, source: CareerSource, *, correlation_id: str) -> CrawlPluginResult: ...


class CrawlerPluginRegistryPort(Protocol):
    def resolve(self, source: CareerSource) -> CrawlerPluginPort: ...
