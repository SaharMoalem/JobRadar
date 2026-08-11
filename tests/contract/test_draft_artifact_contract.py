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


async def _seed_review_posting(client) -> str:
    created = await client.post(
        "/career-sources",
        json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "draft-contract-seed"},
    )
    posting_id = (await client.get("/job-postings")).json()["data"][0]["id"]
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "review"})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "apply"})
    return posting_id


@pytest.mark.anyio
async def test_draft_artifact_response_contract_shape(client):
    posting_id = await _seed_review_posting(client)
    first = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "recruiter_message"},
    )
    second = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "recruiter_message"},
    )
    history = await client.get("/draft-artifacts", params={"job_posting_id": posting_id})

    assert first.status_code == 200
    assert second.status_code == 200
    for body in (first.json()["data"], second.json()["data"]):
        assert set(body.keys()) == {
            "id",
            "job_posting_id",
            "kind",
            "content",
            "source_reference",
            "status",
            "is_latest",
            "correlation_id",
            "created_at",
        }
        assert isinstance(body["id"], str)
        assert isinstance(body["job_posting_id"], str)
        assert isinstance(body["kind"], str)
        assert isinstance(body["content"], str)
        assert isinstance(body["source_reference"], str)
        assert body["status"] == "draft"
        assert isinstance(body["is_latest"], bool)
        assert isinstance(body["correlation_id"], str)
        assert isinstance(body["created_at"], str)

    items = history.json()["data"]
    assert len(items) == 2
    assert items[0]["is_latest"] is False
    assert items[1]["is_latest"] is True
    assert [item["created_at"] for item in items] == sorted(item["created_at"] for item in items)
