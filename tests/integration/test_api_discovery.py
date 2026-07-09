import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.domain.crawl import CrawlPluginResult
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class FailingCrawlerPlugin:
    plugin_id = "failing"

    def crawl(self, source, *, correlation_id: str) -> CrawlPluginResult:
        raise RuntimeError("api plugin failure")


@pytest.fixture
def app():
    return create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        extra_plugins=[FailingCrawlerPlugin()],
    )


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
async def test_execute_returns_crawl_outcome(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")

    response = await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "api-exec-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["data"]["status"] == "succeeded"
    assert payload["data"]["plugin_id"] == "generic"
    assert len(payload["data"]["records"]) == 1
    assert len(payload["data"]["job_postings"]) == 1
    assert payload["data"]["job_postings"][0]["completeness"] == "complete"


@pytest.mark.anyio
async def test_discovery_run_isolates_plugin_failures(client):
    good_id = await _create_runnable(client, name="Good", url="https://good.example.com")
    await _create_runnable(client, name="Bad", url="https://bad.example.com", plugin_id="failing")

    response = await client.post("/discovery/runs", headers={"x-correlation-id": "api-run-1"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["succeeded_count"] == 1
    assert data["failed_count"] == 1
    outcomes = {item["source_id"]: item for item in data["outcomes"]}
    assert outcomes[good_id]["status"] == "succeeded"
    assert outcomes[good_id]["records"]


@pytest.mark.anyio
async def test_execute_returns_502_when_plugin_fails(client):
    bad_id = await _create_runnable(client, name="Bad", url="https://bad.example.com", plugin_id="failing")

    response = await client.post(
        f"/career-sources/{bad_id}/execute",
        headers={"x-correlation-id": "api-exec-fail"},
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["error"]["code"] == "CRAWLER_PLUGIN_FAILED"
    assert payload["data"]["status"] == "failed"


class EmptyCrawlerPlugin:
    plugin_id = "empty"

    def crawl(self, source, *, correlation_id: str) -> CrawlPluginResult:
        return CrawlPluginResult(plugin_id="empty", records=[])


@pytest.mark.anyio
async def test_execute_returns_422_when_plugin_returns_no_records():
    app = create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        extra_plugins=[EmptyCrawlerPlugin()],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        source_id = await _create_runnable(client, name="Empty", url="https://empty.example.com", plugin_id="empty")
        response = await client.post(
            f"/career-sources/{source_id}/execute",
            headers={"x-correlation-id": "api-exec-empty"},
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "CRAWLER_EMPTY_RESULT"
