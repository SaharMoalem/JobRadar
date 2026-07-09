from __future__ import annotations

from src.domain.career_source import CareerSource
from src.ports.crawler_plugin_port import CrawlerPluginPort


class InMemoryCrawlerPluginRegistry:
    def __init__(self, plugins: dict[str, CrawlerPluginPort]) -> None:
        self._plugins = plugins

    def register(self, plugin: CrawlerPluginPort) -> None:
        self._plugins[plugin.plugin_id] = plugin

    def resolve(self, source: CareerSource) -> CrawlerPluginPort:
        plugin = self._plugins.get(source.plugin_id)
        if plugin is None:
            raise KeyError(f"No crawler plugin registered for plugin_id={source.plugin_id!r}")
        return plugin
