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


async def _seed_stub_posting(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "contract-search-seed"},
    )


@pytest.mark.anyio
async def test_opportunity_search_contract_shape(client):
    await _seed_stub_posting(client)
    response = await client.post("/opportunities/search", json={"session_id": "contract-1"})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"data", "error", "meta"}
    assert set(body["data"].keys()) == {"items", "total_count", "empty"}
    assert isinstance(body["data"]["items"], list)
    assert isinstance(body["data"]["total_count"], int)
    assert isinstance(body["data"]["empty"], bool)
    assert body["data"]["total_count"] >= 1
    assert body["data"]["empty"] is False
    assert body["meta"]["session_id"] == "contract-1"
    assert isinstance(body["meta"]["applied_filter"], dict)

    item = body["data"]["items"][0]
    assert set(item.keys()) == {
        "job_posting_id",
        "title",
        "company",
        "location",
        "url",
        "posted_at",
        "lifecycle_state",
        "role_family",
        "work_model",
        "match_score",
    }
    assert isinstance(item["job_posting_id"], str)
    assert isinstance(item["title"], str)
    assert isinstance(item["company"], str)
    assert isinstance(item["location"], str)
    assert isinstance(item["url"], str)
    assert item["posted_at"] is None or isinstance(item["posted_at"], str)
    assert isinstance(item["lifecycle_state"], str)
    assert isinstance(item["role_family"], str)
    assert isinstance(item["work_model"], str)
    assert item["match_score"] is None or isinstance(item["match_score"], int)


@pytest.mark.anyio
async def test_opportunity_filter_state_contract_shape(client):
    saved = await client.put(
        "/opportunity-filter-state",
        json={"location": "Tel Aviv", "session_id": "contract-2"},
    )
    fetched = await client.get("/opportunity-filter-state", params={"session_id": "contract-2"})

    assert saved.status_code == 200
    assert fetched.status_code == 200
    saved_body = saved.json()["data"]
    fetched_body = fetched.json()["data"]
    for body in (saved_body, fetched_body):
        assert set(body.keys()) == {"session_id", "criteria", "updated_at"}
        assert body["session_id"] == "contract-2"
        assert isinstance(body["criteria"], dict)
        assert isinstance(body["updated_at"], str)
