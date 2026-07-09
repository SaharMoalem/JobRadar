from __future__ import annotations

import pytest

from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin
from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult


def test_generic_stub_plugin_satisfies_crawler_contract():
    plugin = GenericStubCrawlerPlugin()
    source = CareerSource(id="src-1", name="Acme", base_url="https://acme.example.com/jobs")

    result = plugin.crawl(source, correlation_id="contract-1")

    assert isinstance(result, CrawlPluginResult)
    assert result.plugin_id == "generic"
    assert len(result.records) >= 1
    record = result.records[0]
    assert record.external_id
    assert record.title
    assert record.url == source.base_url
    assert isinstance(record.raw_payload, dict)


@pytest.mark.parametrize("plugin_factory", [GenericStubCrawlerPlugin])
def test_registered_plugins_expose_plugin_id(plugin_factory):
    plugin = plugin_factory()
    assert isinstance(plugin.plugin_id, str)
    assert plugin.plugin_id
