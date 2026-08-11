from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_top_recommendation_adapter import (
    InMemoryTopRecommendationAdapter,
)
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState, JobLifecycleTransition
from src.domain.match_scoring import MatchScore
from src.domain.precision_policy import TopRecommendation
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter

NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _seed_app():
    postings = InMemoryJobPostingAdapter()
    new_posting = postings.save_posting(
        JobPosting(
            id="seed-new",
            title="New Role",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/new",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="new",
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.NEW,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    top_posting = postings.save_posting(
        JobPosting(
            id="seed-top",
            title="Top Role",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/top",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="top",
            plugin_id="generic",
            lifecycle_state=JobLifecycleState.ACTIVE,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    postings._transitions = [
        JobLifecycleTransition(
            job_posting_id=new_posting.id,
            from_state=None,
            to_state=JobLifecycleState.NEW,
            reason="seed",
            correlation_id="seed",
            transitioned_at=NOW - timedelta(hours=2),
        )
    ]
    scores = InMemoryMatchScoreAdapter()
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=new_posting.id,
                score=90,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={},
            ),
            MatchScore(
                job_posting_id=top_posting.id,
                score=95,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={},
            ),
        ]
    )
    tops = InMemoryTopRecommendationAdapter()
    tops.replace_recommendations(
        [
            TopRecommendation(
                job_posting_id=top_posting.id,
                match_score=95,
                rank=1,
                suppressed=False,
                suppression_reason=None,
                policy_version="v1",
                gate_config_version="v1",
                profile_version="v1",
                evaluated_at=NOW,
            )
        ]
    )
    return create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        job_posting_repository=postings,
        match_score_repository=scores,
        top_recommendation_repository=tops,
    )


@pytest.fixture
def app():
    return _seed_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_morning_digest_flow(client):
    config = await client.get("/morning-digest-config")
    assert config.status_code == 200
    assert config.json()["data"]["digest_threshold"] == 80
    assert config.json()["data"]["top_n"] == 5

    response = await client.post(
        "/digests/morning/run",
        json={"run_context": "2026-08-11"},
        headers={"x-correlation-id": "digest-flow-1"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data.keys()) >= {
        "new_items",
        "updated_items",
        "expired_items",
        "top_recommendations",
        "is_noop",
    }
    assert len(data["new_items"]) == 1
    assert len(data["top_recommendations"]) == 1
    assert data["is_noop"] is False

    listed = await client.get("/digests/morning")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    metrics = await client.get("/observability/morning-digest-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["data"]["morning_digest_runs_total"] == 1


@pytest.mark.anyio
async def test_invalid_digest_config_is_rejected(client):
    response = await client.put("/morning-digest-config", json={"digest_threshold": 150})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_empty_digest_noop(client):
    empty_app = create_app(compliance_checker=FakeComplianceCheckAdapter())
    async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as ac:
        response = await ac.post(
            "/digests/morning/run",
            json={"run_context": "empty-day"},
            headers={"x-correlation-id": "noop-1"},
        )
    assert response.status_code == 200
    assert response.json()["data"]["is_noop"] is True
