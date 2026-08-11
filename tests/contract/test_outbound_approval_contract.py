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


async def _seed_draft(client) -> str:
    created = await client.post(
        "/career-sources",
        json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "outbound-contract-seed"},
    )
    posting_id = (await client.get("/job-postings")).json()["data"][0]["id"]
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "review"})
    draft = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "interview_prep"},
    )
    return draft.json()["data"]["id"]


@pytest.mark.anyio
async def test_outbound_approval_and_delivery_contract_shape(client):
    artifact_id = await _seed_draft(client)
    approved = await client.post(f"/draft-artifacts/{artifact_id}/approve-outbound")
    delivered = await client.post(
        "/outbound/deliver",
        json={"artifact_id": artifact_id, "channel": "manual_export"},
    )

    assert approved.status_code == 200
    approval = approved.json()["data"]
    assert set(approval.keys()) == {"id", "artifact_id", "correlation_id", "approved_at"}
    assert isinstance(approval["id"], str)
    assert isinstance(approval["artifact_id"], str)
    assert isinstance(approval["correlation_id"], str)
    assert isinstance(approval["approved_at"], str)

    assert delivered.status_code == 200
    delivery = delivered.json()["data"]
    assert set(delivery.keys()) == {
        "id",
        "artifact_id",
        "approval_id",
        "channel",
        "correlation_id",
        "content_snapshot",
        "delivered_at",
    }
    assert isinstance(delivery["id"], str)
    assert delivery["artifact_id"] == artifact_id
    assert delivery["approval_id"] == approval["id"]
    assert isinstance(delivery["channel"], str)
    assert isinstance(delivery["correlation_id"], str)
    assert isinstance(delivery["content_snapshot"], str)
    assert isinstance(delivery["delivered_at"], str)
