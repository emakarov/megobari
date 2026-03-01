"""Cron and heartbeat command handlers."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from megobari.db import Repository, get_session
from megobari.transport import TransportContext

logger = logging.getLogger(__name__)


async def cmd_cron(ctx: TransportContext) -> None:
    """Handle /cron command: manage scheduled tasks."""
    fmt = ctx.formatter
    args = ctx.args
    sm = ctx.session_manager
    session = sm.current

    if not args:
        # List all cron jobs
        try:
            async with get_session() as s:
                repo = Repository(s)
                jobs = await repo.list_cron_jobs()
        except Exception:
            await ctx.reply("Failed to read cron jobs from DB.")
            return
        if not jobs:
            await ctx.reply("No cron jobs. Use /cron add <name> <expr> <prompt>")
            return
        lines = [fmt.bold("Scheduled jobs:"), ""]
        for j in jobs:
            state = "\u2705" if j.enabled else "\u23f8"
            last = j.last_run_at.strftime("%m-%d %H:%M") if j.last_run_at else "never"
            preview = j.prompt[:60] + ("..." if len(j.prompt) > 60 else "")
            lines.append(
                f"{state} {fmt.bold(fmt.escape(j.name))} "
                f"{fmt.code(j.cron_expression)} [{j.session_name}]"
            )
            lines.append(f"   {fmt.escape(preview)} (last: {last})")
        await ctx.reply("\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub == "add":
        # /cron add <name> <cron_expr(5 fields)> <prompt...>
        if len(args) < 8:
            await ctx.reply(
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
            await ctx.reply(f"Invalid cron expression: {fmt.code(cron_expr)}", formatted=True)
            return

        try:
            async with get_session() as s:
                repo = Repository(s)
                existing = await repo.get_cron_job(name)
                if existing:
                    await ctx.reply(f"Job '{name}' already exists. Delete it first.")
                    return
                await repo.add_cron_job(
                    name=name,
                    cron_expression=cron_expr,
                    prompt=prompt,
                    session_name=session.name if session else "default",
                )
            await ctx.reply(
                f"\u2705 Cron job '{name}' created\n"
                f"  Schedule: {cron_expr}\n"
                f"  Session: {session.name if session else 'default'}\n"
                f"  Prompt: {prompt[:100]}",
            )
        except Exception:
            await ctx.reply("Failed to create cron job.")

    elif sub == "remove" or sub == "delete":
        if len(args) < 2:
            await ctx.reply("Usage: /cron remove <name>")
            return
        name = args[1]
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_cron_job(name)
            if deleted:
                await ctx.reply(f"\u2705 Deleted cron job '{name}'")
            else:
                await ctx.reply(f"Job '{name}' not found.")
        except Exception:
            await ctx.reply("Failed to delete cron job.")

    elif sub in ("pause", "disable"):
        if len(args) < 2:
            await ctx.reply("Usage: /cron pause <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                job = await repo.toggle_cron_job(args[1], enabled=False)
            if job:
                await ctx.reply(f"\u23f8 Paused '{args[1]}'")
            else:
                await ctx.reply(f"Job '{args[1]}' not found.")
        except Exception:
            await ctx.reply("Failed to pause cron job.")

    elif sub in ("resume", "enable"):
        if len(args) < 2:
            await ctx.reply("Usage: /cron resume <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                job = await repo.toggle_cron_job(args[1], enabled=True)
            if job:
                await ctx.reply(f"\u2705 Resumed '{args[1]}'")
            else:
                await ctx.reply(f"Job '{args[1]}' not found.")
        except Exception:
            await ctx.reply("Failed to resume cron job.")

    else:
        await ctx.reply(
            "Usage:\n"
            "/cron \u2014 list all jobs\n"
            "/cron add <name> <m> <h> <dom> <mon> <dow> <prompt>\n"
            "/cron remove <name>\n"
            "/cron pause <name>\n"
            "/cron resume <name>",
        )


async def cmd_heartbeat(ctx: TransportContext) -> None:
    """Handle /heartbeat command: manage heartbeat daemon and checks."""
    from megobari.scheduler import Scheduler

    fmt = ctx.formatter
    args = ctx.args
    scheduler: Scheduler | None = ctx.bot_data.get("scheduler")

    if not args:
        # Show status + list checks
        running = scheduler and scheduler.running
        status = "\U0001f493 running" if running else "\U0001f4a4 stopped"
        try:
            async with get_session() as s:
                repo = Repository(s)
                checks = await repo.list_heartbeat_checks()
        except Exception:
            checks = []
        lines = [f"Heartbeat: {status}", ""]
        if checks:
            for c in checks:
                icon = "\u2705" if c.enabled else "\u23f8"
                lines.append(
                    f"{icon} {fmt.bold(fmt.escape(c.name))}: "
                    f"{fmt.escape(c.prompt[:80])}"
                )
        else:
            lines.append("No checks configured. Use /heartbeat add <name> <prompt>")
        await ctx.reply("\n".join(lines), formatted=True)
        return

    sub = args[0].lower()
    chat_id = ctx.chat_id

    if sub == "add":
        if len(args) < 3:
            await ctx.reply(
                "Usage: /heartbeat add <name> <prompt>\n"
                "Example: /heartbeat add disk Check if disk usage exceeds 90%",
            )
            return
        name = args[1]
        prompt = " ".join(args[2:])
        try:
            async with get_session() as s:
                repo = Repository(s)
                existing = await repo.get_heartbeat_check(name)
                if existing:
                    await ctx.reply(f"Check '{name}' already exists. Delete it first.")
                    return
                await repo.add_heartbeat_check(name=name, prompt=prompt)
            await ctx.reply(f"\u2705 Check '{name}' added: {prompt[:100]}")
        except Exception:
            await ctx.reply("Failed to add heartbeat check.")

    elif sub in ("remove", "delete"):
        if len(args) < 2:
            await ctx.reply("Usage: /heartbeat remove <name>")
            return
        name = args[1]
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_heartbeat_check(name)
            if deleted:
                await ctx.reply(f"\u2705 Deleted check '{name}'")
            else:
                await ctx.reply(f"Check '{name}' not found.")
        except Exception:
            await ctx.reply("Failed to delete heartbeat check.")

    elif sub in ("pause", "disable"):
        if len(args) < 2:
            await ctx.reply("Usage: /heartbeat pause <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                check = await repo.toggle_heartbeat_check(args[1], enabled=False)
            if check:
                await ctx.reply(f"\u23f8 Paused '{args[1]}'")
            else:
                await ctx.reply(f"Check '{args[1]}' not found.")
        except Exception:
            await ctx.reply("Failed to pause heartbeat check.")

    elif sub in ("resume", "enable"):
        if len(args) < 2:
            await ctx.reply("Usage: /heartbeat resume <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                check = await repo.toggle_heartbeat_check(args[1], enabled=True)
            if check:
                await ctx.reply(f"\u2705 Resumed '{args[1]}'")
            else:
                await ctx.reply(f"Check '{args[1]}' not found.")
        except Exception:
            await ctx.reply("Failed to resume heartbeat check.")

    elif sub in ("on", "start"):
        interval = 30
        if len(args) > 1:
            try:
                interval = int(args[1])
            except ValueError:
                await ctx.reply("Usage: /heartbeat on [minutes]")
                return

        if scheduler and scheduler.running:
            scheduler.stop()

        sm = ctx.session_manager
        session = sm.current
        cwd = session.cwd if session else str(Path.home())
        scheduler = Scheduler(
            bot=ctx.bot_data["_bot"],
            chat_id=chat_id,
            cwd=cwd,
            heartbeat_interval_min=interval,
        )
        scheduler.start()
        ctx.bot_data["scheduler"] = scheduler
        await ctx.reply(f"\U0001f493 Heartbeat started (every {interval}min)")

    elif sub in ("off", "stop"):
        if scheduler:
            scheduler.stop()
            ctx.bot_data["scheduler"] = None
        await ctx.reply("\U0001f4a4 Heartbeat stopped")

    elif sub == "now":
        if scheduler:
            asyncio.create_task(scheduler._run_heartbeat())
            await ctx.reply("\U0001f493 Running heartbeat check now...")
        else:
            await ctx.reply("No scheduler running. Use /heartbeat on first.")

    else:
        await ctx.reply(
            "Usage:\n"
            "/heartbeat \u2014 status & list checks\n"
            "/heartbeat add <name> <prompt> \u2014 add a check\n"
            "/heartbeat remove <name> \u2014 remove a check\n"
            "/heartbeat pause <name> \u2014 disable a check\n"
            "/heartbeat resume <name> \u2014 enable a check\n"
            "/heartbeat on [minutes] \u2014 start daemon (default 30min)\n"
            "/heartbeat off \u2014 stop daemon\n"
            "/heartbeat now \u2014 run checks immediately",
        )
