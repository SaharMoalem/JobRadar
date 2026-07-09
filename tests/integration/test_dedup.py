import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult, RawCrawlRecord
from src.domain.source_policy import SourcePolicyConfig
from tests.support.discovery_stack import build_discovery_stack
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class SharedUrlCrawlerPlugin:
    plugin_id = "shared-url"

    def crawl(self, source: CareerSource, *, correlation_id: str) -> CrawlPluginResult:
        return CrawlPluginResult(
            plugin_id=self.plugin_id,
            records=[
                RawCrawlRecord(
                    external_id=f"{source.id}-shared",
                    title=f"Role at {source.name}",
                    url="https://jobs.example.com/opening/42",
                    raw_payload={
                        "company": source.name,
                        "location": "Remote",
                        "posted_at": "2026-07-01T08:00:00+00:00",
                    },
                )
            ],
        )


@pytest.fixture
def app():
    return create_app(compliance_checker=FakeComplianceCheckAdapter())


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _create_runnable(client, *, name: str, url: str, plugin_id: str = "generic"):
    created = await client.post(
        "/career-sources",
        json={"name": name, "base_url": url, "plugin_id": plugin_id},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    return source_id


@pytest.mark.anyio
async def test_repeat_execute_keeps_stable_canonical_identity(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")

    first = await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "dedup-repeat-1"},
    )
    second = await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "dedup-repeat-2"},
    )

    first_id = first.json()["data"]["job_postings"][0]["id"]
    second_id = second.json()["data"]["job_postings"][0]["id"]
    assert first_id == second_id

    listed = await client.get("/job-postings")
    assert len(listed.json()["data"]) == 1


@pytest.mark.anyio
async def test_cross_source_duplicate_is_suppressed_and_queryable(client):
    postings = InMemoryJobPostingAdapter()
    app = create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        extra_plugins=[SharedUrlCrawlerPlugin()],
        job_posting_repository=postings,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first_source = await _create_runnable(ac, name="Alpha", url="https://alpha.example.com", plugin_id="shared-url")
        second_source = await _create_runnable(ac, name="Beta", url="https://beta.example.com", plugin_id="shared-url")

        await ac.post(f"/career-sources/{first_source}/execute", headers={"x-correlation-id": "dedup-1"})
        await ac.post(f"/career-sources/{second_source}/execute", headers={"x-correlation-id": "dedup-2"})

        listed = await ac.get("/job-postings")
        assert len(listed.json()["data"]) == 1

        links = await ac.get("/job-duplicate-links")
        assert links.status_code == 200
        items = links.json()["data"]
        assert len(items) == 1
        assert items[0]["career_source_id"] == second_source
        assert items[0]["canonical_id"] == listed.json()["data"][0]["id"]


def test_discovery_stack_dedup_integration():
    repository = InMemoryCareerSourceAdapter()
    source_service = CareerSourceService(
        repository=repository,
        config=SourcePolicyConfig(max_enabled_sources=50),
    )
    compliance_service = SourceComplianceService(
        repository=repository,
        compliance_checker=FakeComplianceCheckAdapter(),
    )
    discovery, postings = build_discovery_stack(
        repository,
        plugins={"generic": GenericStubCrawlerPlugin(), "shared-url": SharedUrlCrawlerPlugin()},
    )

    first = source_service.create("Alpha", "https://alpha.example.com", plugin_id="shared-url")
    second = source_service.create("Beta", "https://beta.example.com", plugin_id="shared-url")
    for source in (first, second):
        compliance_service.approve(source.id)
        source_service.enable(source.id)

    discovery.run_source(first.id, correlation_id="stack-1")
    discovery.run_source(second.id, correlation_id="stack-2")
    discovery.run_source(second.id, correlation_id="stack-3")

    assert len(postings.list_complete()) == 1
    assert len(postings.list_duplicate_links()) == 1
