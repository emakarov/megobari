"""Cron and heartbeat command handlers."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from megobari.db import Repository, get_session

from ._common import _get_sm, _reply, fmt

logger = logging.getLogger(__name__)


async def cmd_cron(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cron command: manage scheduled tasks."""
    args = context.args or []
    sm = _get_sm(context)
    session = sm.current

    if not args:
        # List all cron jobs
        try:
            async with get_session() as s:
                repo = Repository(s)
                jobs = await repo.list_cron_jobs()
        except Exception:
            await _reply(update, "Failed to read cron jobs from DB.")
            return
        if not jobs:
            await _reply(update, "No cron jobs. Use /cron add <name> <expr> <prompt>")
            return
        lines = [fmt.bold("Scheduled jobs:"), ""]
        for j in jobs:
            state = "✅" if j.enabled else "⏸"
            last = j.last_run_at.strftime("%m-%d %H:%M") if j.last_run_at else "never"
            preview = j.prompt[:60] + ("..." if len(j.prompt) > 60 else "")
            lines.append(
                f"{state} {fmt.bold(fmt.escape(j.name))} "
                f"{fmt.code(j.cron_expression)} [{j.session_name}]"
            )
            lines.append(f"   {fmt.escape(preview)} (last: {last})")
        await _reply(update, "\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub == "add":
        # /cron add <name> <cron_expr(5 fields)> <prompt...>
        if len(args) < 8:
            await _reply(
                update,
                "Usage: /cron add <name> <min> <hour> <dom> <mon> <dow> <prompt...>\n"
                "Example: /cron add morning 0 7 * * * Good morning briefing",
            )
            return
        name = args[1]
        cron_expr = " ".join(args[2:7])
        prompt = " ".join(args[7:])

        # Validate cron expression
        try:
            from croniter import croniter
            croniter(cron_expr)
        except (ValueError, KeyError):
            await _reply(update, f"Invalid cron expression: {fmt.code(cron_expr)}", formatted=True)
            return

        try:
            async with get_session() as s:
                repo = Repository(s)
                existing = await repo.get_cron_job(name)
                if existing:
                    await _reply(update, f"Job '{name}' already exists. Delete it first.")
                    return
                await repo.add_cron_job(
                    name=name,
                    cron_expression=cron_expr,
                    prompt=prompt,
                    session_name=session.name if session else "default",
                )
            await _reply(
                update,
                f"✅ Cron job '{name}' created\n"
                f"  Schedule: {cron_expr}\n"
                f"  Session: {session.name if session else 'default'}\n"
                f"  Prompt: {prompt[:100]}",
            )
        except Exception:
            await _reply(update, "Failed to create cron job.")

    elif sub == "remove" or sub == "delete":
        if len(args) < 2:
            await _reply(update, "Usage: /cron remove <name>")
            return
        name = args[1]
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_cron_job(name)
            if deleted:
                await _reply(update, f"✅ Deleted cron job '{name}'")
            else:
                await _reply(update, f"Job '{name}' not found.")
        except Exception:
            await _reply(update, "Failed to delete cron job.")

    elif sub in ("pause", "disable"):
        if len(args) < 2:
            await _reply(update, "Usage: /cron pause <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                job = await repo.toggle_cron_job(args[1], enabled=False)
            if job:
                await _reply(update, f"⏸ Paused '{args[1]}'")
            else:
                await _reply(update, f"Job '{args[1]}' not found.")
        except Exception:
            await _reply(update, "Failed to pause cron job.")

    elif sub in ("resume", "enable"):
        if len(args) < 2:
            await _reply(update, "Usage: /cron resume <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                job = await repo.toggle_cron_job(args[1], enabled=True)
            if job:
                await _reply(update, f"✅ Resumed '{args[1]}'")
            else:
                await _reply(update, f"Job '{args[1]}' not found.")
        except Exception:
            await _reply(update, "Failed to resume cron job.")

    else:
        await _reply(
            update,
            "Usage:\n"
            "/cron — list all jobs\n"
            "/cron add <name> <m> <h> <dom> <mon> <dow> <prompt>\n"
            "/cron remove <name>\n"
            "/cron pause <name>\n"
            "/cron resume <name>",
        )


async def cmd_heartbeat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /heartbeat command: manage heartbeat daemon."""
    from megobari.scheduler import Scheduler

    args = context.args or []
    scheduler: Scheduler | None = context.bot_data.get("scheduler")

    if not args:
        if scheduler and scheduler.running:
            await _reply(update, "💓 Heartbeat is running")
        else:
            await _reply(update, "💤 Heartbeat is stopped. Use /heartbeat on")
        return

    sub = args[0].lower()
    chat_id = update.effective_chat.id

    if sub in ("on", "start"):
        interval = 30
        if len(args) > 1:
            try:
                interval = int(args[1])
            except ValueError:
                await _reply(update, "Usage: /heartbeat on [minutes]")
                return

        if scheduler and scheduler.running:
            scheduler.stop()

        sm = _get_sm(context)
        session = sm.current
        cwd = session.cwd if session else str(Path.home())
        scheduler = Scheduler(
            bot=context.bot,
            chat_id=chat_id,
            cwd=cwd,
            heartbeat_interval_min=interval,
        )
        scheduler.start()
        context.bot_data["scheduler"] = scheduler
        await _reply(update, f"💓 Heartbeat started (every {interval}min)")

    elif sub in ("off", "stop"):
        if scheduler:
            scheduler.stop()
            context.bot_data["scheduler"] = None
        await _reply(update, "💤 Heartbeat stopped")

    elif sub == "now":
        # Run heartbeat immediately
        if scheduler:
            asyncio.create_task(scheduler._run_heartbeat())
            await _reply(update, "💓 Running heartbeat check now...")
        else:
            await _reply(update, "No scheduler running. Use /heartbeat on first.")

    else:
        await _reply(
            update,
            "Usage:\n"
            "/heartbeat — show status\n"
            "/heartbeat on [minutes] — start (default 30min)\n"
            "/heartbeat off — stop\n"
            "/heartbeat now — run check immediately",
        )
