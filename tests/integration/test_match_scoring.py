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
async def test_match_scoring_flow(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "score-flow-1"},
    )

    profile = await client.put(
        "/user-profile",
        json={
            "skills": ["python"],
            "preferred_locations": ["Tel Aviv"],
            "preferred_languages": ["english"],
            "target_seniority": "senior",
        },
    )
    assert profile.status_code == 200

    first = await client.post("/match-scores/run", headers={"x-correlation-id": "score-flow-2"})
    second = await client.post("/match-scores/run", headers={"x-correlation-id": "score-flow-3"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["scores"][0]["score"] == second.json()["data"]["scores"][0]["score"]

    listed = await client.get("/match-scores")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1


@pytest.mark.anyio
async def test_scoring_without_profile_returns_typed_failure(client):
    response = await client.post("/match-scores/run", headers={"x-correlation-id": "score-no-profile"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROFILE_NOT_CONFIGURED"

    listed = await client.get("/match-scores")
    assert listed.json()["data"] == []
