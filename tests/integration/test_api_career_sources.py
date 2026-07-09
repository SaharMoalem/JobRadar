import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_api_envelope_and_lifecycle(client):
    created = await client.post(
        "/career-sources",
        json={"name": "Company API", "base_url": "https://api.example.com/jobs"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["error"] is None
    source_id = payload["data"]["id"]

    enabled = await client.post(f"/career-sources/{source_id}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["data"]["status"] == "enabled"

    listed = await client.get("/career-sources")
    assert listed.status_code == 200
    assert isinstance(listed.json()["data"], list)


@pytest.mark.anyio
async def test_api_rejects_invalid_url_with_400(client):
    response = await client.post("/career-sources", json={"name": "Bad", "base_url": "ftp://oops"})
    assert response.status_code == 400
    payload = response.json()
    assert payload["data"] is None
    assert payload["error"]["code"] == "SOURCE_URL_INVALID"


@pytest.mark.anyio
async def test_api_not_found_returns_404(client):
    response = await client.post("/career-sources/missing-id/enable")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SOURCE_NOT_FOUND"


@pytest.mark.anyio
async def test_api_enable_limit_returns_409():
    app = create_app(max_enabled_sources=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/career-sources",
            json={"name": "A", "base_url": "https://a.example.com"},
        )
        second = await client.post(
            "/career-sources",
            json={"name": "B", "base_url": "https://b.example.com"},
        )
        await client.post(f"/career-sources/{first.json()['data']['id']}/enable")
        limit_response = await client.post(f"/career-sources/{second.json()['data']['id']}/enable")
    assert limit_response.status_code == 409
    assert limit_response.json()["error"]["code"] == "SOURCE_ENABLED_LIMIT_EXCEEDED"
