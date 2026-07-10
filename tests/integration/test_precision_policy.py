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
async def test_precision_policy_flow(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "precision-flow-1"},
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
    await client.post("/match-scores/run", headers={"x-correlation-id": "precision-flow-2"})
    await client.post("/recommendations/gating/run", headers={"x-correlation-id": "precision-flow-3"})

    config = await client.get("/recommendation-precision-config")
    assert config.status_code == 200
    assert config.json()["data"]["min_confidence_for_top"] == 85

    precision = await client.post(
        "/recommendations/precision/run",
        headers={"x-correlation-id": "precision-flow-4"},
    )
    assert precision.status_code == 200
    assert "top_recommendations" in precision.json()["data"]

    top = await client.get("/recommendations/top")
    traces = await client.get("/recommendations/precision-traces")
    actionable = await client.get("/recommendations/actionable")
    assert top.status_code == 200
    assert traces.status_code == 200
    assert actionable.status_code == 200
    assert len(top.json()["data"]) <= len(actionable.json()["data"])
    for item in traces.json()["data"]:
        assert item["policy_version"]
        if item["suppressed"]:
            assert item["suppression_reason"]


@pytest.mark.anyio
async def test_invalid_precision_config_is_rejected(client):
    response = await client.put(
        "/recommendation-precision-config",
        json={"min_confidence_for_top": 40},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PRECISION_MIN_CONFIDENCE_OUT_OF_RANGE"


@pytest.mark.anyio
async def test_precision_config_change_affects_top_output(client):
    source_id = await _create_runnable(client, name="Beta", url="https://beta.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "precision-threshold-1"},
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
    await client.post("/match-scores/run", headers={"x-correlation-id": "precision-threshold-2"})
    await client.post("/recommendations/gating/run", headers={"x-correlation-id": "precision-threshold-3"})

    await client.put("/recommendation-precision-config", json={"min_confidence_for_top": 95})
    strict = await client.post(
        "/recommendations/precision/run",
        headers={"x-correlation-id": "precision-threshold-4"},
    )
    await client.put("/recommendation-precision-config", json={"min_confidence_for_top": 60})
    relaxed = await client.post(
        "/recommendations/precision/run",
        headers={"x-correlation-id": "precision-threshold-5"},
    )

    assert strict.status_code == 200
    assert relaxed.status_code == 200
    assert strict.json()["data"]["top_count"] <= relaxed.json()["data"]["top_count"]
