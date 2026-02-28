"""Tests for /think, /effort, /usage, /compact, /doctor commands."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.claude_bridge import QueryUsage
from megobari.db import close_db, init_db
from megobari.session import SessionManager


@pytest.fixture(autouse=True)
async def db():
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


@pytest.fixture
def sm_with_session(session_manager: SessionManager) -> SessionManager:
    """SessionManager with an active session created."""
    session_manager.create("test")
    return session_manager


def _make_context(
    session_manager: SessionManager,
    args: list[str] | None = None,
    usage_map: dict | None = None,
):
    ctx = MagicMock()
    bot_data = {"session_manager": session_manager}
    if usage_map is not None:
        bot_data["usage"] = usage_map
    ctx.bot_data = bot_data
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
# /think
# ---------------------------------------------------------------


class TestCmdThink:
    async def test_show_current(self, sm_with_session):
        from megobari.bot import cmd_think

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "adaptive" in text

    async def test_think_on(self, sm_with_session):
        from megobari.bot import cmd_think

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on"])
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "enabled" in text.lower() or "10,000" in text
        assert sm_with_session.current.thinking == "enabled"
        assert sm_with_session.current.thinking_budget == 10000

    async def test_think_on_custom_budget(self, sm_with_session):
        from megobari.bot import cmd_think

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on", "50000"])
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "50,000" in text
        assert sm_with_session.current.thinking_budget == 50000

    async def test_think_on_invalid_budget(self, sm_with_session):
        from megobari.bot import cmd_think

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on", "notanumber"])
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Invalid" in text

    async def test_think_off(self, sm_with_session):
        from megobari.bot import cmd_think

        sm_with_session.current.thinking = "enabled"
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["off"])
        await cmd_think(update, ctx)
        assert sm_with_session.current.thinking == "disabled"

    async def test_think_adaptive(self, sm_with_session):
        from megobari.bot import cmd_think

        sm_with_session.current.thinking = "disabled"
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["adaptive"])
        await cmd_think(update, ctx)
        assert sm_with_session.current.thinking == "adaptive"

    async def test_think_invalid_mode(self, sm_with_session):
        from megobari.bot import cmd_think

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["bogus"])
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_show_budget_when_enabled(self, sm_with_session):
        from megobari.bot import cmd_think

        sm_with_session.current.thinking = "enabled"
        sm_with_session.current.thinking_budget = 25000
        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "25,000" in text


# ---------------------------------------------------------------
# /effort
# ---------------------------------------------------------------


class TestCmdEffort:
    async def test_show_current_default(self, sm_with_session):
        from megobari.bot import cmd_effort

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_effort(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not set" in text.lower() or "default" in text.lower()

    async def test_set_high(self, sm_with_session):
        from megobari.bot import cmd_effort

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["high"])
        await cmd_effort(update, ctx)
        assert sm_with_session.current.effort == "high"
        text = update.message.reply_text.call_args[0][0]
        assert "high" in text

    async def test_set_max(self, sm_with_session):
        from megobari.bot import cmd_effort

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["max"])
        await cmd_effort(update, ctx)
        assert sm_with_session.current.effort == "max"

    async def test_set_low(self, sm_with_session):
        from megobari.bot import cmd_effort

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["low"])
        await cmd_effort(update, ctx)
        assert sm_with_session.current.effort == "low"

    async def test_effort_off(self, sm_with_session):
        from megobari.bot import cmd_effort

        sm_with_session.current.effort = "high"
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["off"])
        await cmd_effort(update, ctx)
        assert sm_with_session.current.effort is None
        text = update.message.reply_text.call_args[0][0]
        assert "cleared" in text.lower() or "default" in text.lower()

    async def test_effort_invalid(self, sm_with_session):
        from megobari.bot import cmd_effort

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["extreme"])
        await cmd_effort(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


# ---------------------------------------------------------------
# /usage
# ---------------------------------------------------------------


class TestCmdUsage:
    async def test_no_usage_yet(self, sm_with_session):
        from megobari.bot import cmd_usage

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No usage" in text

    async def test_with_usage_data(self, sm_with_session):
        from megobari.bot import SessionUsage, cmd_usage

        su = SessionUsage(
            total_cost_usd=0.0342,
            total_turns=12,
            total_duration_ms=45200,
            message_count=5,
        )
        usage_map = {sm_with_session.current.name: su}
        update = _make_update()
        ctx = _make_context(sm_with_session, usage_map=usage_map)
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "$0.0342" in text
        assert "12" in text
        assert "5" in text
        assert "45.2" in text

    async def test_usage_all(self, sm_with_session):
        from megobari.bot import cmd_usage
        from megobari.db import Repository, get_session

        # Seed some usage records in DB
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_usage("test", 0.01, 3, 5000)
            await repo.add_usage("other", 0.02, 5, 8000)

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["all"])
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "All-time" in text
        assert "$0.0300" in text
        assert "8" in text  # total turns
        assert "2" in text  # session_count or query_count

    async def test_usage_shows_db_history(self, sm_with_session):
        from megobari.bot import cmd_usage
        from megobari.db import Repository, get_session

        # Seed DB with historical usage for current session
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_usage("test", 0.05, 10, 20000)

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "All-time" in text
        assert "$0.0500" in text


# ---------------------------------------------------------------
# Usage accumulation
# ---------------------------------------------------------------


class TestAccumulateUsage:
    @patch("megobari.handlers._common._persist_usage", new_callable=AsyncMock)
    async def test_accumulate_new_session(self, mock_persist, session_manager):
        from megobari.bot import SessionUsage, _accumulate_usage

        ctx = _make_context(session_manager)
        usage = QueryUsage(cost_usd=0.01, num_turns=3, duration_api_ms=5000)
        _accumulate_usage(ctx, "test", usage)

        su = ctx.bot_data["usage"]["test"]
        assert isinstance(su, SessionUsage)
        assert su.total_cost_usd == 0.01
        assert su.total_turns == 3
        assert su.message_count == 1

    @patch("megobari.handlers._common._persist_usage", new_callable=AsyncMock)
    async def test_accumulate_existing_session(self, mock_persist, session_manager):
        from megobari.bot import _accumulate_usage

        ctx = _make_context(session_manager)
        usage1 = QueryUsage(cost_usd=0.01, num_turns=3, duration_api_ms=5000)
        usage2 = QueryUsage(cost_usd=0.02, num_turns=5, duration_api_ms=8000)
        _accumulate_usage(ctx, "test", usage1)
        _accumulate_usage(ctx, "test", usage2)

        su = ctx.bot_data["usage"]["test"]
        assert su.total_cost_usd == pytest.approx(0.03)
        assert su.total_turns == 8
        assert su.total_duration_ms == 13000
        assert su.message_count == 2

    @patch("megobari.handlers._common._persist_usage", new_callable=AsyncMock)
    async def test_accumulate_fires_persist(self, mock_persist, session_manager):
        from megobari.bot import _accumulate_usage

        ctx = _make_context(session_manager)
        usage = QueryUsage(cost_usd=0.05, num_turns=2, duration_api_ms=3000)
        _accumulate_usage(ctx, "test", usage, user_id=42)
        # Let the fire-and-forget task run
        await asyncio.sleep(0.01)
        mock_persist.assert_called_once_with("test", usage, 42)

    async def test_persist_usage_writes_to_db(self, session_manager):
        from megobari.bot import _persist_usage
        from megobari.db import Repository, get_session

        usage = QueryUsage(cost_usd=0.05, num_turns=2, duration_api_ms=3000)
        await _persist_usage("test-session", usage, user_id=None)

        async with get_session() as s:
            repo = Repository(s)
            records = await repo.get_usage_records(session_name="test-session")
        assert len(records) == 1
        assert records[0].cost_usd == 0.05
        assert records[0].num_turns == 2


# ---------------------------------------------------------------
# /compact
# ---------------------------------------------------------------


class TestCmdCompact:
    async def test_no_context(self, sm_with_session):
        from megobari.bot import cmd_compact

        sm_with_session.current.session_id = None
        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_compact(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No active context" in text

    @patch("megobari.handlers.usage.send_to_claude")
    async def test_compact_success(self, mock_send, sm_with_session):
        from megobari.bot import cmd_compact

        sm_with_session.current.session_id = "old-sid"

        # First call: summarize, second call: seed
        mock_send.side_effect = [
            ("• Task A done\n• Working on B", [], None, QueryUsage()),
            ("OK, continuing.", [], "new-sid", QueryUsage()),
        ]

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_compact(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "compacted" in text.lower() or "Summary" in text
        assert "Task A" in text
        # Session should have new id
        assert sm_with_session.current.session_id == "new-sid"
        # send_to_claude called twice
        assert mock_send.call_count == 2


# ---------------------------------------------------------------
# /doctor
# ---------------------------------------------------------------


class TestCmdDoctor:
    async def test_doctor_runs(self, sm_with_session):
        from megobari.bot import cmd_doctor

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_doctor(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        # Should include various check results
        assert "SDK" in text
        assert "Sessions" in text
        assert "DB" in text

    async def test_doctor_shows_active_session(self, sm_with_session):
        from megobari.bot import cmd_doctor

        sm_with_session.current.thinking = "enabled"
        sm_with_session.current.effort = "high"
        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_doctor(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "enabled" in text
        assert "high" in text


# ---------------------------------------------------------------
# Bridge: _build_thinking_config
# ---------------------------------------------------------------


class TestBuildThinkingConfig:
    def test_adaptive(self):
        from megobari.claude_bridge import _build_thinking_config
        from megobari.session import Session

        s = Session(name="t", thinking="adaptive")
        assert _build_thinking_config(s) == {"type": "adaptive"}

    def test_enabled_default_budget(self):
        from megobari.claude_bridge import _build_thinking_config
        from megobari.session import Session

        s = Session(name="t", thinking="enabled")
        config = _build_thinking_config(s)
        assert config["type"] == "enabled"
        assert config["budget_tokens"] == 10000

    def test_enabled_custom_budget(self):
        from megobari.claude_bridge import _build_thinking_config
        from megobari.session import Session

        s = Session(name="t", thinking="enabled", thinking_budget=50000)
        config = _build_thinking_config(s)
        assert config["budget_tokens"] == 50000

    def test_disabled(self):
        from megobari.claude_bridge import _build_thinking_config
        from megobari.session import Session

        s = Session(name="t", thinking="disabled")
        assert _build_thinking_config(s) == {"type": "disabled"}


class TestBuildOptions:
    def test_includes_thinking_and_effort(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t", thinking="enabled", thinking_budget=20000, effort="high")
        options = _build_options(s)
        assert options.thinking == {"type": "enabled", "budget_tokens": 20000}
        assert options.effort == "high"

    def test_no_effort_when_none(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        options = _build_options(s)
        assert options.effort is None

    def test_resume_set_when_session_id(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t", session_id="sid-123")
        options = _build_options(s)
        assert options.resume == "sid-123"


# ---------------------------------------------------------------
# Session model fields
# ---------------------------------------------------------------


class TestSessionFields:
    def test_default_thinking(self):
        from megobari.session import Session

        s = Session(name="t")
        assert s.thinking == "adaptive"
        assert s.thinking_budget is None
        assert s.effort is None

    def test_serialization(self):
        from dataclasses import asdict

        from megobari.session import Session

        s = Session(name="t", thinking="enabled", thinking_budget=30000, effort="max")
        d = asdict(s)
        assert d["thinking"] == "enabled"
        assert d["thinking_budget"] == 30000
        assert d["effort"] == "max"

    def test_round_trip(self):
        from dataclasses import asdict

        from megobari.session import Session

        s = Session(name="t", thinking="disabled", effort="low")
        d = asdict(s)
        s2 = Session(**d)
        assert s2.thinking == "disabled"
        assert s2.effort == "low"


# ---------------------------------------------------------------
# Session info display
# ---------------------------------------------------------------


class TestFormatSessionInfo:
    def test_includes_thinking_effort(self):
        from megobari.message_utils import format_session_info
        from megobari.session import Session

        s = Session(name="t", thinking="enabled", thinking_budget=15000, effort="high")
        text = format_session_info(s)
        assert "enabled" in text
        assert "15,000" in text
        assert "high" in text

    def test_default_effort_shown(self):
        from megobari.message_utils import format_session_info
        from megobari.session import Session

        s = Session(name="t")
        text = format_session_info(s)
        assert "default" in text

    def test_includes_model(self):
        from megobari.message_utils import format_session_info
        from megobari.session import Session

        s = Session(name="t", model="claude-sonnet-4-20250514")
        text = format_session_info(s)
        assert "claude-sonnet-4-20250514" in text

    def test_default_model_shown(self):
        from megobari.message_utils import format_session_info
        from megobari.session import Session

        s = Session(name="t")
        text = format_session_info(s)
        # Model line should say "default"
        assert "Model" in text


# ---------------------------------------------------------------
# /model
# ---------------------------------------------------------------


class TestCmdModel:
    async def test_show_current_default(self, sm_with_session):
        from megobari.bot import cmd_model

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_model(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "default" in text.lower()
        assert "haiku" in text or "sonnet" in text or "opus" in text

    async def test_set_sonnet(self, sm_with_session):
        from megobari.bot import cmd_model

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["sonnet"])
        await cmd_model(update, ctx)
        assert sm_with_session.current.model == "claude-sonnet-4-20250514"
        text = update.message.reply_text.call_args[0][0]
        assert "sonnet" in text

    async def test_set_opus(self, sm_with_session):
        from megobari.bot import cmd_model

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["opus"])
        await cmd_model(update, ctx)
        assert sm_with_session.current.model == "claude-opus-4-6"

    async def test_set_haiku(self, sm_with_session):
        from megobari.bot import cmd_model

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["haiku"])
        await cmd_model(update, ctx)
        assert sm_with_session.current.model == "claude-haiku-4-20250414"

    async def test_set_full_model_name(self, sm_with_session):
        from megobari.bot import cmd_model

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["claude-sonnet-4-20250514"])
        await cmd_model(update, ctx)
        assert sm_with_session.current.model == "claude-sonnet-4-20250514"

    async def test_model_off(self, sm_with_session):
        from megobari.bot import cmd_model

        sm_with_session.current.model = "claude-opus-4-6"
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["off"])
        await cmd_model(update, ctx)
        assert sm_with_session.current.model is None
        text = update.message.reply_text.call_args[0][0]
        assert "cleared" in text.lower() or "default" in text.lower()

    async def test_model_default(self, sm_with_session):
        from megobari.bot import cmd_model

        sm_with_session.current.model = "claude-opus-4-6"
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["default"])
        await cmd_model(update, ctx)
        assert sm_with_session.current.model is None


# ---------------------------------------------------------------
# /context
# ---------------------------------------------------------------


class TestCmdContext:
    async def test_no_data_yet(self, sm_with_session):
        from megobari.bot import cmd_context

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_context(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No token data" in text

    async def test_with_run_data(self, sm_with_session):
        from megobari.bot import SessionUsage, cmd_context

        su = SessionUsage(
            total_cost_usd=0.05,
            total_turns=10,
            total_duration_ms=30000,
            input_tokens=5000,
            output_tokens=2000,
            message_count=3,
        )
        usage_map = {sm_with_session.current.name: su}
        update = _make_update()
        ctx = _make_context(sm_with_session, usage_map=usage_map)
        await cmd_context(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "5,000" in text
        assert "2,000" in text
        assert "7,000" in text  # total tokens
        assert "3" in text  # messages

    async def test_shows_session_config(self, sm_with_session):
        from megobari.bot import cmd_context

        sm_with_session.current.model = "claude-opus-4-6"
        sm_with_session.current.thinking = "enabled"
        sm_with_session.current.effort = "high"
        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_context(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "opus" in text or "claude-opus" in text
        assert "enabled" in text
        assert "high" in text

    async def test_with_db_data(self, sm_with_session):
        from megobari.bot import cmd_context
        from megobari.db import Repository, get_session

        # Seed DB with token data
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_usage(
                "test", 0.05, 10, 20000,
                input_tokens=8000, output_tokens=3000,
            )

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_context(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "8,000" in text
        assert "3,000" in text


# ---------------------------------------------------------------
# /history
# ---------------------------------------------------------------


class TestCmdHistory:
    async def test_no_messages(self, sm_with_session):
        from megobari.bot import cmd_history

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No messages" in text

    async def test_with_messages(self, sm_with_session):
        from megobari.bot import cmd_history
        from megobari.summarizer import log_message

        await log_message("test", "user", "Hello world")
        await log_message("test", "assistant", "Hi there!")

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Hello world" in text
        assert "Hi there" in text

    async def test_history_all(self, sm_with_session):
        from megobari.bot import cmd_history
        from megobari.summarizer import log_message

        await log_message("test", "user", "Message 1")
        await log_message("other-session", "user", "Message 2")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["all"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Message 1" in text
        assert "Message 2" in text

    async def test_history_search(self, sm_with_session):
        from megobari.bot import cmd_history
        from megobari.summarizer import log_message

        await log_message("test", "user", "The quick brown fox")
        await log_message("test", "user", "Lazy dog sleeps")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["search", "fox"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "fox" in text
        assert "dog" not in text.replace("Search results", "")  # only in header maybe

    async def test_history_search_no_results(self, sm_with_session):
        from megobari.bot import cmd_history

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["search", "nonexistent"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No messages matching" in text

    async def test_history_stats(self, sm_with_session):
        from megobari.bot import cmd_history
        from megobari.summarizer import log_message

        await log_message("test", "user", "M1")
        await log_message("test", "assistant", "M2")
        await log_message("test", "user", "M3")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["stats"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "3 messages" in text

    async def test_history_stats_empty(self, sm_with_session):
        from megobari.bot import cmd_history

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["stats"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No messages" in text

    async def test_history_invalid_sub(self, sm_with_session):
        from megobari.bot import cmd_history

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["bogus"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


# ---------------------------------------------------------------
# Session model field
# ---------------------------------------------------------------


class TestSessionModelField:
    def test_default_model_none(self):
        from megobari.session import Session

        s = Session(name="t")
        assert s.model is None

    def test_model_serialization(self):
        from dataclasses import asdict

        from megobari.session import Session

        s = Session(name="t", model="claude-opus-4-6")
        d = asdict(s)
        assert d["model"] == "claude-opus-4-6"

    def test_model_round_trip(self):
        from dataclasses import asdict

        from megobari.session import Session

        s = Session(name="t", model="claude-haiku-4-20250414")
        d = asdict(s)
        s2 = Session(**d)
        assert s2.model == "claude-haiku-4-20250414"


# ---------------------------------------------------------------
# Bridge: _build_options with model
# ---------------------------------------------------------------


class TestBuildOptionsModel:
    def test_includes_model(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t", model="claude-opus-4-6")
        options = _build_options(s)
        assert options.model == "claude-opus-4-6"

    def test_no_model_when_none(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        options = _build_options(s)
        assert options.model is None


# ---------------------------------------------------------------
# Help text
# ---------------------------------------------------------------


class TestHelpText:
    def test_help_includes_new_commands(self):
        from megobari.message_utils import format_help

        text = format_help()
        assert "/model" in text
        assert "/context" in text
        assert "/history" in text


# ---------------------------------------------------------------
# Edge cases for coverage
# ---------------------------------------------------------------


class TestHistoryAllEmpty:
    """Cover the 'no messages recorded yet' path for /history all."""

    async def test_history_all_no_messages(self, sm_with_session):
        from megobari.bot import cmd_history

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["all"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No messages recorded yet" in text


class TestHistoryAllWithMessages:
    """Cover the success path for /history all with messages."""

    async def test_history_all_shows_messages(self, sm_with_session):
        from megobari.bot import cmd_history
        from megobari.summarizer import log_message

        await log_message("sess1", "user", "Hello from session 1")
        await log_message("sess2", "assistant", "Reply from session 2")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["all"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "all sessions" in text
        assert "Hello from session 1" in text
        assert "Reply from session 2" in text


class TestHistorySearchWithResults:
    """Cover the search success path with multiple results."""

    async def test_history_search_returns_results(self, sm_with_session):
        from megobari.bot import cmd_history
        from megobari.summarizer import log_message

        await log_message("test", "user", "Build the widget factory")
        await log_message("test", "assistant", "I built the widget factory")
        await log_message("test", "user", "Now test the database")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["search", "widget"])
        await cmd_history(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "widget" in text.lower()


class TestContextDBError:
    """Cover the DB error path for /context."""

    @patch("megobari.handlers.usage.get_session")
    async def test_context_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_context

        mock_gs.side_effect = Exception("DB down")

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_context(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        # Should still show config even if DB fails
        assert "Session config" in text


class TestUsageDBError:
    """Cover DB error paths for /usage."""

    @patch("megobari.handlers.usage.get_session")
    async def test_usage_all_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_usage

        mock_gs.side_effect = Exception("DB error")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["all"])
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed to read usage" in text


# ---------------------------------------------------------------
# Session max_turns and max_budget_usd fields
# ---------------------------------------------------------------


class TestSessionMaxTurnsAndBudget:
    def test_default_none(self):
        from megobari.session import Session

        s = Session(name="t")
        assert s.max_turns is None
        assert s.max_budget_usd is None

    def test_set_values(self):
        from megobari.session import Session

        s = Session(name="t", max_turns=50, max_budget_usd=1.5)
        assert s.max_turns == 50
        assert s.max_budget_usd == 1.5

    def test_serialization(self):
        from dataclasses import asdict

        from megobari.session import Session

        s = Session(name="t", max_turns=25, max_budget_usd=0.5)
        d = asdict(s)
        assert d["max_turns"] == 25
        assert d["max_budget_usd"] == 0.5

    def test_round_trip(self):
        from dataclasses import asdict

        from megobari.session import Session

        s = Session(name="t", max_turns=100, max_budget_usd=2.0)
        d = asdict(s)
        s2 = Session(**d)
        assert s2.max_turns == 100
        assert s2.max_budget_usd == 2.0


# ---------------------------------------------------------------
# _build_options with max_turns and max_budget_usd
# ---------------------------------------------------------------


class TestBuildOptionsMaxTurnsAndBudget:
    def test_includes_max_turns(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t", max_turns=50)
        options = _build_options(s)
        assert options.max_turns == 50

    def test_no_max_turns_when_none(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        options = _build_options(s)
        assert not hasattr(options, "max_turns") or options.max_turns is None

    def test_includes_max_budget_usd(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t", max_budget_usd=1.5)
        options = _build_options(s)
        assert options.max_budget_usd == 1.5

    def test_no_max_budget_when_none(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        options = _build_options(s)
        assert not hasattr(options, "max_budget_usd") or options.max_budget_usd is None

    def test_both_set(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t", max_turns=25, max_budget_usd=0.5, effort="max")
        options = _build_options(s)
        assert options.max_turns == 25
        assert options.max_budget_usd == 0.5
        assert options.effort == "max"


# ---------------------------------------------------------------
# _build_options with MCP servers
# ---------------------------------------------------------------


class TestBuildOptionsWithMcp:
    def test_mcp_servers_passed(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        mcp = {
            "github": {"command": "npx", "args": ["-y", "server-github"]},
            "sgerp": {"command": "uv", "args": ["run", "sgerp-mcp"]},
        }
        options = _build_options(s, mcp_servers=mcp)
        assert options.mcp_servers == mcp
        assert "mcp__github__*" in options.allowed_tools
        assert "mcp__sgerp__*" in options.allowed_tools

    def test_no_mcp_servers(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        options = _build_options(s)
        # No persona MCP → should not have our custom servers
        assert not options.mcp_servers or options.mcp_servers == {}

    def test_empty_mcp_dict_not_set(self):
        from megobari.claude_bridge import _build_options
        from megobari.session import Session

        s = Session(name="t")
        options = _build_options(s, mcp_servers={})
        assert not options.mcp_servers or options.mcp_servers == {}


# ---------------------------------------------------------------
# /autonomous command
# ---------------------------------------------------------------


class TestCmdAutonomous:
    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_show_status_off(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "OFF" in text

    async def test_show_status_on(self, sm_with_session):
        from megobari.bot import cmd_autonomous
        from megobari.session import DEFAULT_AUTONOMOUS_MAX_TURNS

        session = sm_with_session.current
        session.permission_mode = "bypassPermissions"
        session.effort = "max"
        session.max_turns = DEFAULT_AUTONOMOUS_MAX_TURNS
        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "ON" in text

    async def test_turn_on(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on"])
        await cmd_autonomous(update, ctx)
        session = sm_with_session.current
        assert session.permission_mode == "bypassPermissions"
        assert session.effort == "max"
        assert session.max_turns == 50
        text = update.message.reply_text.call_args[0][0]
        assert "ON" in text

    async def test_turn_off(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        session = sm_with_session.current
        session.permission_mode = "bypassPermissions"
        session.effort = "max"
        session.max_turns = 50
        session.max_budget_usd = 1.0
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["off"])
        await cmd_autonomous(update, ctx)
        assert session.permission_mode == "default"
        assert session.effort is None
        assert session.max_turns is None
        assert session.max_budget_usd is None
        text = update.message.reply_text.call_args[0][0]
        assert "OFF" in text

    async def test_set_turns(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["turns", "100"])
        await cmd_autonomous(update, ctx)
        assert sm_with_session.current.max_turns == 100
        text = update.message.reply_text.call_args[0][0]
        assert "100" in text

    async def test_set_turns_invalid(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["turns", "abc"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_set_turns_too_low(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["turns", "0"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_show_turns_no_value(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["turns"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Max turns" in text

    async def test_set_budget(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["budget", "2.50"])
        await cmd_autonomous(update, ctx)
        assert sm_with_session.current.max_budget_usd == 2.50
        text = update.message.reply_text.call_args[0][0]
        assert "$2.50" in text

    async def test_budget_off(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        sm_with_session.current.max_budget_usd = 1.0
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["budget", "off"])
        await cmd_autonomous(update, ctx)
        assert sm_with_session.current.max_budget_usd is None
        text = update.message.reply_text.call_args[0][0]
        assert "removed" in text.lower()

    async def test_budget_invalid(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["budget", "xyz"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_budget_negative(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["budget", "-5"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_show_budget_no_arg(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["budget"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "unlimited" in text.lower()

    async def test_show_budget_with_value(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        sm_with_session.current.max_budget_usd = 3.0
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["budget"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "$3.00" in text

    async def test_invalid_subcommand(self, sm_with_session):
        from megobari.bot import cmd_autonomous

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["bogus"])
        await cmd_autonomous(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_on_aliases(self, sm_with_session):
        """Test 'true' and '1' work same as 'on'."""
        from megobari.bot import cmd_autonomous

        for arg in ("true", "1"):
            sm_with_session.current.permission_mode = "default"
            sm_with_session.current.effort = None
            sm_with_session.current.max_turns = None
            update = _make_update()
            ctx = _make_context(sm_with_session, args=[arg])
            await cmd_autonomous(update, ctx)
            assert sm_with_session.current.permission_mode == "bypassPermissions"

    async def test_off_aliases(self, sm_with_session):
        """Test 'false' and '0' work same as 'off'."""
        from megobari.bot import cmd_autonomous

        for arg in ("false", "0"):
            sm_with_session.current.permission_mode = "bypassPermissions"
            sm_with_session.current.effort = "max"
            sm_with_session.current.max_turns = 50
            update = _make_update()
            ctx = _make_context(sm_with_session, args=[arg])
            await cmd_autonomous(update, ctx)
            assert sm_with_session.current.permission_mode == "default"


# ---------------------------------------------------------------
# /cron command
# ---------------------------------------------------------------


class TestCmdCron:
    async def test_list_empty(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No cron jobs" in text

    async def test_list_with_jobs(self, sm_with_session):
        from megobari.bot import cmd_cron
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="morning",
                cron_expression="0 7 * * *",
                prompt="Good morning briefing",
                session_name="test",
            )

        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "morning" in text
        assert "0 7 * * *" in text

    @patch("megobari.handlers.scheduling.get_session")
    async def test_list_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_cron

        mock_gs.side_effect = Exception("DB down")
        update = _make_update()
        ctx = _make_context(sm_with_session)
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed to read cron jobs" in text

    async def test_add_job(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(
            sm_with_session,
            args=["add", "morning", "0", "7", "*", "*", "*", "Good morning briefing"],
        )
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "morning" in text
        assert "created" in text.lower()

    async def test_add_job_too_few_args(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["add", "morning"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_add_duplicate(self, sm_with_session):
        from megobari.bot import cmd_cron
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="daily",
                cron_expression="0 9 * * *",
                prompt="test",
                session_name="test",
            )

        update = _make_update()
        ctx = _make_context(
            sm_with_session,
            args=["add", "daily", "0", "9", "*", "*", "*", "test prompt"],
        )
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "already exists" in text

    async def test_add_invalid_cron_expr(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(
            sm_with_session,
            args=["add", "bad", "invalid", "cron", "expr", "ess", "ion", "prompt"],
        )
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Invalid cron" in text

    async def test_remove_job(self, sm_with_session):
        from megobari.bot import cmd_cron
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="temp",
                cron_expression="0 12 * * *",
                prompt="test",
                session_name="test",
            )

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove", "temp"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Deleted" in text

    async def test_remove_not_found(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove", "nope"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_remove_no_name(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_pause_job(self, sm_with_session):
        from megobari.bot import cmd_cron
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="daily",
                cron_expression="0 9 * * *",
                prompt="test",
                session_name="test",
            )

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause", "daily"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Paused" in text

    async def test_pause_not_found(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause", "nope"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_pause_no_name(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_resume_job(self, sm_with_session):
        from megobari.bot import cmd_cron
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="daily",
                cron_expression="0 9 * * *",
                prompt="test",
                session_name="test",
            )
            await repo.toggle_cron_job("daily", enabled=False)

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume", "daily"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Resumed" in text

    async def test_resume_not_found(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume", "nope"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_resume_no_name(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_invalid_subcommand(self, sm_with_session):
        from megobari.bot import cmd_cron

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["bogus"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    @patch("megobari.handlers.scheduling.get_session")
    async def test_remove_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_cron

        mock_gs.side_effect = Exception("DB error")
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove", "something"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed" in text

    @patch("megobari.handlers.scheduling.get_session")
    async def test_pause_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_cron

        mock_gs.side_effect = Exception("DB error")
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause", "something"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed" in text

    @patch("megobari.handlers.scheduling.get_session")
    async def test_resume_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_cron

        mock_gs.side_effect = Exception("DB error")
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume", "something"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed" in text

    @patch("megobari.handlers.scheduling.get_session")
    async def test_add_db_failure(self, mock_gs, sm_with_session):
        """Cover the generic exception path when creating a job fails."""
        # First call succeeds (croniter validation), second call (DB) fails
        from contextlib import asynccontextmanager

        from megobari.bot import cmd_cron

        call_count = 0

        @asynccontextmanager
        async def _fake_gs():
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("DB error")
            # First call: need a real session for croniter validation
            # But since croniter validation doesn't use DB, just raise on any DB call
            raise Exception("DB error")

        mock_gs.side_effect = _fake_gs
        update = _make_update()
        ctx = _make_context(
            sm_with_session,
            args=["add", "test", "0", "7", "*", "*", "*", "hello"],
        )
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed" in text

    async def test_delete_alias(self, sm_with_session):
        """'delete' should work as alias for 'remove'."""
        from megobari.bot import cmd_cron
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="tmp",
                cron_expression="0 12 * * *",
                prompt="test",
                session_name="test",
            )

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["delete", "tmp"])
        await cmd_cron(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Deleted" in text


# ---------------------------------------------------------------
# /heartbeat command
# ---------------------------------------------------------------


class TestCmdHeartbeat:
    async def test_status_stopped_no_checks(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session)
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "stopped" in text.lower()
        assert "No checks" in text

    async def test_status_running_with_checks(self, sm_with_session):
        from megobari.bot import cmd_heartbeat
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_heartbeat_check("disk", "Check disk usage")

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        update = _make_update()
        ctx = _make_context(sm_with_session)
        ctx.bot_data["scheduler"] = mock_scheduler
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "running" in text.lower()
        assert "disk" in text

    async def test_add_check(self, sm_with_session):
        from megobari.bot import cmd_heartbeat
        from megobari.db import Repository, get_session

        update = _make_update()
        ctx = _make_context(
            sm_with_session, args=["add", "disk", "Check", "disk", "usage"]
        )
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "disk" in text
        assert "added" in text.lower() or "✅" in text

        # Verify in DB
        async with get_session() as s:
            repo = Repository(s)
            check = await repo.get_heartbeat_check("disk")
        assert check is not None
        assert check.prompt == "Check disk usage"

    async def test_add_check_duplicate(self, sm_with_session):
        from megobari.bot import cmd_heartbeat
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_heartbeat_check("disk", "Check disk")

        update = _make_update()
        ctx = _make_context(
            sm_with_session, args=["add", "disk", "Another", "check"]
        )
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "already exists" in text

    async def test_add_check_missing_args(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["add", "disk"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_remove_check(self, sm_with_session):
        from megobari.bot import cmd_heartbeat
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_heartbeat_check("disk", "Check disk")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove", "disk"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Deleted" in text

        async with get_session() as s:
            repo = Repository(s)
            check = await repo.get_heartbeat_check("disk")
        assert check is None

    async def test_remove_check_not_found(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove", "nope"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_pause_check(self, sm_with_session):
        from megobari.bot import cmd_heartbeat
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_heartbeat_check("disk", "Check disk")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause", "disk"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Paused" in text

        async with get_session() as s:
            repo = Repository(s)
            check = await repo.get_heartbeat_check("disk")
        assert check.enabled is False

    async def test_resume_check(self, sm_with_session):
        from megobari.bot import cmd_heartbeat
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_heartbeat_check("disk", "Check disk")
            await repo.toggle_heartbeat_check("disk", enabled=False)

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume", "disk"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Resumed" in text

        async with get_session() as s:
            repo = Repository(s)
            check = await repo.get_heartbeat_check("disk")
        assert check.enabled is True

    async def test_remove_missing_args(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["remove"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_pause_missing_args(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_pause_not_found(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["pause", "nope"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_resume_missing_args(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_resume_not_found(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["resume", "nope"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    @patch("megobari.handlers.scheduling.get_session")
    async def test_status_db_error(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_heartbeat

        mock_gs.side_effect = Exception("DB down")
        update = _make_update()
        ctx = _make_context(sm_with_session)
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No checks" in text

    async def test_start(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        scheduler = ctx.bot_data["scheduler"]
        assert scheduler is not None
        assert scheduler.running is True
        scheduler.stop()
        text = update.message.reply_text.call_args[0][0]
        assert "started" in text.lower()

    async def test_start_with_interval(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on", "15"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        scheduler = ctx.bot_data["scheduler"]
        assert scheduler is not None
        assert scheduler._heartbeat_interval == 15 * 60
        scheduler.stop()
        text = update.message.reply_text.call_args[0][0]
        assert "15" in text

    async def test_start_invalid_interval(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on", "abc"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_start_stops_existing(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        existing = MagicMock()
        existing.running = True
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["on"])
        ctx.bot_data["scheduler"] = existing
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        existing.stop.assert_called_once()
        new_scheduler = ctx.bot_data["scheduler"]
        assert new_scheduler is not None
        assert new_scheduler is not existing
        new_scheduler.stop()

    async def test_stop(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        mock_scheduler = MagicMock()
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["off"])
        ctx.bot_data["scheduler"] = mock_scheduler
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        mock_scheduler.stop.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "stopped" in text.lower()

    async def test_stop_no_scheduler(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["off"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "stopped" in text.lower()

    async def test_now_with_scheduler(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        mock_scheduler = MagicMock()
        mock_scheduler._run_heartbeat = AsyncMock()
        update = _make_update()
        ctx = _make_context(sm_with_session, args=["now"])
        ctx.bot_data["scheduler"] = mock_scheduler
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Running" in text

    async def test_now_no_scheduler(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["now"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No scheduler" in text

    async def test_invalid_subcommand(self, sm_with_session):
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["bogus"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_start_no_session(self, session_manager):
        """When no active session, should use home dir."""
        from megobari.bot import cmd_heartbeat

        update = _make_update()
        ctx = _make_context(session_manager, args=["start"])
        ctx.bot_data["scheduler"] = None
        ctx.bot_data["config"] = None
        await cmd_heartbeat(update, ctx)
        scheduler = ctx.bot_data["scheduler"]
        assert scheduler is not None
        assert scheduler.running is True
        scheduler.stop()
