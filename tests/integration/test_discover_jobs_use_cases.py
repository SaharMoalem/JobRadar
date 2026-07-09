from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.crawl import CrawlPluginResult, RawCrawlRecord, SourceCrawlStatus
from src.domain.job_posting import JobPostingCompleteness
from src.domain.source_policy import SourcePolicyConfig
from tests.support.discovery_stack import build_discovery_stack
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class IncompleteCrawlerPlugin:
    plugin_id = "incomplete"

    def crawl(self, source, *, correlation_id: str) -> CrawlPluginResult:
        return CrawlPluginResult(
            plugin_id=self.plugin_id,
            records=[
                RawCrawlRecord(
                    external_id=f"{source.id}-incomplete-1",
                    title="Incomplete role",
                    url=source.base_url,
                    raw_payload={"company": source.name},
                )
            ],
        )


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
    from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin

    discovery, postings = build_discovery_stack(
        repository,
        plugins={
            "generic": GenericStubCrawlerPlugin(),
            "failing": FailingCrawlerPlugin(),
            "incomplete": IncompleteCrawlerPlugin(),
        },
    )
    return source_service, compliance_service, discovery, postings


def test_run_source_persists_normalized_job_posting():
    source_service, compliance_service, discovery, postings = _services()
    source = source_service.create("Acme", "https://acme.example.com")
    compliance_service.approve(source.id)
    source_service.enable(source.id)

    outcome = discovery.run_source(source.id, correlation_id="norm-1")

    assert outcome.status == SourceCrawlStatus.SUCCEEDED
    assert len(outcome.job_postings) == 1
    assert outcome.job_postings[0].completeness == JobPostingCompleteness.COMPLETE
    assert postings.list_complete()[0].title.startswith("Sample role")


def test_incomplete_record_is_rejected_and_persisted():
    source_service, compliance_service, discovery, postings = _services()
    source = source_service.create("Acme", "https://acme.example.com", plugin_id="incomplete")
    compliance_service.approve(source.id)
    source_service.enable(source.id)

    outcome = discovery.run_source(source.id, correlation_id="norm-2")

    assert outcome.status == SourceCrawlStatus.SUCCEEDED
    assert outcome.job_postings == ()
    assert len(outcome.normalization_rejections) == 1
    assert "posted_at" in outcome.normalization_rejections[0].missing_fields
    assert postings.list_complete() == []
    assert len(postings.list_rejections()) == 1


def test_run_all_continues_when_one_plugin_fails():
    source_service, compliance_service, discovery, _postings = _services()

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


def test_run_all_continues_when_plugin_id_missing():
    source_service, compliance_service, discovery, _postings = _services()

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
