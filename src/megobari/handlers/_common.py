"""Shared state, helpers, and types used by all handler modules."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from megobari.claude_bridge import QueryUsage
from megobari.db import Repository, get_session
from megobari.transport import TransportContext

logger = logging.getLogger(__name__)

# Track which sessions are currently processing a query (enables parallel work).
_busy_sessions: set[str] = set()


async def _track_user(ctx: TransportContext) -> None:
    """Upsert the user in the local database."""
    uid = ctx.user_id
    if not uid:
        return
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.upsert_user(
                telegram_id=uid,
                username=ctx.username,
                first_name=ctx.first_name,
                last_name=ctx.last_name,
            )
    except Exception:
        logger.debug("Failed to track user", exc_info=True)


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
    ctx: TransportContext,
    session_name: str,
    query_usage: QueryUsage,
    user_id: int | None = None,
) -> None:
    """Accumulate usage stats from a query into bot_data and persist to DB."""
    # In-memory accumulation
    usage_map: dict[str, SessionUsage] = ctx.bot_data.setdefault("usage", {})
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
