"""Tests for the memory recall module."""

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.recall import RecallResult, build_recall_context


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


async def test_recall_empty():
    """No summaries or memories returns RecallResult with None context."""
    result = await build_recall_context("empty_session")
    assert isinstance(result, RecallResult)
    assert result.context is None
    assert result.persona_mcp_servers == []
    assert result.persona_skills == []


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
    assert result.context is not None
    # Should use short_summary, not full summary
    assert "Built MCP tools" in result.context
    assert "Added busy emoji" in result.context
    assert "Previous conversation summaries" in result.context
    # Full summary text should NOT be in recall (short_summary is preferred)
    assert "fixed streaming" not in result.context


async def test_recall_with_memories():
    async with get_session() as s:
        repo = Repository(s)
        await repo.set_memory("preference", "language", "Python")
        await repo.set_memory("fact", "project", "megobari bot")

    result = await build_recall_context("any_session")
    assert result.context is not None
    assert "Python" in result.context
    assert "megobari bot" in result.context
    assert "Known facts" in result.context


async def test_recall_with_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(
            name="dev",
            system_prompt="You are a senior Python developer",
            is_default=True,
        )

    result = await build_recall_context("sess")
    assert result.context is not None
    assert "senior Python developer" in result.context
    assert "Active persona" in result.context


async def test_recall_combined():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(session_name="sess", summary="Did X and Y")
        await repo.set_memory("pref", "lang", "Python")
        await repo.create_persona(
            name="dev", system_prompt="Be concise", is_default=True
        )

    result = await build_recall_context("sess")
    assert "Did X and Y" in result.context
    assert "Python" in result.context
    assert "Be concise" in result.context


async def test_recall_only_current_session_summaries():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(session_name="sess_a", summary="Summary A")
        await repo.add_summary(session_name="sess_b", summary="Summary B")

    result = await build_recall_context("sess_a")
    assert "Summary A" in result.context
    assert "Summary B" not in result.context


async def test_recall_with_user_memories():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=42)
        await repo.set_memory("pref", "tz", "Asia/Tokyo", user_id=user.id)

    result = await build_recall_context("sess", user_id=1)
    # user_id=1 is the DB id (first user created)
    assert result.context is not None
    assert "Asia/Tokyo" in result.context


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
    assert result.context is not None
    assert "Full detailed summary text here" in result.context


async def test_recall_survives_db_error():
    """Should return RecallResult with None context on error."""
    await close_db()
    result = await build_recall_context("sess")
    assert isinstance(result, RecallResult)
    assert result.context is None
    await init_db("sqlite+aiosqlite://")


async def test_recall_persona_with_skills():
    """Persona skills should be in context and RecallResult."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(
            name="devops",
            system_prompt="DevOps expert",
            skills=["jira", "clickhouse-best-practices"],
            is_default=True,
        )

    result = await build_recall_context("sess")
    assert result.persona_skills == ["jira", "clickhouse-best-practices"]
    assert "Prioritize these skills" in result.context
    assert "jira" in result.context
    assert "clickhouse-best-practices" in result.context


async def test_recall_persona_with_mcp():
    """Persona MCP server names should be in RecallResult."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(
            name="sgerp-dev",
            mcp_servers=["sgerp", "jira"],
            is_default=True,
        )

    result = await build_recall_context("sess")
    assert result.persona_mcp_servers == ["sgerp", "jira"]
    assert "Active MCP integrations" in result.context
    assert "sgerp" in result.context


async def test_recall_persona_with_skills_and_mcp():
    """Combined skills + MCP + system_prompt."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(
            name="full",
            system_prompt="Expert assistant",
            skills=["jira"],
            mcp_servers=["sgerp"],
            is_default=True,
        )

    result = await build_recall_context("sess")
    assert result.persona_skills == ["jira"]
    assert result.persona_mcp_servers == ["sgerp"]
    assert "Expert assistant" in result.context
    assert "Prioritize these skills: jira" in result.context
    assert "Active MCP integrations: sgerp" in result.context


async def test_recall_non_default_persona_ignored():
    """Non-default persona should not affect recall."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(
            name="unused",
            skills=["jira"],
            mcp_servers=["sgerp"],
            is_default=False,
        )

    result = await build_recall_context("sess")
    assert result.persona_skills == []
    assert result.persona_mcp_servers == []
