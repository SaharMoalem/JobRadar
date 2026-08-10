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


async def _seed_posting(client) -> str:
    created = await client.post(
        "/career-sources",
        json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "tracker-contract-seed"},
    )
    listed = await client.get("/job-postings")
    return listed.json()["data"][0]["id"]


@pytest.mark.anyio
async def test_tracked_opportunity_and_history_contract_shape(client):
    posting_id = await _seed_posting(client)
    bookmarked = await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "review"})
    history = await client.get(f"/tracker/{posting_id}/transitions")

    assert bookmarked.status_code == 200
    tracked = bookmarked.json()["data"]
    assert set(tracked.keys()) == {
        "job_posting_id",
        "tracker_state",
        "bookmarked",
        "bookmarked_at",
        "updated_at",
    }
    assert isinstance(tracked["job_posting_id"], str)
    assert isinstance(tracked["tracker_state"], str)
    assert isinstance(tracked["bookmarked"], bool)
    assert tracked["bookmarked_at"] is None or isinstance(tracked["bookmarked_at"], str)
    assert isinstance(tracked["updated_at"], str)

    assert history.status_code == 200
    items = history.json()["data"]
    assert len(items) >= 2
    for item in items:
        assert set(item.keys()) == {
            "job_posting_id",
            "from_state",
            "to_state",
            "reason",
            "correlation_id",
            "transitioned_at",
        }
        assert isinstance(item["job_posting_id"], str)
        assert item["from_state"] is None or isinstance(item["from_state"], str)
        assert isinstance(item["to_state"], str)
        assert isinstance(item["reason"], str)
        assert isinstance(item["correlation_id"], str)
        assert isinstance(item["transitioned_at"], str)
    assert [item["transitioned_at"] for item in items] == sorted(
        item["transitioned_at"] for item in items
    )
