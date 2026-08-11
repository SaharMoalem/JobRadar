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
            lifecycle_state=JobLifecycleState.NEW,
            completeness=JobPostingCompleteness.COMPLETE,
        )
    )
    postings._transitions = [
        JobLifecycleTransition(
            job_posting_id=posting.id,
            from_state=None,
            to_state=JobLifecycleState.NEW,
            reason="seed",
            correlation_id="seed",
            transitioned_at=NOW - timedelta(hours=1),
        )
    ]
    scores = InMemoryMatchScoreAdapter()
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=posting.id,
                score=88,
                profile_version="v1",
                config_version="v1",
                signal_breakdown={},
            )
        ]
    )
    tops = InMemoryTopRecommendationAdapter()
    tops.replace_recommendations(
        [
            TopRecommendation(
                job_posting_id=posting.id,
                match_score=88,
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
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_morning_digest_contract_shape(client):
    config = await client.get("/morning-digest-config")
    assert config.status_code == 200
    assert set(config.json()["data"].keys()) == {
        "config_version",
        "digest_threshold",
        "digest_window_hours",
        "top_n",
    }

    response = await client.post(
        "/digests/morning/run",
        json={"run_context": "contract-day"},
        headers={"x-correlation-id": "digest-contract-1"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data.keys()) == {
        "id",
        "run_context",
        "correlation_id",
        "digest_date",
        "is_noop",
        "skipped_below_threshold_count",
        "skipped_missing_score_count",
        "skipped_missing_posting_count",
        "new_items",
        "updated_items",
        "expired_items",
        "top_recommendations",
        "created_at",
    }
    assert isinstance(data["new_items"], list)
    assert isinstance(data["updated_items"], list)
    assert isinstance(data["expired_items"], list)
    assert isinstance(data["top_recommendations"], list)
    assert data["run_context"] == "contract-day"
    assert data["correlation_id"] == "digest-contract-1"
    item = data["new_items"][0]
    assert set(item.keys()) == {
        "job_posting_id",
        "role_summary",
        "match_score",
        "deep_link",
        "lifecycle_state",
        "transitioned_at",
        "rank",
    }
