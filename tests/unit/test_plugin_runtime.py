from src.adapters.crawling.plugin_runtime import CrawlerPluginRuntime
from src.domain.career_source import CareerSource
from src.domain.crawl import SourceCrawlStatus


class _FailingPlugin:
    plugin_id = "failing"

    def crawl(self, source: CareerSource, *, correlation_id: str):
        raise RuntimeError("plugin exploded")


class _CountingPlugin:
    plugin_id = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def crawl(self, source: CareerSource, *, correlation_id: str):
        self.calls += 1
        from src.domain.crawl import CrawlPluginResult, RawCrawlRecord

        return CrawlPluginResult(
            plugin_id=self.plugin_id,
            records=[
                RawCrawlRecord(
                    external_id=f"{source.id}-1",
                    title="Role",
                    url=source.base_url,
                )
            ],
        )


def test_runtime_isolates_plugin_failure():
    runtime = CrawlerPluginRuntime()
    source = CareerSource(id="s1", name="A", base_url="https://a.example.com")

    outcome = runtime.execute(_FailingPlugin(), source, correlation_id="corr-1")

    assert outcome.status == SourceCrawlStatus.FAILED
    assert outcome.error_code == "CRAWLER_PLUGIN_FAILED"
    assert outcome.records == []


def test_runtime_returns_success_records():
    runtime = CrawlerPluginRuntime()
    plugin = _CountingPlugin()
    source = CareerSource(id="s2", name="B", base_url="https://b.example.com")

    outcome = runtime.execute(plugin, source, correlation_id="corr-2")

    assert outcome.status == SourceCrawlStatus.SUCCEEDED
    assert outcome.plugin_id == "counting"
    assert len(outcome.records) == 1
    assert plugin.calls == 1


class _EmptyPlugin:
    plugin_id = "empty"

    def crawl(self, source: CareerSource, *, correlation_id: str):
        from src.domain.crawl import CrawlPluginResult

        return CrawlPluginResult(plugin_id="wrong-id", records=[])


def test_runtime_fails_on_empty_records():
    runtime = CrawlerPluginRuntime()
    source = CareerSource(id="s3", name="C", base_url="https://c.example.com")

    outcome = runtime.execute(_EmptyPlugin(), source, correlation_id="corr-3")

    assert outcome.status == SourceCrawlStatus.FAILED
    assert outcome.error_code == "CRAWLER_EMPTY_RESULT"
    assert outcome.plugin_id == "empty"
