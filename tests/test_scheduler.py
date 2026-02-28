"""Tests for the Scheduler class (cron execution and heartbeat)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.db import close_db, init_db


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


def _make_scheduler(
    chat_id: int = 12345,
    cwd: str | None = None,
    heartbeat_interval_min: int = 30,
):
    from megobari.scheduler import Scheduler

    bot = AsyncMock()
    return Scheduler(
        bot=bot,
        chat_id=chat_id,
        cwd=cwd or str(Path.home()),
        heartbeat_interval_min=heartbeat_interval_min,
    )


class TestSchedulerLifecycle:
    def test_init_defaults(self):
        from megobari.scheduler import Scheduler

        bot = AsyncMock()
        s = Scheduler(bot=bot, chat_id=42)
        assert s._chat_id == 42
        assert s._heartbeat_interval == 30 * 60
        assert s._task is None

    def test_init_custom_interval(self):
        s = _make_scheduler(heartbeat_interval_min=10)
        assert s._heartbeat_interval == 600

    def test_init_custom_cwd(self, tmp_path):
        s = _make_scheduler(cwd=str(tmp_path))
        assert s._cwd == str(tmp_path)

    def test_not_running_initially(self):
        s = _make_scheduler()
        assert s.running is False

    async def test_start_creates_task(self):
        s = _make_scheduler()
        s.start()
        assert s.running is True
        assert s._task is not None
        # Clean up
        s.stop()

    async def test_start_idempotent(self):
        s = _make_scheduler()
        s.start()
        first_task = s._task
        s.start()  # second call should be ignored (warning logged)
        assert s._task is first_task
        s.stop()

    async def test_stop(self):
        s = _make_scheduler()
        s.start()
        assert s.running is True
        s.stop()
        assert s._task is None

    def test_stop_when_not_running(self):
        s = _make_scheduler()
        # Should not raise
        s.stop()
        assert s._task is None

    async def test_running_false_after_cancel(self):
        s = _make_scheduler()
        s.start()
        s._task.cancel()
        s._task = None
        assert s.running is False


class TestSchedulerHeartbeat:
    async def _add_check(self, name: str = "disk", prompt: str = "Check disk usage"):
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            await repo.add_heartbeat_check(name=name, prompt=prompt)

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_no_checks_skips(self, mock_send):
        s = _make_scheduler()
        await s._run_heartbeat()
        mock_send.assert_not_called()
        s._bot.send_message.assert_not_called()

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_ok_no_notification(self, mock_send):
        await self._add_check()
        mock_send.return_value = ("HEARTBEAT_OK", [], None, MagicMock())
        s = _make_scheduler()

        await s._run_heartbeat()

        s._bot.send_message.assert_not_called()

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_alert_sends_message(self, mock_send):
        await self._add_check()
        mock_send.return_value = (
            "Background task completed: build succeeded",
            [],
            None,
            MagicMock(),
        )
        s = _make_scheduler()

        await s._run_heartbeat()

        s._bot.send_message.assert_called_once()
        msg = s._bot.send_message.call_args[1]["text"]
        assert "Heartbeat" in msg
        assert "build succeeded" in msg

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_builds_prompt_from_db(self, mock_send):
        await self._add_check("ci", "Check CI pipeline")
        await self._add_check("prs", "Review open PRs")
        mock_send.return_value = ("HEARTBEAT_OK", [], None, MagicMock())
        s = _make_scheduler()

        await s._run_heartbeat()

        prompt = mock_send.call_args[1]["prompt"]
        assert "Check CI pipeline" in prompt
        assert "Review open PRs" in prompt

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_skips_disabled_checks(self, mock_send):
        from megobari.db import Repository, get_session

        await self._add_check("active", "Active check")
        await self._add_check("paused", "Paused check")
        async with get_session() as s:
            repo = Repository(s)
            await repo.toggle_heartbeat_check("paused", enabled=False)

        mock_send.return_value = ("HEARTBEAT_OK", [], None, MagicMock())
        s = _make_scheduler()
        await s._run_heartbeat()

        prompt = mock_send.call_args[1]["prompt"]
        assert "Active check" in prompt
        assert "Paused check" not in prompt

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_long_message_truncated(self, mock_send):
        await self._add_check()
        mock_send.return_value = ("x" * 5000, [], None, MagicMock())
        s = _make_scheduler()

        await s._run_heartbeat()

        msg = s._bot.send_message.call_args[1]["text"]
        assert len(msg) <= 4000

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_error_handled(self, mock_send):
        await self._add_check()
        mock_send.side_effect = RuntimeError("boom")
        s = _make_scheduler()

        # Should not raise
        await s._run_heartbeat()

    @patch("megobari.scheduler.send_to_claude")
    async def test_heartbeat_empty_response(self, mock_send):
        await self._add_check()
        mock_send.return_value = ("", [], None, MagicMock())
        s = _make_scheduler()

        await s._run_heartbeat()

        s._bot.send_message.assert_not_called()


class TestSchedulerCronExecution:
    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_sends_result(self, mock_send):
        mock_send.return_value = ("Task completed!", [], None, MagicMock())
        s = _make_scheduler()

        await s._execute_cron("test_job", "Run the tests", "default", isolated=False)

        # Should send message to telegram
        s._bot.send_message.assert_called_once()
        msg = s._bot.send_message.call_args[1]["text"]
        assert "test_job" in msg
        assert "Task completed!" in msg

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_isolated(self, mock_send):
        mock_send.return_value = ("Done", [], None, MagicMock())
        s = _make_scheduler()

        await s._execute_cron("iso_job", "Run isolated", "default", isolated=True)

        # Should create session with cron:name prefix
        session_arg = mock_send.call_args[1]["session"]
        assert session_arg.name == "cron:iso_job"

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_non_isolated(self, mock_send):
        mock_send.return_value = ("Done", [], None, MagicMock())
        s = _make_scheduler()

        await s._execute_cron("job", "Run", "mysession", isolated=False)

        session_arg = mock_send.call_args[1]["session"]
        assert session_arg.name == "mysession"

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_long_message_truncated(self, mock_send):
        mock_send.return_value = ("x" * 5000, [], None, MagicMock())
        s = _make_scheduler()

        await s._execute_cron("long_job", "Run", "default", isolated=False)

        msg = s._bot.send_message.call_args[1]["text"]
        assert len(msg) <= 4000

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_empty_response_no_message(self, mock_send):
        mock_send.return_value = ("", [], None, MagicMock())
        s = _make_scheduler()

        await s._execute_cron("silent_job", "Run", "default", isolated=False)

        s._bot.send_message.assert_not_called()

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_whitespace_only_no_message(self, mock_send):
        mock_send.return_value = ("   \n  ", [], None, MagicMock())
        s = _make_scheduler()

        await s._execute_cron("ws_job", "Run", "default", isolated=False)

        s._bot.send_message.assert_not_called()

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_error_notifies(self, mock_send):
        mock_send.side_effect = RuntimeError("API down")
        s = _make_scheduler()

        await s._execute_cron("fail_job", "Run", "default", isolated=False)

        s._bot.send_message.assert_called_once()
        msg = s._bot.send_message.call_args[1]["text"]
        assert "fail_job" in msg
        assert "failed" in msg.lower()

    @patch("megobari.scheduler.send_to_claude")
    async def test_execute_cron_error_notify_also_fails(self, mock_send):
        mock_send.side_effect = RuntimeError("API down")
        s = _make_scheduler()
        s._bot.send_message.side_effect = RuntimeError("send failed too")

        # Should not raise even if both calls fail
        await s._execute_cron("doomed", "Run", "default", isolated=False)


class TestSchedulerRunDueCrons:
    @patch("megobari.scheduler.send_to_claude")
    async def test_run_due_crons_triggers_job(self, mock_send):
        from megobari.db import Repository, get_session

        mock_send.return_value = ("Done!", [], None, MagicMock())

        # Create a cron job that is past due
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        async with get_session() as s:
            repo = Repository(s)
            job = await repo.add_cron_job(
                name="due_job",
                cron_expression="* * * * *",  # every minute
                prompt="Run this",
                session_name="default",
            )
            # Manually set created_at to the past so it will be due
            job.created_at = past
            await s.flush()

        s = _make_scheduler()
        now = datetime.now(timezone.utc)
        await s._run_due_crons(now)

        # Give the fire-and-forget task a chance to run
        await asyncio.sleep(0.1)

        # send_to_claude should have been called
        assert mock_send.called

    @patch("megobari.scheduler.get_session")
    async def test_run_due_crons_db_failure(self, mock_gs):
        """Should handle DB failure gracefully."""
        mock_gs.side_effect = Exception("DB down")
        s = _make_scheduler()
        # Should not raise
        await s._run_due_crons(datetime.now(timezone.utc))

    @patch("megobari.scheduler.send_to_claude")
    async def test_run_due_crons_skips_not_due(self, mock_send):
        from megobari.db import Repository, get_session

        # Create a cron job that is NOT due (runs at midnight, check now isn't midnight)
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_cron_job(
                name="future_job",
                cron_expression="0 0 1 1 *",  # midnight Jan 1 only
                prompt="Run this",
                session_name="default",
            )

        s = _make_scheduler()
        # Check at a time that is definitely not midnight on Jan 1
        now = datetime(2025, 6, 15, 14, 30, tzinfo=timezone.utc)
        await s._run_due_crons(now)

        await asyncio.sleep(0.1)
        mock_send.assert_not_called()


class TestSchedulerLoop:
    async def test_loop_runs_and_stops(self):
        s = _make_scheduler(heartbeat_interval_min=0)
        s.start()
        assert s.running is True

        await asyncio.sleep(0.05)
        s.stop()

        # Give the task a moment to clean up
        await asyncio.sleep(0.05)
        assert s.running is False

    async def test_loop_cancelled(self):
        s = _make_scheduler()
        s.start()
        await asyncio.sleep(0.01)
        # Cancel the task directly
        s._task.cancel()
        try:
            await s._task
        except asyncio.CancelledError:
            pass
