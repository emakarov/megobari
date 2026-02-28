"""Cron scheduler — runs scheduled prompts and heartbeat checks."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from croniter import croniter

from megobari.claude_bridge import send_to_claude
from megobari.db import Repository, get_session
from megobari.session import Session

logger = logging.getLogger(__name__)

# Heartbeat defaults
_HEARTBEAT_INTERVAL_MIN = 30
_HEARTBEAT_FILE = "HEARTBEAT.md"
_HEARTBEAT_OK = "HEARTBEAT_OK"

_DEFAULT_HEARTBEAT_CONTENT = """\
# Heartbeat checklist

- Check if any background tasks have completed
- If anything important happened recently, summarize it briefly
- Otherwise respond with HEARTBEAT_OK
"""


class Scheduler:
    """Manages cron jobs and heartbeat. Runs as an asyncio background task."""

    def __init__(
        self,
        bot,
        chat_id: int,
        cwd: str | None = None,
        heartbeat_interval_min: int = _HEARTBEAT_INTERVAL_MIN,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._cwd = cwd or str(Path.home())
        self._heartbeat_interval = heartbeat_interval_min * 60  # seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # -- lifecycle --

    def start(self) -> None:
        """Start the scheduler loop as a background task."""
        if self._task and not self._task.done():
            logger.warning("Scheduler already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="scheduler")
        logger.info("Scheduler started (heartbeat every %ds)", self._heartbeat_interval)

    def stop(self) -> None:
        """Stop the scheduler loop."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Scheduler stopped")

    @property
    def running(self) -> bool:
        """Return True if the scheduler loop is active."""
        return self._task is not None and not self._task.done()

    # -- main loop --

    async def _loop(self) -> None:
        """Run cron checks every 60 seconds."""
        try:
            last_heartbeat = datetime.now(timezone.utc)
            while not self._stop_event.is_set():
                now = datetime.now(timezone.utc)

                # Check cron jobs
                await self._run_due_crons(now)

                # Heartbeat check
                if self._heartbeat_interval > 0:
                    elapsed = (now - last_heartbeat).total_seconds()
                    if elapsed >= self._heartbeat_interval:
                        await self._run_heartbeat()
                        last_heartbeat = datetime.now(timezone.utc)

                # Sleep 60s between checks
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=60
                    )
                    break  # stop_event was set
                except asyncio.TimeoutError:
                    pass  # normal tick
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Scheduler loop error")

    # -- cron execution --

    async def _run_due_crons(self, now: datetime) -> None:
        """Check and run any due cron jobs."""
        try:
            async with get_session() as s:
                repo = Repository(s)
                jobs = await repo.list_cron_jobs(enabled_only=True)
        except Exception:
            logger.debug("Failed to load cron jobs", exc_info=True)
            return

        for job in jobs:
            try:
                cron = croniter(job.cron_expression, job.last_run_at or job.created_at)
                next_run = cron.get_next(datetime)
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
                if next_run <= now:
                    logger.info("Running cron job: %s", job.name)
                    asyncio.create_task(
                        self._execute_cron(job.name, job.prompt, job.session_name, job.isolated)
                    )
                    # Update last_run_at
                    try:
                        async with get_session() as s:
                            repo = Repository(s)
                            await repo.update_cron_last_run(job.name)
                    except Exception:
                        logger.debug("Failed to update cron last_run", exc_info=True)
            except Exception:
                logger.warning("Bad cron expression for job %s: %s", job.name, job.cron_expression)

    async def _execute_cron(
        self, name: str, prompt: str, session_name: str, isolated: bool
    ) -> None:
        """Execute a single cron job prompt and send result to Telegram."""
        try:
            session = Session(name=f"cron:{name}" if isolated else session_name, cwd=self._cwd)
            response, _, _, _ = await send_to_claude(prompt=prompt, session=session)

            if response and response.strip():
                msg = f"🕐 *Cron: {name}*\n\n{response}"
                # Truncate if too long
                if len(msg) > 4000:
                    msg = msg[:3997] + "..."
                await self._bot.send_message(chat_id=self._chat_id, text=msg)
        except Exception:
            logger.exception("Cron job %s failed", name)
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=f"❌ Cron job *{name}* failed. Check logs.",
                )
            except Exception:
                pass

    # -- heartbeat --

    async def _run_heartbeat(self) -> None:
        """Run heartbeat: read HEARTBEAT.md, send to Claude, notify if needed."""
        heartbeat_path = Path(self._cwd) / _HEARTBEAT_FILE
        if not heartbeat_path.exists():
            # Create default heartbeat file
            heartbeat_path.write_text(_DEFAULT_HEARTBEAT_CONTENT)
            logger.info("Created default %s", heartbeat_path)

        try:
            checklist = heartbeat_path.read_text()
        except Exception:
            logger.debug("Failed to read heartbeat file", exc_info=True)
            return

        prompt = (
            "This is an automated heartbeat check. Process this checklist and respond:\n"
            "- If nothing needs attention, respond with exactly: HEARTBEAT_OK\n"
            "- If something needs the user's attention, describe it briefly.\n\n"
            f"{checklist}"
        )

        try:
            session = Session(name="_heartbeat", cwd=self._cwd)
            response, _, _, _ = await send_to_claude(prompt=prompt, session=session)

            if response and _HEARTBEAT_OK not in response:
                # Something needs attention — notify user
                msg = f"💓 *Heartbeat*\n\n{response}"
                if len(msg) > 4000:
                    msg = msg[:3997] + "..."
                await self._bot.send_message(chat_id=self._chat_id, text=msg)
            else:
                logger.debug("Heartbeat OK — nothing to report")
        except Exception:
            logger.exception("Heartbeat failed")
