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
        headers={"x-correlation-id": "outbound-seed"},
    )
    posting_id = (await client.get("/job-postings")).json()["data"][0]["id"]
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "review"})
    draft = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "recruiter_message"},
    )
    return draft.json()["data"]["id"]


@pytest.mark.anyio
async def test_outbound_without_approval_is_blocked(client):
    artifact_id = await _seed_draft(client)
    blocked = await client.post(
        "/outbound/deliver",
        json={"artifact_id": artifact_id},
        headers={"x-correlation-id": "block-out-1"},
    )
    deliveries = await client.get("/outbound/deliveries")
    metrics = await client.get("/observability/outbound-metrics")

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "OUTBOUND_APPROVAL_REQUIRED"
    assert deliveries.json()["data"] == []
    assert metrics.json()["data"]["outbound_policy_blocks_total"] >= 1


@pytest.mark.anyio
async def test_approve_then_deliver_succeeds(client):
    artifact_id = await _seed_draft(client)
    approved = await client.post(
        f"/draft-artifacts/{artifact_id}/approve-outbound",
        headers={"x-correlation-id": "approve-out-1"},
    )
    delivered = await client.post(
        "/outbound/deliver",
        json={"artifact_id": artifact_id, "channel": "manual_export"},
        headers={"x-correlation-id": "deliver-out-1"},
    )
    deliveries = await client.get("/outbound/deliveries")
    metrics = await client.get("/observability/outbound-metrics")

    assert approved.status_code == 200
    assert approved.json()["data"]["artifact_id"] == artifact_id
    assert delivered.status_code == 200
    assert delivered.json()["data"]["approval_id"] == approved.json()["data"]["id"]
    assert len(deliveries.json()["data"]) == 1
    assert metrics.json()["data"]["outbound_approvals_total"] >= 1
    assert metrics.json()["data"]["outbound_deliveries_total"] >= 1


@pytest.mark.anyio
async def test_draft_generation_does_not_auto_deliver(client):
    artifact_id = await _seed_draft(client)
    deliveries = await client.get("/outbound/deliveries")
    assert artifact_id
    assert deliveries.json()["data"] == []


@pytest.mark.anyio
async def test_approval_consumed_and_missing_artifact_blocked(client):
    artifact_id = await _seed_draft(client)
    await client.post(
        f"/draft-artifacts/{artifact_id}/approve-outbound",
        headers={"x-correlation-id": "approve-once"},
    )
    first = await client.post(
        "/outbound/deliver",
        json={"artifact_id": artifact_id},
        headers={"x-correlation-id": "deliver-once"},
    )
    second = await client.post(
        "/outbound/deliver",
        json={"artifact_id": artifact_id},
        headers={"x-correlation-id": "deliver-again"},
    )
    missing = await client.post(
        "/draft-artifacts/missing-draft/approve-outbound",
        headers={"x-correlation-id": "missing-approve"},
    )
    deliveries = await client.get("/outbound/deliveries")
    metrics = await client.get("/observability/outbound-metrics")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "OUTBOUND_APPROVAL_REQUIRED"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "OUTBOUND_ARTIFACT_NOT_FOUND"
    assert len(deliveries.json()["data"]) == 1
    assert metrics.json()["data"]["outbound_policy_blocks_total"] >= 2
