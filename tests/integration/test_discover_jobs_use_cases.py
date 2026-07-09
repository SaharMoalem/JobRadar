from src.adapters.crawling.plugin_registry import InMemoryCrawlerPluginRegistry
from src.adapters.crawling.plugin_runtime import CrawlerPluginRuntime
from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.discover_jobs import DiscoverJobsUseCase
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.crawl import SourceCrawlStatus
from src.domain.source_policy import SourcePolicyConfig
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class FailingCrawlerPlugin:
    plugin_id = "failing"

    def crawl(self, source, *, correlation_id: str):
        raise RuntimeError("simulated plugin failure")


def _services():
    repository = InMemoryCareerSourceAdapter()
    source_service = CareerSourceService(
        repository=repository,
        config=SourcePolicyConfig(max_enabled_sources=50),
    )
    compliance_service = SourceComplianceService(
        repository=repository,
        compliance_checker=FakeComplianceCheckAdapter(),
    )
    registry = InMemoryCrawlerPluginRegistry(
        {
            "generic": GenericStubCrawlerPlugin(),
            "failing": FailingCrawlerPlugin(),
        }
    )
    discovery = DiscoverJobsUseCase(
        repository=repository,
        plugin_registry=registry,
        runtime=CrawlerPluginRuntime(),
    )
    return source_service, compliance_service, discovery


def test_run_all_continues_when_one_plugin_fails():
    source_service, compliance_service, discovery = _services()

    good = source_service.create("Good Co", "https://good.example.com", plugin_id="generic")
    bad = source_service.create("Bad Co", "https://bad.example.com", plugin_id="failing")
    for source in (good, bad):
        compliance_service.approve(source.id)
        source_service.enable(source.id)

    run = discovery.run_all(correlation_id="run-1")

    assert run.succeeded_count == 1
    assert run.failed_count == 1
    by_source = {outcome.source_id: outcome for outcome in run.outcomes}
    assert by_source[good.id].status == SourceCrawlStatus.SUCCEEDED
    assert by_source[bad.id].status == SourceCrawlStatus.FAILED


def test_run_source_executes_through_generic_plugin():
    source_service, compliance_service, discovery = _services()
    source = source_service.create("Acme", "https://acme.example.com")
    compliance_service.approve(source.id)
    source_service.enable(source.id)

    outcome = discovery.run_source(source.id, correlation_id="run-2")

    assert outcome.status == SourceCrawlStatus.SUCCEEDED
    assert outcome.plugin_id == "generic"
    assert len(outcome.records) == 1


def test_run_all_continues_when_plugin_id_missing():
    source_service, compliance_service, discovery = _services()

    good = source_service.create("Good Co", "https://good.example.com", plugin_id="generic")
    unknown = source_service.create("Unknown Co", "https://unknown.example.com", plugin_id="missing")
    for source in (good, unknown):
        compliance_service.approve(source.id)
        source_service.enable(source.id)

    run = discovery.run_all(correlation_id="run-missing-plugin")

    assert run.succeeded_count == 1
    assert run.failed_count == 1
    by_source = {outcome.source_id: outcome for outcome in run.outcomes}
    assert by_source[unknown.id].error_code == "CRAWLER_PLUGIN_NOT_FOUND"
