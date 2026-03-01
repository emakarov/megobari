"""Tests for the dashboard REST API endpoints."""

from __future__ import annotations

import httpx
import pytest

from megobari.api.app import create_api
from megobari.db import Repository, close_db, get_session, init_db


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


@pytest.fixture
def auth_header() -> dict[str, str]:
    """Return a bearer header value for test requests."""
    return {"Authorization": "Bearer test-token-for-api-tests"}


@pytest.fixture
async def api_client(auth_header):
    """Create an httpx.AsyncClient wired to the FastAPI app.

    Seeds a valid dashboard token so authenticated requests succeed.
    """
    app = create_api(bot_data={}, session_manager=None)

    # Seed a valid token
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_dashboard_token("test-client", "test-token-for-api-tests")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------
# GET /api/messages/recent
# ---------------------------------------------------------------


async def test_messages_recent_empty(api_client, auth_header):
    resp = await api_client.get("/api/messages/recent", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_messages_recent_returns_messages(api_client, auth_header):
    # Seed messages in different sessions
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_message("sess-a", "user", "Hello from A")
        await repo.add_message("sess-b", "user", "Hello from B")
        await repo.add_message("sess-a", "assistant", "Reply from A")

    resp = await api_client.get("/api/messages/recent", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # Newest first
    assert data[0]["content"] == "Reply from A"
    assert data[0]["session_name"] == "sess-a"
    assert data[0]["role"] == "assistant"
    # All expected keys present
    for msg in data:
        assert "id" in msg
        assert "session_name" in msg
        assert "role" in msg
        assert "content" in msg
        assert "summarized" in msg
        assert "created_at" in msg


async def test_messages_recent_respects_limit(api_client, auth_header):
    async with get_session() as s:
        repo = Repository(s)
        for i in range(10):
            await repo.add_message("sess", "user", f"msg-{i}")

    resp = await api_client.get(
        "/api/messages/recent", headers=auth_header, params={"limit": 3}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["content"] == "msg-9"


async def test_messages_recent_limit_validation(api_client, auth_header):
    # limit < 1 should fail validation
    resp = await api_client.get(
        "/api/messages/recent", headers=auth_header, params={"limit": 0}
    )
    assert resp.status_code == 422

    # limit > 200 should fail validation
    resp = await api_client.get(
        "/api/messages/recent", headers=auth_header, params={"limit": 201}
    )
    assert resp.status_code == 422


async def test_messages_recent_unauthenticated(api_client):
    resp = await api_client.get("/api/messages/recent")
    assert resp.status_code == 401


async def test_messages_recent_bad_token(api_client):
    resp = await api_client.get(
        "/api/messages/recent",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401
