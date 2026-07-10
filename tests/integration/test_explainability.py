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
async def test_explainability_flow(client):
    source_id = await _create_runnable(client, name="Acme", url="https://acme.example.com")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "explain-flow-1"},
    )
    await client.put(
        "/user-profile",
        json={
            "skills": ["sample"],
            "preferred_locations": ["Tel Aviv"],
            "preferred_languages": [],
            "target_seniority": "senior",
        },
    )
    await client.put(
        "/recommendation-gate-config",
        json={
            "enforce_seniority": False,
            "enforce_skill_overlap": False,
            "enforce_language": False,
            "global_threshold": 60,
        },
    )
    await client.post("/match-scores/run", headers={"x-correlation-id": "explain-flow-2"})
    await client.post("/recommendations/gating/run", headers={"x-correlation-id": "explain-flow-3"})
    await client.put("/recommendation-precision-config", json={"min_confidence_for_top": 60})
    await client.post("/recommendations/precision/run", headers={"x-correlation-id": "explain-flow-4"})

    explainability = await client.post(
        "/recommendations/explainability/run",
        headers={"x-correlation-id": "explain-flow-5"},
    )
    assert explainability.status_code == 200
    assert explainability.json()["data"]["promoted_count"] >= 1

    explainable = await client.get("/recommendations/explainable")
    traces = await client.get("/recommendations/explainability-traces")
    assert explainable.status_code == 200
    assert traces.status_code == 200
    assert len(explainable.json()["data"]) >= 1
    assert len(explainable.json()["data"]) <= len(traces.json()["data"])
    for item in traces.json()["data"]:
        if not item["promoted"]:
            assert item["failure_code"]


@pytest.mark.anyio
async def test_explainability_without_profile_returns_typed_failure(client):
    response = await client.post(
        "/recommendations/explainability/run",
        headers={"x-correlation-id": "explain-no-profile"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROFILE_NOT_CONFIGURED"
