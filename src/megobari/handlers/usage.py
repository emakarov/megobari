"""Usage tracking, context info, compact, and history command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from megobari.claude_bridge import send_to_claude
from megobari.db import Repository, get_session
from megobari.message_utils import split_message

from ._common import SessionUsage, _get_sm, _reply, fmt

logger = logging.getLogger(__name__)


async def cmd_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /usage command: show session and historical usage stats."""
    sm = _get_sm(context)
    session = sm.current
    args = context.args or []

    if args and args[0].lower() == "all":
        # Show all-time totals from DB
        try:
            async with get_session() as s:
                repo = Repository(s)
                total = await repo.get_total_usage()
        except Exception:
            await _reply(update, "Failed to read usage from DB.")
            return

        if total["query_count"] == 0:
            await _reply(update, "No usage recorded yet.")
            return

        duration_s = total["total_duration_ms"] / 1000
        lines = [
            fmt.bold("All-time usage:"),
            f"{fmt.bold('Cost:')} ${total['total_cost']:.4f}",
            f"{fmt.bold('Turns:')} {total['total_turns']} ({total['query_count']} queries)",
            f"{fmt.bold('Sessions:')} {total['session_count']}",
            f"{fmt.bold('API time:')} {duration_s:.1f}s",
        ]
        await _reply(update, "\n".join(lines), formatted=True)
        return

    # Show current session usage — combine in-memory + DB historical
    lines = [f"{fmt.bold('Session:')} {fmt.escape(session.name)}"]

    # Current run (in-memory)
    usage_map: dict[str, SessionUsage] = context.bot_data.get("usage", {})
    su = usage_map.get(session.name)

    # Historical (DB)
    try:
        async with get_session() as s:
            repo = Repository(s)
            db_usage = await repo.get_session_usage(session.name)
    except Exception:
        db_usage = None

    if su and su.message_count > 0:
        duration_s = su.total_duration_ms / 1000
        lines.append("")
        lines.append(fmt.bold("This run:"))
        lines.append(f"  Cost: ${su.total_cost_usd:.4f}")
        lines.append(f"  Turns: {su.total_turns} ({su.message_count} messages)")
        lines.append(f"  API time: {duration_s:.1f}s")

    if db_usage and db_usage["query_count"] > 0:
        duration_s = db_usage["total_duration_ms"] / 1000
        lines.append("")
        lines.append(fmt.bold("All-time (this session):"))
        lines.append(f"  Cost: ${db_usage['total_cost']:.4f}")
        lines.append(f"  Turns: {db_usage['total_turns']} ({db_usage['query_count']} queries)")
        lines.append(f"  API time: {duration_s:.1f}s")

    if (not su or su.message_count == 0) and (not db_usage or db_usage["query_count"] == 0):
        await _reply(update, "No usage recorded yet for this session.")
        return

    await _reply(update, "\n".join(lines), formatted=True)


