import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import ExplainableRecommendationResponse, create_app
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


@pytest.fixture
def app():
    return create_app(compliance_checker=FakeComplianceCheckAdapter())


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_explainable_recommendation_response_contract(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "explain-contract-1"},
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
    await client.post("/match-scores/run", headers={"x-correlation-id": "explain-contract-2"})
    await client.post("/recommendations/gating/run", headers={"x-correlation-id": "explain-contract-3"})
    await client.put("/recommendation-precision-config", json={"min_confidence_for_top": 60})
    await client.post("/recommendations/precision/run", headers={"x-correlation-id": "explain-contract-4"})
    await client.post(
        "/recommendations/explainability/run",
        headers={"x-correlation-id": "explain-contract-5"},
    )

    response = await client.get("/recommendations/explainable")
    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1
    for item in response.json()["data"]:
        parsed = ExplainableRecommendationResponse.model_validate(item)
        assert parsed.promoted is True
        assert parsed.note is not None
        assert isinstance(parsed.note.match_rationale, str)
        assert isinstance(parsed.note.missing_skills, list)
        assert isinstance(parsed.note.interview_probability_pct, int)
        assert isinstance(parsed.note.effort_estimate, str)
        assert parsed.scoring_config_version
        assert parsed.generated_at
