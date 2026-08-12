from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_top_recommendation_adapter import (
    InMemoryTopRecommendationAdapter,
)
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState, JobLifecycleTransition
from src.domain.match_scoring import MatchScore
from src.domain.precision_policy import TopRecommendation
from src.domain.recommendation_gating import GatedRecommendation
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter

NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


@pytest.fixture
def app():
    postings = InMemoryJobPostingAdapter()
    posting = postings.save_posting(
        JobPosting(
            id="notify-job",
            title="Backend Engineer",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/notify",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="notify",
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
                match_score=93,
                profile_version="v1",
                config_version="v1",
                actionable=True,
                gate_trace=(),
                evaluated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        ]
    )
    return create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        job_posting_repository=postings,
        gated_recommendation_repository=gated,
    )


@pytest.fixture
def digest_app():
    postings = InMemoryJobPostingAdapter()
    posting = postings.save_posting(
        JobPosting(
            id="digest-notify-job",
            title="Digest Role",
            company="Acme",
            location="Tel Aviv",
            url="https://jobs.example.com/digest",
            posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            career_source_id="src-1",
            external_id="digest-notify",
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
            transitioned_at=NOW - timedelta(hours=2),
        )
    ]
    scores = InMemoryMatchScoreAdapter()
    scores.replace_scores(
        [
            MatchScore(
                job_posting_id=posting.id,
                score=90,
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
                match_score=90,
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
async def test_notification_deliver_flow(client):
    alert_run = await client.post(
        "/alerts/immediate/run",
        json={"run_context": "notify-run"},
        headers={"x-correlation-id": "notify-1"},
    )
    assert alert_run.status_code == 200
    assert alert_run.json()["data"]["triggered_count"] == 1

    delivered = await client.post(
        "/notifications/deliver",
        json={"kind": "immediate_alert", "run_context": "notify-run"},
        headers={"x-correlation-id": "notify-2"},
    )
    assert delivered.status_code == 200
    body = delivered.json()["data"]
    assert body["delivered_count"] == 2
    assert {item["channel_id"] for item in body["deliveries"]} == {"in_app", "email"}

    inbox = await client.get("/notifications/in-app")
    assert inbox.status_code == 200
    assert len(inbox.json()["data"]) == 1

    all_deliveries = await client.get("/notifications/deliveries")
    assert len(all_deliveries.json()["data"]) == 2

    metrics = await client.get("/observability/notification-metrics")
    assert metrics.json()["data"]["notification_deliver_runs_total"] == 1


@pytest.mark.anyio
async def test_unknown_channel_rejected(client):
    response = await client.post(
        "/notifications/deliver",
        json={"kind": "immediate_alert", "channels": ["sms"]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NOTIFICATION_CHANNEL_UNKNOWN"


@pytest.fixture
async def digest_client(digest_app):
    async with AsyncClient(transport=ASGITransport(app=digest_app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_morning_digest_notification_deliver_flow(digest_client):
    digest_run = await digest_client.post(
        "/digests/morning/run",
        json={"run_context": "digest-notify-run"},
        headers={"x-correlation-id": "digest-notify-1"},
    )
    assert digest_run.status_code == 200

    delivered = await digest_client.post(
        "/notifications/deliver",
        json={"kind": "morning_digest", "run_context": "digest-notify-run"},
        headers={"x-correlation-id": "digest-notify-2"},
    )
    assert delivered.status_code == 200
    body = delivered.json()["data"]
    assert body["delivered_count"] == 2
    assert body["kind"] == "morning_digest"
    assert {item["channel_id"] for item in body["deliveries"]} == {"in_app", "email"}
