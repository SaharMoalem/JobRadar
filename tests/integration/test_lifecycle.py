import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult, RawCrawlRecord
from src.domain.lifecycle import JobLifecycleState
from src.domain.source_policy import SourcePolicyConfig
from tests.support.discovery_stack import build_discovery_stack
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class DifferentJobCrawlerPlugin:
    plugin_id = "different"

    def crawl(self, source: CareerSource, *, correlation_id: str) -> CrawlPluginResult:
        return CrawlPluginResult(
            plugin_id=self.plugin_id,
            records=[
                RawCrawlRecord(
                    external_id=f"{source.id}-other-1",
                    title=f"Other role at {source.name}",
                    url=f"{source.base_url}/jobs/other",
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
async def test_execute_sets_new_lifecycle_state(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")

    response = await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "life-1"},
    )

    posting = response.json()["data"]["job_postings"][0]
    assert posting["lifecycle_state"] == JobLifecycleState.NEW.value

    transitions = await client.get("/job-lifecycle-transitions")
    assert transitions.status_code == 200
    assert len(transitions.json()["data"]) >= 1


@pytest.mark.anyio
async def test_unseen_posting_expires_when_source_returns_other_jobs(client):
    telemetry_app = create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        extra_plugins=[DifferentJobCrawlerPlugin()],
    )
    async with AsyncClient(transport=ASGITransport(app=telemetry_app), base_url="http://test") as ac:
        source_id = await _create_runnable(ac, name="Acme", url="https://acme.example.com", plugin_id="generic")
        first = await ac.post(f"/career-sources/{source_id}/execute", headers={"x-correlation-id": "life-2a"})
        first_id = first.json()["data"]["job_postings"][0]["id"]
        await ac.patch(
            f"/career-sources/{source_id}",
            json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "different"},
        )
        await ac.post(f"/career-sources/{source_id}/execute", headers={"x-correlation-id": "life-2b"})

        listed = await ac.get("/job-postings")
        states = {item["id"]: item["lifecycle_state"] for item in listed.json()["data"]}
        assert states[first_id] == JobLifecycleState.EXPIRED.value
        assert any(state == JobLifecycleState.NEW.value for state in states.values())


def test_discovery_stack_expires_unseen_postings():
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
        plugins={"generic": GenericStubCrawlerPlugin(), "different": DifferentJobCrawlerPlugin()},
    )

    source = source_service.create("Acme", "https://acme.example.com", plugin_id="generic")
    compliance_service.approve(source.id)
    source_service.enable(source.id)
    discovery.run_source(source.id, correlation_id="life-3a")
    first_id = postings.list_complete()[0].id

    source_service.update(source.id, "Acme", "https://acme.example.com", plugin_id="different")
    discovery.run_source(source.id, correlation_id="life-3b")

    by_id = {posting.id: posting for posting in postings.list_complete()}
    assert by_id[first_id].lifecycle_state == JobLifecycleState.EXPIRED
    assert any(posting.lifecycle_state == JobLifecycleState.NEW for posting in by_id.values())


@pytest.mark.anyio
async def test_lifecycle_metrics_endpoint(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "life-metrics"},
    )

    metrics = await client.get("/observability/lifecycle-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["data"]["transitions_total"] >= 1
