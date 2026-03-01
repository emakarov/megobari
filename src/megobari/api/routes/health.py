"""Health and status endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from megobari.db import get_session
from megobari.db.models import ConversationSummary, Memory, Message, User
from megobari.handlers._common import _busy_sessions

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(request: Request) -> dict:
    """Bot health: scheduler status, busy sessions, DB row counts."""
    sm = request.app.state.session_manager
    bot_data = request.app.state.bot_data
    scheduler = bot_data.get("scheduler")

    db_stats: dict = {}
    try:
        async with get_session() as s:
            for model, key in [
                (User, "users"),
                (Memory, "memories"),
                (Message, "messages"),
                (ConversationSummary, "summaries"),
            ]:
                result = await s.execute(
                    select(func.count()).select_from(model)
                )
                db_stats[key] = result.scalar()
    except Exception as e:
        db_stats = {"error": str(e)}

    return {
        "bot_running": True,
        "scheduler_running": bool(scheduler and getattr(scheduler, "running", False)),
        "active_session": sm.active_name,
        "busy_sessions": list(_busy_sessions),
        "total_sessions": len(sm.list_all()),
        "sessions_with_context": sum(
            1 for s in sm.list_all() if s.session_id
        ),
        "db_stats": db_stats,
    }
