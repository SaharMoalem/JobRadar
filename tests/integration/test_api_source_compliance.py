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


@pytest.mark.anyio
async def test_enable_without_compliance_returns_409(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Company", "base_url": "https://jobs.example.com"},
    )
    source_id = created.json()["data"]["id"]

    response = await client.post(f"/career-sources/{source_id}/enable")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_COMPLIANCE_NOT_APPROVED"


@pytest.mark.anyio
async def test_execute_without_compliance_returns_409(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Company", "base_url": "https://jobs.example.com"},
    )
    source_id = created.json()["data"]["id"]

    response = await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "corr-api-1"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_COMPLIANCE_NOT_APPROVED"


@pytest.mark.anyio
async def test_compliance_approve_enable_execute_flow(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Company", "base_url": "https://jobs.example.com"},
    )
    source_id = created.json()["data"]["id"]

    approved = await client.post(f"/career-sources/{source_id}/compliance/approve")
    assert approved.status_code == 200
    assert approved.json()["data"]["compliance_status"] == "approved"

    enabled = await client.post(f"/career-sources/{source_id}/enable")
    assert enabled.status_code == 200

    executed = await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "corr-api-2"},
    )
    assert executed.status_code == 200
    assert executed.json()["data"]["status"] == "succeeded"
    assert executed.json()["data"]["plugin_id"] == "generic"
