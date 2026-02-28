"""Tests for database-backed commands: /persona, /memory, /summaries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.session import SessionManager


@pytest.fixture(autouse=True)
async def db():
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


def _make_context(session_manager: SessionManager, args: list[str] | None = None):
    ctx = MagicMock()
    ctx.bot_data = {"session_manager": session_manager}
    ctx.args = args or []
    ctx.bot = AsyncMock()
    return ctx


def _make_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    return update


# ---------------------------------------------------------------
# /persona
# ---------------------------------------------------------------


class TestCmdPersona:
    async def test_no_args_shows_usage(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_create_persona(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["create", "dev", "Coding", "assistant"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Created" in text

        async with get_session() as s:
            repo = Repository(s)
            p = await repo.get_persona("dev")
        assert p is not None
        assert p.description == "Coding assistant"

    async def test_create_duplicate(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        update = _make_update()
        ctx = _make_context(session_manager, args=["create", "dev"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "already exists" in text

    async def test_list_empty(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["list"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No personas" in text

    async def test_list_personas(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev", description="Coder")
            await repo.create_persona(name="analyst")

        update = _make_update()
        ctx = _make_context(session_manager, args=["list"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "dev" in text
        assert "analyst" in text

    async def test_info(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev", system_prompt="Be concise")

        update = _make_update()
        ctx = _make_context(session_manager, args=["info", "dev"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "dev" in text
        assert "Be concise" in text

    async def test_info_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["info", "nope"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_default(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        update = _make_update()
        ctx = _make_context(session_manager, args=["default", "dev"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Default persona set" in text

    async def test_delete(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="temp")

        update = _make_update()
        ctx = _make_context(session_manager, args=["delete", "temp"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Deleted" in text

    async def test_prompt(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        update = _make_update()
        ctx = _make_context(session_manager, args=["prompt", "dev", "Be", "brief"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "updated" in text

    async def test_mcp(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        update = _make_update()
        ctx = _make_context(session_manager, args=["mcp", "dev", "sgerp,transit"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "sgerp" in text

    async def test_create_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["create"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_info_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["info"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_default_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["default"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_default_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["default", "nope"])
        await cmd_persona(update, ctx)
        assert "not found" in update.message.reply_text.call_args[0][0]

    async def test_delete_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["delete"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_delete_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["delete", "nope"])
        await cmd_persona(update, ctx)
        assert "not found" in update.message.reply_text.call_args[0][0]

    async def test_prompt_no_text(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["prompt", "dev"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_prompt_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["prompt", "nope", "text"])
        await cmd_persona(update, ctx)
        assert "not found" in update.message.reply_text.call_args[0][0]

    async def test_mcp_no_servers(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["mcp", "dev"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_mcp_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["mcp", "nope", "a,b"])
        await cmd_persona(update, ctx)
        assert "not found" in update.message.reply_text.call_args[0][0]

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["bogus"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Unknown" in text

    async def test_skills(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        update = _make_update()
        ctx = _make_context(
            session_manager,
            args=["skills", "dev", "jira,clickhouse"],
        )
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "jira" in text
        assert "clickhouse" in text

        # Verify in DB
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.get_persona("dev")
        assert Repository.persona_skills(p) == ["jira", "clickhouse"]

    async def test_skills_no_args(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager, args=["skills", "dev"])
        await cmd_persona(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_skills_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(
            session_manager, args=["skills", "nope", "jira"]
        )
        await cmd_persona(update, ctx)
        assert "not found" in update.message.reply_text.call_args[0][0]

    async def test_info_shows_skills(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(
                name="dev", skills=["jira", "clickhouse"]
            )

        update = _make_update()
        ctx = _make_context(session_manager, args=["info", "dev"])
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Skills" in text
        assert "jira" in text

    async def test_usage_shows_skills(self, session_manager):
        from megobari.bot import cmd_persona

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_persona(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "skills" in text.lower()


# ---------------------------------------------------------------
# /mcp and /skills commands
# ---------------------------------------------------------------


class TestCmdMcp:
    @patch("megobari.bot.list_available_servers", return_value=[])
    async def test_no_servers(self, mock_list, session_manager):
        from megobari.bot import cmd_mcp

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_mcp(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No MCP servers" in text

    @patch(
        "megobari.bot.list_available_servers",
        return_value=["figma", "github", "sgerp"],
    )
    async def test_lists_servers(self, mock_list, session_manager):
        from megobari.bot import cmd_mcp

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_mcp(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "github" in text
        assert "sgerp" in text
        assert "figma" in text


class TestCmdSkills:
    @patch("megobari.bot.discover_skills", return_value=[])
    async def test_no_skills(self, mock_discover, session_manager):
        from megobari.bot import cmd_skills

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_skills(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No skills" in text

    @patch(
        "megobari.bot.discover_skills",
        return_value=["clickhouse-best-practices", "find-skills", "jira"],
    )
    async def test_lists_skills(self, mock_discover, session_manager):
        from megobari.bot import cmd_skills

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_skills(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "jira" in text
        assert "clickhouse-best-practices" in text


# ---------------------------------------------------------------
# /memory
# ---------------------------------------------------------------


class TestCmdMemory:
    async def test_no_args_shows_usage(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_set_no_value(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["set", "cat", "key"])
        await cmd_memory(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_get_no_key(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["get", "cat"])
        await cmd_memory(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_delete_no_key(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["delete", "cat"])
        await cmd_memory(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    async def test_delete_not_found(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["delete", "x", "y"])
        await cmd_memory(update, ctx)
        assert "Not found" in update.message.reply_text.call_args[0][0]

    async def test_set_and_list(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["set", "pref", "lang", "Python"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Saved" in text

        update2 = _make_update()
        ctx2 = _make_context(session_manager, args=["list"])
        await cmd_memory(update2, ctx2)
        text2 = update2.message.reply_text.call_args[0][0]
        assert "Python" in text2

    async def test_get(self, session_manager):
        from megobari.bot import cmd_memory

        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory("pref", "editor", "vim")

        update = _make_update()
        ctx = _make_context(session_manager, args=["get", "pref", "editor"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "vim" in text

    async def test_get_not_found(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["get", "x", "y"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Not found" in text

    async def test_delete(self, session_manager):
        from megobari.bot import cmd_memory

        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory("tmp", "x", "val")

        update = _make_update()
        ctx = _make_context(session_manager, args=["delete", "tmp", "x"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Deleted" in text

    async def test_list_empty(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["list"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No memories" in text

    async def test_list_by_category(self, session_manager):
        from megobari.bot import cmd_memory

        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory("pref", "a", "1")
            await repo.set_memory("fact", "b", "2")

        update = _make_update()
        ctx = _make_context(session_manager, args=["list", "pref"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "1" in text
        assert "2" not in text

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_memory

        update = _make_update()
        ctx = _make_context(session_manager, args=["bogus"])
        await cmd_memory(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Unknown" in text


# ---------------------------------------------------------------
# /summaries
# ---------------------------------------------------------------


class TestCmdSummaries:
    async def test_no_args_current_session(self, session_manager):
        from megobari.bot import cmd_summaries

        session_manager.create("default")
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="default", summary="Did things")

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Did things" in text

    async def test_no_summaries(self, session_manager):
        from megobari.bot import cmd_summaries

        session_manager.create("default")
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No summaries" in text

    async def test_all(self, session_manager):
        from megobari.bot import cmd_summaries

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="a", summary="Summary A")
            await repo.add_summary(session_name="b", summary="Summary B")

        update = _make_update()
        ctx = _make_context(session_manager, args=["all"])
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Summary A" in text
        assert "Summary B" in text

    async def test_search(self, session_manager):
        from megobari.bot import cmd_summaries

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="x", summary="Built transit tools")
            await repo.add_summary(session_name="x", summary="Fixed bug")

        update = _make_update()
        ctx = _make_context(session_manager, args=["search", "transit"])
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "transit" in text

    async def test_search_no_results(self, session_manager):
        from megobari.bot import cmd_summaries

        update = _make_update()
        ctx = _make_context(session_manager, args=["search", "nonexistent"])
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No summaries matching" in text

    async def test_milestones(self, session_manager):
        from megobari.bot import cmd_summaries

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="x", summary="Regular")
            await repo.add_summary(
                session_name="x", summary="Big milestone", is_milestone=True
            )

        update = _make_update()
        ctx = _make_context(session_manager, args=["milestones"])
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Big milestone" in text

    async def test_milestones_empty(self, session_manager):
        from megobari.bot import cmd_summaries

        update = _make_update()
        ctx = _make_context(session_manager, args=["milestones"])
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No milestones" in text

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_summaries

        update = _make_update()
        ctx = _make_context(session_manager, args=["bogus"])
        await cmd_summaries(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text
