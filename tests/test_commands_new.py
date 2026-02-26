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
    @patch("megobari.bot._persist_usage", new_callable=AsyncMock)
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

    @patch("megobari.bot._persist_usage", new_callable=AsyncMock)
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

    @patch("megobari.bot._persist_usage", new_callable=AsyncMock)
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

    @patch("megobari.bot.send_to_claude")
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

    @patch("megobari.bot.get_session")
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

    @patch("megobari.bot.get_session")
    async def test_usage_all_db_failure(self, mock_gs, sm_with_session):
        from megobari.bot import cmd_usage

        mock_gs.side_effect = Exception("DB error")

        update = _make_update()
        ctx = _make_context(sm_with_session, args=["all"])
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Failed to read usage" in text
