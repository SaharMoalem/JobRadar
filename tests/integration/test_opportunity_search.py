import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from src.domain.career_source import CareerSource
from src.domain.crawl import CrawlPluginResult, RawCrawlRecord
from tests.support.fake_compliance_check_adapter import FakeComplianceCheckAdapter


class SearchFixtureCrawlerPlugin:
    plugin_id = "search-fixture"

    def crawl(self, source: CareerSource, *, correlation_id: str) -> CrawlPluginResult:
        return CrawlPluginResult(
            plugin_id=self.plugin_id,
            records=[
                RawCrawlRecord(
                    external_id=f"{source.id}-backend",
                    title="Backend Engineer",
                    url=f"https://jobs.example.com/{source.id}/backend",
                    raw_payload={
                        "company": source.name,
                        "location": "Tel Aviv, Israel",
                        "role_family": "engineering",
                        "work_model": "hybrid",
                        "posted_at": "2026-07-01T08:00:00+00:00",
                    },
                ),
                RawCrawlRecord(
                    external_id=f"{source.id}-data",
                    title="Data Analyst",
                    url=f"https://jobs.example.com/{source.id}/data",
                    raw_payload={
                        "company": source.name,
                        "location": "Remote, Israel",
                        "role_family": "data",
                        "work_model": "remote",
                        "posted_at": "2026-07-01T08:00:00+00:00",
                    },
                ),
                RawCrawlRecord(
                    external_id=f"{source.id}-pm",
                    title="Product Manager",
                    url=f"https://jobs.example.com/{source.id}/pm",
                    raw_payload={
                        "company": source.name,
                        "location": "Haifa, Israel",
                        "role_family": "product",
                        "work_model": "on_site",
                        "posted_at": "2026-07-01T08:00:00+00:00",
                    },
                ),
            ],
        )


@pytest.fixture
def app():
    return create_app(
        compliance_checker=FakeComplianceCheckAdapter(),
        extra_plugins=[SearchFixtureCrawlerPlugin()],
    )


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _seed_fixture_postings(client):
    created = await client.post(
        "/career-sources",
        json={
            "name": "FixtureCo",
            "base_url": "https://fixture.example.com",
            "plugin_id": "search-fixture",
        },
    )
    source_id = created.json()["data"]["id"]
    await client.post(f"/career-sources/{source_id}/compliance/approve")
    await client.post(f"/career-sources/{source_id}/enable")
    await client.post(
        f"/career-sources/{source_id}/execute",
        headers={"x-correlation-id": "search-fixture-seed"},
    )


@pytest.mark.anyio
async def test_search_filters_role_family_location_and_work_model(client):
    await _seed_fixture_postings(client)

    response = await client.post(
        "/opportunities/search",
        json={
            "role_family": "data",
            "location": "remote",
            "work_model": "remote",
            "session_id": "workspace-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total_count"] == 1
    assert body["data"]["empty"] is False
    assert body["data"]["items"][0]["role_family"] == "data"
    assert body["meta"]["session_id"] == "workspace-1"
    assert body["meta"]["applied_filter"]["work_model"] == "remote"


@pytest.mark.anyio
async def test_search_empty_state_has_no_error(client):
    await _seed_fixture_postings(client)

    response = await client.post(
        "/opportunities/search",
        json={
            "role_family": "design",
            "session_id": "workspace-empty",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["items"] == []
    assert body["data"]["total_count"] == 0
    assert body["data"]["empty"] is True


@pytest.mark.anyio
async def test_filter_state_round_trip_is_deterministic(client):
    await _seed_fixture_postings(client)

    first = await client.post(
        "/opportunities/search",
        json={
            "role_family": "engineering",
            "work_model": "hybrid",
            "session_id": "workspace-roundtrip",
        },
    )
    restored = await client.get("/opportunity-filter-state", params={"session_id": "workspace-roundtrip"})
    second = await client.post(
        "/opportunities/search",
        json={
            "role_family": "engineering",
            "work_model": "hybrid",
            "session_id": "workspace-roundtrip",
        },
    )

    assert first.status_code == 200
    assert restored.status_code == 200
    assert second.status_code == 200
    assert restored.json()["data"]["criteria"]["role_family"] == "engineering"
    assert first.json()["data"]["items"] == second.json()["data"]["items"]


@pytest.mark.anyio
async def test_search_score_range_filter(client):
    await _seed_fixture_postings(client)
    await client.put(
        "/user-profile",
        json={
            "skills": ["engineering"],
            "preferred_locations": ["Tel Aviv"],
            "preferred_languages": [],
            "target_seniority": "senior",
        },
    )
    await client.post("/match-scores/run", headers={"x-correlation-id": "search-score-1"})

    all_results = await client.post("/opportunities/search", json={"session_id": "score-session"})
    filtered = await client.post(
        "/opportunities/search",
        json={"min_score": 99, "max_score": 100, "session_id": "score-session"},
    )

    assert all_results.status_code == 200
    assert filtered.status_code == 200
    assert all_results.json()["data"]["total_count"] >= 1
    assert filtered.json()["data"]["empty"] is True


@pytest.mark.anyio
async def test_search_freshness_and_lifecycle_filters(client):
    await _seed_fixture_postings(client)

    stale = await client.post(
        "/opportunities/search",
        json={"freshness_days": 7, "session_id": "freshness-session"},
    )
    fresh_enough = await client.post(
        "/opportunities/search",
        json={"freshness_days": 90, "session_id": "freshness-session"},
    )
    expired_only = await client.post(
        "/opportunities/search",
        json={"lifecycle_states": ["expired"], "session_id": "status-session"},
    )

    assert stale.status_code == 200
    assert fresh_enough.status_code == 200
    assert expired_only.status_code == 200
    assert stale.json()["data"]["empty"] is True
    assert fresh_enough.json()["data"]["total_count"] >= 1
    assert expired_only.json()["data"]["empty"] is True


@pytest.mark.anyio
async def test_search_validation_error_does_not_persist_state(client):
    response = await client.post(
        "/opportunities/search",
        json={"min_score": 90, "max_score": 10, "session_id": "bad-search"},
    )
    restored = await client.get("/opportunity-filter-state", params={"session_id": "bad-search"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SEARCH_SCORE_RANGE_INVALID"
    assert restored.json()["data"] is None


@pytest.mark.anyio
async def test_put_filter_state_rejects_invalid_scores(client):
    response = await client.put(
        "/opportunity-filter-state",
        json={"min_score": 150, "session_id": "bad-put"},
    )
    restored = await client.get("/opportunity-filter-state", params={"session_id": "bad-put"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SEARCH_SCORE_OUT_OF_RANGE"
    assert restored.json()["data"] is None
