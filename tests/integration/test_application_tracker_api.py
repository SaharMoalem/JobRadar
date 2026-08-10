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
        headers={"x-correlation-id": "tracker-seed"},
    )
    listed = await client.get("/job-postings")
    return listed.json()["data"][0]["id"]


@pytest.mark.anyio
async def test_bookmark_unbookmark_persists_and_keeps_metadata(client):
    posting_id = await _seed_posting(client)

    bookmarked = await client.post(
        "/tracker/bookmarks",
        json={"job_posting_id": posting_id},
        headers={"x-correlation-id": "bm-1"},
    )
    assert bookmarked.status_code == 200
    assert bookmarked.json()["data"]["bookmarked"] is True
    assert bookmarked.json()["data"]["tracker_state"] == "new"

    listed = await client.get("/tracker/bookmarks")
    assert len(listed.json()["data"]) == 1

    await client.post(
        f"/tracker/{posting_id}/transitions",
        json={"to_state": "review"},
        headers={"x-correlation-id": "tr-1"},
    )
    unbookmarked = await client.delete(f"/tracker/bookmarks/{posting_id}")
    assert unbookmarked.status_code == 200
    assert unbookmarked.json()["data"]["bookmarked"] is False
    assert unbookmarked.json()["data"]["tracker_state"] == "review"

    bookmarks = await client.get("/tracker/bookmarks")
    tracked = await client.get("/tracker")
    assert bookmarks.json()["data"] == []
    assert len(tracked.json()["data"]) == 1


@pytest.mark.anyio
async def test_valid_and_invalid_tracker_transitions(client):
    posting_id = await _seed_posting(client)
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})

    valid = await client.post(
        f"/tracker/{posting_id}/transitions",
        json={"to_state": "review", "reason": "start_review"},
        headers={"x-correlation-id": "tr-valid"},
    )
    invalid = await client.post(
        f"/tracker/{posting_id}/transitions",
        json={"to_state": "submitted"},
        headers={"x-correlation-id": "tr-invalid"},
    )

    assert valid.status_code == 200
    assert valid.json()["data"]["tracker_state"] == "review"
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "TRACKER_TRANSITION_INVALID"


@pytest.mark.anyio
async def test_tracker_history_is_chronological(client):
    posting_id = await _seed_posting(client)
    await client.post(
        "/tracker/bookmarks",
        json={"job_posting_id": posting_id},
        headers={"x-correlation-id": "hist-0"},
    )
    await client.post(
        f"/tracker/{posting_id}/transitions",
        json={"to_state": "review"},
        headers={"x-correlation-id": "hist-1"},
    )
    await client.post(
        f"/tracker/{posting_id}/transitions",
        json={"to_state": "apply"},
        headers={"x-correlation-id": "hist-2"},
    )

    history = await client.get(f"/tracker/{posting_id}/transitions")
    assert history.status_code == 200
    items = history.json()["data"]
    assert [item["to_state"] for item in items] == ["new", "review", "apply"]
    assert [item["from_state"] for item in items] == [None, "new", "review"]
    timestamps = [item["transitioned_at"] for item in items]
    assert timestamps == sorted(timestamps)


@pytest.mark.anyio
async def test_rebookmark_after_unbookmark_preserves_tracker_state(client):
    posting_id = await _seed_posting(client)
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "review"})
    await client.delete(f"/tracker/bookmarks/{posting_id}")

    restored = await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    bookmarks = await client.get("/tracker/bookmarks")

    assert restored.status_code == 200
    assert restored.json()["data"]["bookmarked"] is True
    assert restored.json()["data"]["tracker_state"] == "review"
    assert len(bookmarks.json()["data"]) == 1


@pytest.mark.anyio
async def test_full_pipeline_to_submitted_and_closed(client):
    posting_id = await _seed_posting(client)
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    for state in ("review", "apply", "submitted", "closed"):
        response = await client.post(
            f"/tracker/{posting_id}/transitions",
            json={"to_state": state},
        )
        assert response.status_code == 200
        assert response.json()["data"]["tracker_state"] == state

    history = await client.get(f"/tracker/{posting_id}/transitions")
    assert [item["to_state"] for item in history.json()["data"]] == [
        "new",
        "review",
        "apply",
        "submitted",
        "closed",
    ]


@pytest.mark.anyio
async def test_tracker_typed_errors(client):
    posting_id = await _seed_posting(client)

    unknown = await client.post("/tracker/bookmarks", json={"job_posting_id": "missing-job"})
    missing_unbookmark = await client.delete("/tracker/bookmarks/missing-job")
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    invalid_state = await client.post(
        f"/tracker/{posting_id}/transitions",
        json={"to_state": "not-a-state"},
    )

    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "TRACKER_JOB_POSTING_NOT_FOUND"
    assert missing_unbookmark.status_code == 404
    assert missing_unbookmark.json()["error"]["code"] == "TRACKER_NOT_FOUND"
    assert invalid_state.status_code == 400
    assert invalid_state.json()["error"]["code"] == "TRACKER_STATE_INVALID"
