"""Sessions endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from megobari.db import Repository, get_session
from megobari.handlers._common import SessionUsage, _busy_sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(request: Request) -> list[dict]:
    """All sessions with live status."""
    sm = request.app.state.session_manager
    active_name = sm.active_name
    usage_map: dict[str, SessionUsage] = request.app.state.bot_data.get(
        "usage", {}
    )

    result = []
    for s in sm.list_all():
        su = usage_map.get(s.name)
        result.append({
            "name": s.name,
            "is_active": s.name == active_name,
            "is_busy": s.name in _busy_sessions,
            "has_context": bool(s.session_id),
            "streaming": s.streaming,
            "permission_mode": s.permission_mode,
            "model": s.model,
            "thinking": s.thinking,
            "effort": s.effort,
            "cwd": s.cwd,
            "created_at": s.created_at,
            "last_used_at": s.last_used_at,
            "current_run_cost": su.total_cost_usd if su else 0,
            "current_run_messages": su.message_count if su else 0,
        })
    return result


@router.get("/{name}")
async def get_session_detail(name: str, request: Request) -> dict:
    """Single session detail with DB usage stats."""
    sm = request.app.state.session_manager
    session = sm.get(name)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{name}' not found")

    usage_map: dict[str, SessionUsage] = request.app.state.bot_data.get(
        "usage", {}
    )
    su = usage_map.get(name)

    async with get_session() as s:
        repo = Repository(s)
        db_usage = await repo.get_session_usage(name)
        recent_msgs = await repo.get_recent_messages(name, limit=10)

    return {
        "name": session.name,
        "session_id": session.session_id,
        "is_active": session.name == sm.active_name,
        "is_busy": session.name in _busy_sessions,
        "streaming": session.streaming,
        "permission_mode": session.permission_mode,
        "model": session.model,
        "thinking": session.thinking,
        "thinking_budget": session.thinking_budget,
        "effort": session.effort,
        "max_turns": session.max_turns,
        "cwd": session.cwd,
        "dirs": session.dirs,
        "created_at": session.created_at,
        "last_used_at": session.last_used_at,
        "current_run": {
            "cost_usd": su.total_cost_usd if su else 0,
            "messages": su.message_count if su else 0,
            "input_tokens": su.input_tokens if su else 0,
            "output_tokens": su.output_tokens if su else 0,
        },
        "all_time": db_usage,
        "recent_messages": [
            {
                "role": m.role,
                "content": m.content[:300],
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(recent_msgs)
        ],
    }
