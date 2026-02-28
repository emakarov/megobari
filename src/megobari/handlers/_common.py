"""Shared state, helpers, and types used by all handler modules."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes

from megobari.claude_bridge import QueryUsage
from megobari.db import Repository, get_session
from megobari.formatting import Formatter, TelegramFormatter
from megobari.session import SessionManager

logger = logging.getLogger(__name__)

# Client-specific formatter — swap this out for other frontends.
fmt: Formatter = TelegramFormatter()

# Track which sessions are currently processing a query (enables parallel work).
_busy_sessions: set[str] = set()


def _get_sm(context: ContextTypes.DEFAULT_TYPE) -> SessionManager:
    return context.bot_data["session_manager"]


def _reply(update: Update, text: str, formatted: bool = False):
    """Helper: reply with or without parse_mode."""
    kwargs = {}
    if formatted:
        kwargs["parse_mode"] = fmt.parse_mode
    return update.message.reply_text(text, **kwargs)


async def _track_user(update: Update) -> None:
    """Upsert the Telegram user in the local database."""
    user = update.effective_user
    if user is None:
        return
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.upsert_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
    except Exception:
        logger.debug("Failed to track user", exc_info=True)


async def _set_reaction(bot, chat_id: int, message_id: int, emoji: str | None) -> None:
    """Set or remove a reaction on a message. Failures are silently ignored."""
    try:
        if emoji is None:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[],
            )
        else:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[emoji],
            )
    except Exception:
        logger.debug("Failed to set reaction %r", emoji, exc_info=True)


def _busy_emoji(session_name: str | None = None) -> str:
    """Return hourglass if session is busy, eyes if idle.

    Args:
        session_name: Session to check. If None, checks if any session is busy.
    """
    if session_name is not None:
        return "\u23f3" if session_name in _busy_sessions else "\U0001f440"
    return "\u23f3" if _busy_sessions else "\U0001f440"


@dataclass
class SessionUsage:
    """Accumulated usage for a session (in-memory, resets on restart)."""

    total_cost_usd: float = 0.0
    total_turns: int = 0
    total_duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    message_count: int = 0


def _accumulate_usage(
    context: ContextTypes.DEFAULT_TYPE,
    session_name: str,
    query_usage: QueryUsage,
    user_id: int | None = None,
) -> None:
    """Accumulate usage stats from a query into bot_data and persist to DB."""
    # In-memory accumulation
    usage_map: dict[str, SessionUsage] = context.bot_data.setdefault("usage", {})
    su = usage_map.setdefault(session_name, SessionUsage())
    su.total_cost_usd += query_usage.cost_usd
    su.total_turns += query_usage.num_turns
    su.total_duration_ms += query_usage.duration_api_ms
    su.input_tokens += query_usage.input_tokens
    su.output_tokens += query_usage.output_tokens
    su.message_count += 1

    # Persist to DB (fire-and-forget)
    asyncio.create_task(
        _persist_usage(session_name, query_usage, user_id)
    )


async def _persist_usage(
    session_name: str, query_usage: QueryUsage, user_id: int | None
) -> None:
    """Save a usage record to the database."""
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_usage(
                session_name=session_name,
                cost_usd=query_usage.cost_usd,
                num_turns=query_usage.num_turns,
                duration_ms=query_usage.duration_api_ms,
                input_tokens=query_usage.input_tokens,
                output_tokens=query_usage.output_tokens,
                user_id=user_id,
            )
    except Exception:
        logger.warning("Failed to persist usage record", exc_info=True)
