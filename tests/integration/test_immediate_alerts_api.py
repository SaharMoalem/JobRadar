from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.recommendation_gating import GatedRecommendation
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


def _seed_repositories() -> tuple[InMemoryJobPostingAdapter, InMemoryGatedRecommendationAdapter]:
    postings = InMemoryJobPostingAdapter()
    high = postings.save_posting(
        JobPosting(
            id="seed-high",
            title="Senior Python Engineer",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/high",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="high",
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.ACTIVE,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    low = postings.save_posting(
        JobPosting(
            id="seed-low",
            title="Junior Role",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/low",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="low",
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.ACTIVE,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations(
        [
            GatedRecommendation(
                job_posting_id=high.id,
                match_score=92,
                profile_version="v1",
                config_version="v1",
                actionable=True,
                gate_trace=(),
                evaluated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            ),
            GatedRecommendation(
                job_posting_id=low.id,
                match_score=70,
                profile_version="v1",
                config_version="v1",
                actionable=True,
                gate_trace=(),
                evaluated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            ),
        ]
    )
    return postings, gated


@pytest.fixture
def app():
    postings, gated = _seed_repositories()
    return create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        job_posting_repository=postings,
        gated_recommendation_repository=gated,
    )


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_immediate_alert_flow_and_idempotency(client):
    config = await client.get("/immediate-alert-config")
    assert config.status_code == 200
    assert config.json()["data"]["alert_threshold"] == 90

    first = await client.post(
        "/alerts/immediate/run",
        json={"run_context": "run-1"},
        headers={"x-correlation-id": "alert-flow-1"},
    )
    second = await client.post(
        "/alerts/immediate/run",
        json={"run_context": "run-1"},
        headers={"x-correlation-id": "alert-flow-2"},
    )

    assert first.status_code == 200
    body = first.json()["data"]
    assert body["triggered_count"] == 1
    assert body["skipped_below_threshold_count"] == 1
    assert body["run_context"] == "run-1"
    for alert in body["alerts"]:
        assert alert["role_summary"]
        assert isinstance(alert["match_score"], int)
        assert alert["deep_link"].startswith("/job-postings/")
        assert alert["match_score"] >= 90

    assert second.status_code == 200
    assert second.json()["data"]["triggered_count"] == 0
    assert second.json()["data"]["skipped_duplicate_count"] == 1

    listed = await client.get("/alerts/immediate")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    metrics = await client.get("/observability/immediate-alert-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["data"]["immediate_alert_runs_total"] == 2


@pytest.mark.anyio
async def test_invalid_alert_config_is_rejected(client):
    response = await client.put("/immediate-alert-config", json={"alert_threshold": 150})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_boolean_alert_threshold_is_rejected(client):
    response = await client.put("/immediate-alert-config", json={"alert_threshold": True})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_threshold_change_affects_alert_output(client):
    await client.put("/immediate-alert-config", json={"alert_threshold": 95})
    strict = await client.post(
        "/alerts/immediate/run",
        json={"run_context": "strict"},
        headers={"x-correlation-id": "strict-1"},
    )
    await client.put("/immediate-alert-config", json={"alert_threshold": 60})
    relaxed = await client.post(
        "/alerts/immediate/run",
        json={"run_context": "relaxed"},
        headers={"x-correlation-id": "relaxed-1"},
    )

    assert strict.json()["data"]["triggered_count"] == 0
    assert relaxed.json()["data"]["triggered_count"] == 2
