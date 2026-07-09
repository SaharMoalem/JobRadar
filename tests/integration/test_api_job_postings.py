import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


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
async def test_list_job_postings_after_execute(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")

    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "list-postings-1"},
    )

    listed = await client.get("/job-postings")
    assert listed.status_code == 200
    items = listed.json()["data"]
    assert len(items) == 1
    assert items[0]["title"].startswith("Sample role")
    assert items[0]["company"] == "Acme"
