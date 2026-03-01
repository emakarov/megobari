"""Tests for database-backed commands: /persona, /memory, /summaries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.formatting import TelegramFormatter


@pytest.fixture(autouse=True)
async def db():
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


class MockTransport:
    """Lightweight mock implementing TransportContext interface for tests."""

    def __init__(self, session_manager=None, args=None, text="hello",
                 user_id=12345, chat_id=12345, message_id=99,
                 bot_data=None, caption=None):
        self._session_manager = session_manager
        self._args = args or []
        self._text = text
        self._user_id = user_id
        self._chat_id = chat_id
        self._message_id = message_id
        self._caption = caption
        self._formatter = TelegramFormatter()
        self._bot_data = bot_data if bot_data is not None else {}
        if session_manager and "session_manager" not in self._bot_data:
            self._bot_data["session_manager"] = session_manager

        # Mock all async methods
        self.reply = AsyncMock(return_value=MagicMock())
        self.reply_formatted = AsyncMock(return_value=MagicMock())
        self.reply_document = AsyncMock()
        self.reply_photo = AsyncMock()
        self.send_message = AsyncMock()
        self.edit_message = AsyncMock()
        self.delete_message = AsyncMock()
        self.send_typing = AsyncMock()
        self.set_reaction = AsyncMock()
        self.download_photo = AsyncMock(return_value=None)
        self.download_document = AsyncMock(return_value=None)
        self.download_voice = AsyncMock(return_value=None)

    @property
    def args(self): return self._args
    @property
    def text(self): return self._text
    @property
    def chat_id(self): return self._chat_id
    @property
    def message_id(self): return self._message_id
    @property
    def user_id(self): return self._user_id
    @property
    def username(self): return "testuser"
    @property
    def first_name(self): return "Test"
    @property
    def last_name(self): return "User"
    @property
    def caption(self): return self._caption
    @property
    def session_manager(self): return self._session_manager
    @property
    def formatter(self): return self._formatter
    @property
    def bot_data(self): return self._bot_data
    @property
    def transport_name(self): return "test"
    @property
    def max_message_length(self): return 4096


# ---------------------------------------------------------------
# /persona
# ---------------------------------------------------------------


class TestCmdPersona:
    async def test_no_args_shows_usage(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager)
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text

    async def test_create_persona(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(
            session_manager=session_manager,
            args=["create", "dev", "Coding", "assistant"],
        )
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
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

        ctx = MockTransport(session_manager=session_manager, args=["create", "dev"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "already exists" in text

    async def test_list_empty(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["list"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No personas" in text

    async def test_list_personas(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev", description="Coder")
            await repo.create_persona(name="analyst")

        ctx = MockTransport(session_manager=session_manager, args=["list"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "dev" in text
        assert "analyst" in text

    async def test_info(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev", system_prompt="Be concise")

        ctx = MockTransport(session_manager=session_manager, args=["info", "dev"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "dev" in text
        assert "Be concise" in text

    async def test_info_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["info", "nope"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_default(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        ctx = MockTransport(session_manager=session_manager, args=["default", "dev"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Default persona set" in text

    async def test_delete(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="temp")

        ctx = MockTransport(session_manager=session_manager, args=["delete", "temp"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Deleted" in text

    async def test_prompt(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        ctx = MockTransport(session_manager=session_manager, args=["prompt", "dev", "Be", "brief"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "updated" in text

    async def test_mcp(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        ctx = MockTransport(session_manager=session_manager, args=["mcp", "dev", "sgerp,transit"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "sgerp" in text

    async def test_create_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["create"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_info_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["info"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_default_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["default"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_default_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["default", "nope"])
        await cmd_persona(ctx)
        assert "not found" in ctx.reply.call_args[0][0]

    async def test_delete_no_name(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["delete"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_delete_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["delete", "nope"])
        await cmd_persona(ctx)
        assert "not found" in ctx.reply.call_args[0][0]

    async def test_prompt_no_text(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["prompt", "dev"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_prompt_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["prompt", "nope", "text"])
        await cmd_persona(ctx)
        assert "not found" in ctx.reply.call_args[0][0]

    async def test_mcp_no_servers(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["mcp", "dev"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_mcp_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["mcp", "nope", "a,b"])
        await cmd_persona(ctx)
        assert "not found" in ctx.reply.call_args[0][0]

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["bogus"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Unknown" in text

    async def test_skills(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(name="dev")

        ctx = MockTransport(
            session_manager=session_manager,
            args=["skills", "dev", "jira,clickhouse"],
        )
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "jira" in text
        assert "clickhouse" in text

        # Verify in DB
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.get_persona("dev")
        assert Repository.persona_skills(p) == ["jira", "clickhouse"]

    async def test_skills_no_args(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager, args=["skills", "dev"])
        await cmd_persona(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_skills_not_found(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(
            session_manager=session_manager, args=["skills", "nope", "jira"]
        )
        await cmd_persona(ctx)
        assert "not found" in ctx.reply.call_args[0][0]

    async def test_info_shows_skills(self, session_manager):
        from megobari.bot import cmd_persona

        async with get_session() as s:
            repo = Repository(s)
            await repo.create_persona(
                name="dev", skills=["jira", "clickhouse"]
            )

        ctx = MockTransport(session_manager=session_manager, args=["info", "dev"])
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Skills" in text
        assert "jira" in text

    async def test_usage_shows_skills(self, session_manager):
        from megobari.bot import cmd_persona

        ctx = MockTransport(session_manager=session_manager)
        await cmd_persona(ctx)
        text = ctx.reply.call_args[0][0]
        assert "skills" in text.lower()


# ---------------------------------------------------------------
# /mcp and /skills commands
# ---------------------------------------------------------------


class TestCmdMcp:
    @patch("megobari.handlers.persona.list_available_servers", return_value=[])
    async def test_no_servers(self, mock_list, session_manager):
        from megobari.bot import cmd_mcp

        ctx = MockTransport(session_manager=session_manager)
        await cmd_mcp(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No MCP servers" in text

    @patch(
        "megobari.handlers.persona.list_available_servers",
        return_value=["figma", "github", "sgerp"],
    )
    async def test_lists_servers(self, mock_list, session_manager):
        from megobari.bot import cmd_mcp

        ctx = MockTransport(session_manager=session_manager)
        await cmd_mcp(ctx)
        text = ctx.reply.call_args[0][0]
        assert "github" in text
        assert "sgerp" in text
        assert "figma" in text


class TestCmdSkills:
    @patch("megobari.handlers.persona.discover_skills", return_value=[])
    async def test_no_skills(self, mock_discover, session_manager):
        from megobari.bot import cmd_skills

        ctx = MockTransport(session_manager=session_manager)
        await cmd_skills(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No skills" in text

    @patch(
        "megobari.handlers.persona.discover_skills",
        return_value=["clickhouse-best-practices", "find-skills", "jira"],
    )
    async def test_lists_skills(self, mock_discover, session_manager):
        from megobari.bot import cmd_skills

        ctx = MockTransport(session_manager=session_manager)
        await cmd_skills(ctx)
        text = ctx.reply.call_args[0][0]
        assert "jira" in text
        assert "clickhouse-best-practices" in text


# ---------------------------------------------------------------
# /memory
# ---------------------------------------------------------------


class TestCmdMemory:
    async def test_no_args_shows_usage(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager)
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text

    async def test_set_no_value(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["set", "cat", "key"])
        await cmd_memory(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_get_no_key(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["get", "cat"])
        await cmd_memory(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_delete_no_key(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["delete", "cat"])
        await cmd_memory(ctx)
        assert "Usage" in ctx.reply.call_args[0][0]

    async def test_delete_not_found(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["delete", "x", "y"])
        await cmd_memory(ctx)
        assert "Not found" in ctx.reply.call_args[0][0]

    async def test_set_and_list(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(
            session_manager=session_manager,
            args=["set", "pref", "lang", "Python"],
        )
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Saved" in text

        ctx2 = MockTransport(session_manager=session_manager, args=["list"])
        await cmd_memory(ctx2)
        text2 = ctx2.reply.call_args[0][0]
        assert "Python" in text2

    async def test_get(self, session_manager):
        from megobari.bot import cmd_memory

        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory("pref", "editor", "vim")

        ctx = MockTransport(session_manager=session_manager, args=["get", "pref", "editor"])
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "vim" in text

    async def test_get_not_found(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["get", "x", "y"])
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Not found" in text

    async def test_delete(self, session_manager):
        from megobari.bot import cmd_memory

        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory("tmp", "x", "val")

        ctx = MockTransport(session_manager=session_manager, args=["delete", "tmp", "x"])
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Deleted" in text

    async def test_list_empty(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["list"])
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No memories" in text

    async def test_list_by_category(self, session_manager):
        from megobari.bot import cmd_memory

        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory("pref", "a", "1")
            await repo.set_memory("fact", "b", "2")

        ctx = MockTransport(session_manager=session_manager, args=["list", "pref"])
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
        assert "1" in text
        assert "2" not in text

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_memory

        ctx = MockTransport(session_manager=session_manager, args=["bogus"])
        await cmd_memory(ctx)
        text = ctx.reply.call_args[0][0]
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

        ctx = MockTransport(session_manager=session_manager)
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Did things" in text

    async def test_no_summaries(self, session_manager):
        from megobari.bot import cmd_summaries

        session_manager.create("default")
        ctx = MockTransport(session_manager=session_manager)
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No summaries" in text

    async def test_all(self, session_manager):
        from megobari.bot import cmd_summaries

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="a", summary="Summary A")
            await repo.add_summary(session_name="b", summary="Summary B")

        ctx = MockTransport(session_manager=session_manager, args=["all"])
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Summary A" in text
        assert "Summary B" in text

    async def test_search(self, session_manager):
        from megobari.bot import cmd_summaries

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="x", summary="Built transit tools")
            await repo.add_summary(session_name="x", summary="Fixed bug")

        ctx = MockTransport(session_manager=session_manager, args=["search", "transit"])
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "transit" in text

    async def test_search_no_results(self, session_manager):
        from megobari.bot import cmd_summaries

        ctx = MockTransport(session_manager=session_manager, args=["search", "nonexistent"])
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No summaries matching" in text

    async def test_milestones(self, session_manager):
        from megobari.bot import cmd_summaries

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(session_name="x", summary="Regular")
            await repo.add_summary(
                session_name="x", summary="Big milestone", is_milestone=True
            )

        ctx = MockTransport(session_manager=session_manager, args=["milestones"])
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Big milestone" in text

    async def test_milestones_empty(self, session_manager):
        from megobari.bot import cmd_summaries

        ctx = MockTransport(session_manager=session_manager, args=["milestones"])
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No milestones" in text

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_summaries

        ctx = MockTransport(session_manager=session_manager, args=["bogus"])
        await cmd_summaries(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text


# ---------------------------------------------------------------
# /dashboard
# ---------------------------------------------------------------


class TestCmdDashboard:
    async def test_list_empty(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(session_manager=session_manager)
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No dashboard tokens" in text

    async def test_add_token(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["add", "my-app"]
        )
        await cmd_dashboard(ctx)
        # Find the call with formatted=True
        text = ctx.reply.call_args[0][0]
        assert "New dashboard token created" in text
        assert "my-app" in text
        assert "#" in text  # token ID

        # Verify token was persisted in DB
        async with get_session() as s:
            repo = Repository(s)
            tokens = await repo.list_dashboard_tokens()
        assert len(tokens) == 1
        assert tokens[0].name == "my-app"

    async def test_add_token_multi_word_name(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["add", "My", "Dashboard", "App"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "My Dashboard App" in text

    async def test_add_no_name(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(session_manager=session_manager, args=["add"])
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text

    async def test_list_with_tokens(self, session_manager):
        from megobari.bot import cmd_dashboard

        # Create tokens directly in DB
        async with get_session() as s:
            repo = Repository(s)
            await repo.create_dashboard_token("app-one", "token_aaaaaa11")
            await repo.create_dashboard_token("app-two", "token_bbbbbb22")

        ctx = MockTransport(session_manager=session_manager)
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Dashboard Tokens" in text
        assert "app-one" in text
        assert "app-two" in text

    async def test_disable(self, session_manager):
        from megobari.bot import cmd_dashboard

        async with get_session() as s:
            repo = Repository(s)
            dt = await repo.create_dashboard_token("app", "token_xyz")
            token_id = dt.id

        ctx = MockTransport(
            session_manager=session_manager, args=["disable", str(token_id)]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "disabled" in text

        # Verify in DB
        async with get_session() as s:
            repo = Repository(s)
            tokens = await repo.list_dashboard_tokens()
        assert tokens[0].enabled is False

    async def test_enable(self, session_manager):
        from megobari.bot import cmd_dashboard

        async with get_session() as s:
            repo = Repository(s)
            dt = await repo.create_dashboard_token("app", "token_xyz")
            dt.enabled = False
            await s.flush()
            token_id = dt.id

        ctx = MockTransport(
            session_manager=session_manager, args=["enable", str(token_id)]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "enabled" in text

        # Verify in DB
        async with get_session() as s:
            repo = Repository(s)
            tokens = await repo.list_dashboard_tokens()
        assert tokens[0].enabled is True

    async def test_disable_not_found(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["disable", "999"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_enable_not_found(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["enable", "999"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_disable_no_id(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(session_manager=session_manager, args=["disable"])
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text

    async def test_enable_no_id(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(session_manager=session_manager, args=["enable"])
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text

    async def test_disable_non_numeric_id(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["disable", "abc"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "must be a number" in text

    async def test_enable_non_numeric_id(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["enable", "abc"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "must be a number" in text

    async def test_revoke(self, session_manager):
        from megobari.bot import cmd_dashboard

        async with get_session() as s:
            repo = Repository(s)
            dt = await repo.create_dashboard_token("temp", "token_temp")
            token_id = dt.id

        ctx = MockTransport(
            session_manager=session_manager, args=["revoke", str(token_id)]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "permanently revoked" in text

        # Verify deleted from DB
        async with get_session() as s:
            repo = Repository(s)
            tokens = await repo.list_dashboard_tokens()
        assert len(tokens) == 0

    async def test_revoke_not_found(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["revoke", "999"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_revoke_no_id(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(session_manager=session_manager, args=["revoke"])
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage" in text

    async def test_revoke_non_numeric_id(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["revoke", "abc"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "must be a number" in text

    async def test_unknown_subcommand(self, session_manager):
        from megobari.bot import cmd_dashboard

        ctx = MockTransport(
            session_manager=session_manager, args=["bogus"]
        )
        await cmd_dashboard(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Unknown subcommand" in text


# ---------------------------------------------------------------
# Dashboard API auth middleware
# ---------------------------------------------------------------


class TestRequireAuth:
    async def test_valid_token_passes(self):
        from fastapi.security import HTTPAuthorizationCredentials

        from megobari.api.auth import require_auth

        token = "valid_bearer_token_for_test"
        async with get_session() as s:
            repo = Repository(s)
            await repo.create_dashboard_token("test-client", token)

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        request = MagicMock()

        # Should not raise
        await require_auth(request, creds)

    async def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        from megobari.api.auth import require_auth

        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="wrong_token"
        )
        request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request, creds)
        assert exc_info.value.status_code == 401

    async def test_disabled_token_raises_401(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        from megobari.api.auth import require_auth

        token = "disabled_token_for_test"
        async with get_session() as s:
            repo = Repository(s)
            dt = await repo.create_dashboard_token("disabled-client", token)
            dt.enabled = False
            await s.flush()

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request, creds)
        assert exc_info.value.status_code == 401
