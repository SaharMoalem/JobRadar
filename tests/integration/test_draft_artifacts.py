import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.adapters.observability.structured_draft_artifact_telemetry_adapter import (
    StructuredDraftArtifactTelemetryAdapter,
)
from src.adapters.persistence.in_memory_application_tracker_adapter import (
    InMemoryApplicationTrackerAdapter,
)
from src.adapters.persistence.in_memory_draft_artifact_adapter import InMemoryDraftArtifactAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class FailingDraftGenerator:
    def generate(self, *, kind, posting, profile):
        return ""


@pytest.fixture
def app():
    return create_app(compliance_checker=FakeComplianceCheckAdapter())


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _seed_review_posting(client) -> str:
    created = await client.post(
        "/career-sources",
        json={"name": "Acme", "base_url": "https://acme.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "draft-seed"},
    )
    posting_id = (await client.get("/job-postings")).json()["data"][0]["id"]
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})
    await client.post(f"/tracker/{posting_id}/transitions", json={"to_state": "review"})
    return posting_id


@pytest.mark.anyio
async def test_generate_draft_artifacts_for_review_context(client):
    posting_id = await _seed_review_posting(client)
    response = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "recruiter_message"},
        headers={"x-correlation-id": "draft-gen-1"},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "draft"
    assert body["is_latest"] is True
    assert body["job_posting_id"] == posting_id
    assert "created_at" in body
    assert "source_reference" in body
    assert body["content"].startswith("[DRAFT]")


@pytest.mark.anyio
async def test_draft_history_keeps_prior_and_marks_latest(client):
    posting_id = await _seed_review_posting(client)
    first = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "cv_improvement"},
    )
    second = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "cv_improvement"},
    )
    history = await client.get("/draft-artifacts", params={"job_posting_id": posting_id})
    latest = await client.get(
        "/draft-artifacts",
        params={"job_posting_id": posting_id, "latest_only": True},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    items = history.json()["data"]
    assert len(items) == 2
    assert items[0]["is_latest"] is False
    assert items[1]["is_latest"] is True
    assert items[1]["id"] == second.json()["data"]["id"]
    assert len(latest.json()["data"]) == 1
    assert latest.json()["data"][0]["id"] == second.json()["data"]["id"]


@pytest.mark.anyio
async def test_failed_generation_keeps_existing_artifacts():
    postings = InMemoryJobPostingAdapter()
    trackers = InMemoryApplicationTrackerAdapter()
    drafts = InMemoryDraftArtifactAdapter()
    telemetry = StructuredDraftArtifactTelemetryAdapter()

    app = create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        job_posting_repository=postings,
        application_tracker_repository=trackers,
        draft_artifact_repository=drafts,
        draft_artifact_telemetry=telemetry,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        posting_id = await _seed_review_posting(client)
        ok = await client.post(
            "/draft-artifacts/generate",
            json={"job_posting_id": posting_id, "kind": "interview_prep"},
        )
        assert ok.status_code == 200
        kept_id = ok.json()["data"]["id"]

    failing_app = create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        job_posting_repository=postings,
        application_tracker_repository=trackers,
        draft_artifact_repository=drafts,
        draft_artifact_telemetry=telemetry,
        draft_artifact_generator=FailingDraftGenerator(),
    )
    async with AsyncClient(transport=ASGITransport(app=failing_app), base_url="http://test") as client:
        failed = await client.post(
            "/draft-artifacts/generate",
            json={"job_posting_id": posting_id, "kind": "interview_prep"},
            headers={"x-correlation-id": "draft-fail"},
        )
        history = await client.get("/draft-artifacts", params={"job_posting_id": posting_id})
        metrics = await client.get("/observability/draft-artifact-metrics")

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "DRAFT_GENERATION_FAILED"
    assert len(history.json()["data"]) == 1
    assert history.json()["data"][0]["id"] == kept_id
    assert history.json()["data"][0]["is_latest"] is True
    assert metrics.json()["data"]["draft_generation_failures_total"] >= 1


@pytest.mark.anyio
async def test_generation_requires_review_or_apply_context(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Beta", "base_url": "https://beta.example.com", "plugin_id": "generic"},
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(f"/career-sources/{source_id}/execute", headers={"x-correlation-id": "ctx"})
    posting_id = (await client.get("/job-postings")).json()["data"][0]["id"]
    await client.post("/tracker/bookmarks", json={"job_posting_id": posting_id})

    response = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "recruiter_message"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRAFT_TRACKER_CONTEXT_INVALID"


@pytest.mark.anyio
async def test_get_draft_by_id_and_typed_not_found_errors(client):
    posting_id = await _seed_review_posting(client)
    created = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "recruiter_message"},
    )
    artifact_id = created.json()["data"]["id"]

    fetched = await client.get(f"/draft-artifacts/{artifact_id}")
    missing_posting = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": "missing-job", "kind": "recruiter_message"},
    )

    created_source = await client.post(
        "/career-sources",
        json={"name": "Gamma", "base_url": "https://gamma.example.com", "plugin_id": "generic"},
    )
    source_id = created_source.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "no-track"},
    )
    untracked_id = [
        item["id"]
        for item in (await client.get("/job-postings")).json()["data"]
        if item["id"] != posting_id
    ][0]
    untracked = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": untracked_id, "kind": "recruiter_message"},
    )
    invalid_kind = await client.post(
        "/draft-artifacts/generate",
        json={"job_posting_id": posting_id, "kind": "not_a_kind"},
        headers={"x-correlation-id": "bad-kind"},
    )
    metrics = await client.get("/observability/draft-artifact-metrics")

    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == artifact_id
    assert missing_posting.status_code == 404
    assert missing_posting.json()["error"]["code"] == "DRAFT_JOB_POSTING_NOT_FOUND"
    assert untracked.status_code == 409
    assert untracked.json()["error"]["code"] == "DRAFT_TRACKER_NOT_FOUND"
    assert invalid_kind.status_code == 400
    assert invalid_kind.json()["error"]["code"] == "DRAFT_KIND_INVALID"
    assert metrics.json()["data"]["draft_generation_failures_total"] >= 3
