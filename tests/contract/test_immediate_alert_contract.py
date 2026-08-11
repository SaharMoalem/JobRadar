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


@pytest.fixture
def app():
    postings = InMemoryJobPostingAdapter()
    posting = postings.save_posting(
        JobPosting(
            id="contract-job",
            title="Backend Engineer",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/contract",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="contract",
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.ACTIVE,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations(
        [
            GatedRecommendation(
                job_posting_id=posting.id,
                match_score=91,
                profile_version="v1",
                config_version="v1",
                actionable=True,
                gate_trace=(),
                evaluated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )
        ]
    )
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
async def test_immediate_alert_contract_shape(client):
    response = await client.post(
        "/alerts/immediate/run",
        json={"run_context": "contract-run"},
        headers={"x-correlation-id": "alert-contract-1"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data.keys()) == {
        "triggered_count",
        "skipped_below_threshold_count",
        "skipped_duplicate_count",
        "skipped_missing_posting_count",
        "run_context",
        "alerts",
    }
    assert isinstance(data["triggered_count"], int)
    assert data["run_context"] == "contract-run"
    assert isinstance(data["alerts"], list)
    assert data["triggered_count"] == 1
    alert = data["alerts"][0]
    assert set(alert.keys()) == {
        "id",
        "job_posting_id",
        "role_summary",
        "match_score",
        "deep_link",
        "run_context",
        "correlation_id",
        "created_at",
    }
    assert isinstance(alert["id"], str)
    assert isinstance(alert["job_posting_id"], str)
    assert isinstance(alert["role_summary"], str)
    assert alert["match_score"] == 91
    assert alert["deep_link"].startswith("/job-postings/")
    assert alert["run_context"] == "contract-run"
    assert alert["correlation_id"] == "alert-contract-1"
    assert isinstance(alert["created_at"], str)
