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
async def test_recommendation_gating_flow(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "gating-flow-1"},
    )

    await client.put(
        "/user-profile",
        json={
            "skills": ["python"],
            "preferred_locations": ["Tel Aviv"],
            "preferred_languages": ["english"],
            "target_seniority": "senior",
        },
    )
    await client.post("/match-scores/run", headers={"x-correlation-id": "gating-flow-2"})

    config = await client.get("/recommendation-gate-config")
    assert config.status_code == 200
    assert config.json()["data"]["global_threshold"] == 80

    gating = await client.post("/recommendations/gating/run", headers={"x-correlation-id": "gating-flow-3"})
    assert gating.status_code == 200
    assert "recommendations" in gating.json()["data"]
    for recommendation in gating.json()["data"]["recommendations"]:
        assert recommendation["gate_trace"]
        if not recommendation["actionable"]:
            assert any(entry["passed"] is False for entry in recommendation["gate_trace"])

    all_items = await client.get("/recommendations")
    actionable = await client.get("/recommendations/actionable")
    assert all_items.status_code == 200
    assert actionable.status_code == 200
    assert len(all_items.json()["data"]) >= len(actionable.json()["data"])


@pytest.mark.anyio
async def test_invalid_gate_config_is_rejected(client):
    response = await client.put(
        "/recommendation-gate-config",
        json={"global_threshold": 40},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "GATE_THRESHOLD_OUT_OF_RANGE"


@pytest.mark.anyio
async def test_gating_without_profile_returns_typed_failure(client):
    response = await client.post("/recommendations/gating/run", headers={"x-correlation-id": "gating-no-profile"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROFILE_NOT_CONFIGURED"

    listed = await client.get("/recommendations")
    assert listed.json()["data"] == []


@pytest.mark.anyio
async def test_threshold_change_affects_actionable_set(client):
    source_id = await _create_runnable(client, name="Beta", url="https://beta.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "gating-threshold-1"},
    )
    await client.put(
        "/user-profile",
        json={
            "skills": ["python"],
            "preferred_locations": ["Tel Aviv"],
            "preferred_languages": [],
            "target_seniority": "senior",
        },
    )
    await client.post("/match-scores/run", headers={"x-correlation-id": "gating-threshold-2"})

    await client.put("/recommendation-gate-config", json={"global_threshold": 95})
    strict = await client.post("/recommendations/gating/run", headers={"x-correlation-id": "gating-threshold-3"})
    await client.put("/recommendation-gate-config", json={"global_threshold": 60})
    relaxed = await client.post("/recommendations/gating/run", headers={"x-correlation-id": "gating-threshold-4"})

    assert strict.status_code == 200
    assert relaxed.status_code == 200
    assert strict.json()["data"]["actionable_count"] <= relaxed.json()["data"]["actionable_count"]