async def cmd_compact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /compact command: summarize conversation and reset context."""
    sm = _get_sm(context)
    session = sm.current
    chat_id = update.effective_chat.id

    if not session.session_id:
        await _reply(update, "No active context to compact.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Ask Claude to summarize the conversation
    summary_prompt = (
        "Summarize our conversation. Produce two parts separated by the "
        "exact delimiter '---FULL---' on its own line:\n"
        "1. First, a SHORT one-line summary (max 150 chars) capturing the essence.\n"
        "2. Then '---FULL---'\n"
        "3. Then a FULL summary with bullet points covering decisions made, "
        "tasks completed, and any ongoing work."
    )

    response_text, _, _, _ = await send_to_claude(
        prompt=summary_prompt, session=session,
    )

    # Parse short + full summary from response
    from megobari.summarizer import _parse_summary
    short_summary, full_summary = _parse_summary(response_text)

    # Clear context (break session)
    session.session_id = None
    sm._save()

    # Seed new context with the summary
    seed_prompt = (
        f"Here is a summary of our previous conversation context:\n\n"
        f"{full_summary}\n\n"
        f"Continue from here. The user has compacted the conversation."
    )
    _, _, new_session_id, _ = await send_to_claude(
        prompt=seed_prompt, session=session,
    )

    if new_session_id:
        sm.update_session_id(session.name, new_session_id)

    # Save as a summary in DB
    uid = update.effective_user.id if update.effective_user else None
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(
                session_name=session.name,
                summary=full_summary,
                short_summary=short_summary,
                message_count=0,
                is_milestone=True,
                user_id=uid,
            )
    except Exception:
        logger.warning("Failed to save compact summary to DB")

    compact_msg = f"📦 Context compacted.\n\n{fmt.bold('Summary:')}\n{fmt.escape(full_summary)}"
    for chunk in split_message(compact_msg):
        await _reply(update, chunk, formatted=True)


async def cmd_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /context command: show token usage for current session."""
    sm = _get_sm(context)
    session = sm.current

    # In-memory (this run)
    usage_map: dict[str, SessionUsage] = context.bot_data.get("usage", {})
    su = usage_map.get(session.name)

    # DB history
    try:
        async with get_session() as s:
            repo = Repository(s)
            db_usage = await repo.get_session_usage(session.name)
    except Exception:
        db_usage = None

    lines = [f"{fmt.bold('Context info for:')} {fmt.escape(session.name)}"]

    if su and su.message_count > 0:
        total_tokens = su.input_tokens + su.output_tokens
        lines.append("")
        lines.append(fmt.bold("This run:"))
        lines.append(f"  Input tokens: {su.input_tokens:,}")
        lines.append(f"  Output tokens: {su.output_tokens:,}")
        lines.append(f"  Total tokens: {total_tokens:,}")
        lines.append(f"  Messages: {su.message_count}")

    if db_usage and db_usage["query_count"] > 0:
        db_total = db_usage["total_input_tokens"] + db_usage["total_output_tokens"]
        lines.append("")
        lines.append(fmt.bold("All-time (this session):"))
        lines.append(f"  Input tokens: {db_usage['total_input_tokens']:,}")
        lines.append(f"  Output tokens: {db_usage['total_output_tokens']:,}")
        lines.append(f"  Total tokens: {db_total:,}")
        lines.append(f"  Queries: {db_usage['query_count']}")

    if (not su or su.message_count == 0) and (not db_usage or db_usage["query_count"] == 0):
        lines.append("\nNo token data recorded yet.")

    # Session config
    lines.append("")
    lines.append(fmt.bold("Session config:"))
    lines.append(f"  Model: {session.model or 'default'}")
    lines.append(f"  Thinking: {session.thinking}")
    lines.append(f"  Effort: {session.effort or 'default'}")
    lines.append(f"  Has context: {'yes' if session.session_id else 'no'}")

    await _reply(update, "\n".join(lines), formatted=True)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /history command: browse past conversations from DB."""
    sm = _get_sm(context)
    session = sm.current
    args = context.args or []

    if not args:
        # Show recent messages for current session
        try:
            async with get_session() as s:
                repo = Repository(s)
                msgs = await repo.get_recent_messages(session.name, limit=10)
        except Exception:
            await _reply(update, "Failed to read history from DB.")
            return

        if not msgs:
            await _reply(update, "No messages recorded for this session yet.")
            return

        lines = [fmt.bold(f"Recent messages ({session.name}):"), ""]
        for m in reversed(msgs):  # oldest first
            ts = m.created_at.strftime("%H:%M") if m.created_at else "?"
            role_icon = "👤" if m.role == "user" else "🤖"
            preview = m.content[:100] + ("..." if len(m.content) > 100 else "")
            lines.append(f"{role_icon} {ts} {fmt.escape(preview)}")
        await _reply(update, "\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub == "all":
        # Show messages across all sessions
        try:
            async with get_session() as s:
                repo = Repository(s)
                from sqlalchemy import select

                from megobari.db.models import Message
                stmt = (
                    select(Message)
                    .order_by(Message.created_at.desc())
                    .limit(15)
                )
                result = await s.execute(stmt)
                msgs = list(result.scalars().all())
        except Exception:
            await _reply(update, "Failed to read history from DB.")
            return

        if not msgs:
            await _reply(update, "No messages recorded yet.")
            return

        lines = [fmt.bold("Recent messages (all sessions):"), ""]
        for m in reversed(msgs):
            ts = m.created_at.strftime("%m-%d %H:%M") if m.created_at else "?"
            role_icon = "👤" if m.role == "user" else "🤖"
            preview = m.content[:80] + ("..." if len(m.content) > 80 else "")
            lines.append(f"{role_icon} {ts} [{m.session_name}] {fmt.escape(preview)}")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "search" and len(args) > 1:
        query_text = " ".join(args[1:])
        try:
            async with get_session() as s:
                repo = Repository(s)
                from sqlalchemy import select

                from megobari.db.models import Message
                stmt = (
                    select(Message)
                    .where(Message.content.ilike(f"%{query_text}%"))
                    .order_by(Message.created_at.desc())
                    .limit(10)
                )
                result = await s.execute(stmt)
                msgs = list(result.scalars().all())
        except Exception:
            await _reply(update, "Failed to search history.")
            return

        if not msgs:
            await _reply(update, f"No messages matching '{query_text}'.")
            return

        lines = [fmt.bold(f"Search results for '{query_text}':"), ""]
        for m in reversed(msgs):
            ts = m.created_at.strftime("%m-%d %H:%M") if m.created_at else "?"
            role_icon = "👤" if m.role == "user" else "🤖"
            preview = m.content[:100] + ("..." if len(m.content) > 100 else "")
            lines.append(f"{role_icon} {ts} [{m.session_name}] {fmt.escape(preview)}")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "stats":
        try:
            async with get_session() as s:
                repo = Repository(s)
                from sqlalchemy import func as sqlfunc
                from sqlalchemy import select

                from megobari.db.models import Message

                # Count by session
                stmt = (
                    select(
                        Message.session_name,
                        sqlfunc.count(Message.id).label("cnt"),
                    )
                    .group_by(Message.session_name)
                    .order_by(sqlfunc.count(Message.id).desc())
                    .limit(10)
                )
                result = await s.execute(stmt)
                rows = result.all()
        except Exception:
            await _reply(update, "Failed to read history stats.")
            return

        if not rows:
            await _reply(update, "No messages recorded yet.")
            return

        lines = [fmt.bold("Message stats by session:"), ""]
        for row in rows:
            marker = " ◂" if row.session_name == session.name else ""
            lines.append(f"  {fmt.escape(row.session_name)}: {row.cnt} messages{marker}")
        await _reply(update, "\n".join(lines), formatted=True)

    else:
        await _reply(
            update,
            "Usage:\n"
            "/history — recent messages for current session\n"
            "/history all — recent across all sessions\n"
            "/history search <query> — search message content\n"
            "/history stats — message counts by session",
        )
