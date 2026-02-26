"""Tests for the memory recall module."""

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.recall import build_recall_context


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


async def test_recall_empty():
    """No summaries or memories returns None."""
    result = await build_recall_context("empty_session")
    assert result is None


async def test_recall_with_summaries():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(
            session_name="sess",
            summary="Built MCP tools for sgerp",
            short_summary="Built MCP tools",
        )
        await repo.add_summary(
            session_name="sess",
            summary="Added busy emoji to bot and fixed streaming",
            short_summary="Added busy emoji",
        )

    result = await build_recall_context("sess")
    assert result is not None
    # Should use short_summary, not full summary
    assert "Built MCP tools" in result
    assert "Added busy emoji" in result
    assert "Previous conversation summaries" in result
    # Full summary text should NOT be in recall (short_summary is preferred)
    assert "fixed streaming" not in result


async def test_recall_with_memories():
    async with get_session() as s:
        repo = Repository(s)
        await repo.set_memory("preference", "language", "Python")
        await repo.set_memory("fact", "project", "megobari bot")

    result = await build_recall_context("any_session")
    assert result is not None
    assert "Python" in result
    assert "megobari bot" in result
    assert "Known facts" in result


async def test_recall_with_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(
            name="dev",
            system_prompt="You are a senior Python developer",
            is_default=True,
        )

    result = await build_recall_context("sess")
    assert result is not None
    assert "senior Python developer" in result
    assert "Active persona" in result


async def test_recall_combined():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(session_name="sess", summary="Did X and Y")
        await repo.set_memory("pref", "lang", "Python")
        await repo.create_persona(
            name="dev", system_prompt="Be concise", is_default=True
        )

    result = await build_recall_context("sess")
    assert "Did X and Y" in result
    assert "Python" in result
    assert "Be concise" in result


async def test_recall_only_current_session_summaries():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(session_name="sess_a", summary="Summary A")
        await repo.add_summary(session_name="sess_b", summary="Summary B")

    result = await build_recall_context("sess_a")
    assert "Summary A" in result
    assert "Summary B" not in result


async def test_recall_with_user_memories():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=42)
        await repo.set_memory("pref", "tz", "Asia/Tokyo", user_id=user.id)

    result = await build_recall_context("sess", user_id=1)
    # user_id=1 is the DB id (first user created)
    assert result is not None
    assert "Asia/Tokyo" in result


async def test_recall_falls_back_to_full_summary():
    """When short_summary is None, recall uses the full summary."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(
            session_name="sess",
            summary="Full detailed summary text here",
            # short_summary intentionally omitted (None)
        )

    result = await build_recall_context("sess")
    assert result is not None
    assert "Full detailed summary text here" in result


async def test_recall_survives_db_error():
    """Should return None on error, not raise."""
    await close_db()
    result = await build_recall_context("sess")
    assert result is None
    await init_db("sqlite+aiosqlite://")
