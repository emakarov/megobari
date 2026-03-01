"""Message history endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from megobari.db import Repository, get_session

router = APIRouter(prefix="/messages", tags=["messages"])


def _utc_iso(dt: datetime) -> str:
    """Ensure datetime is serialized as UTC with Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialize_message(m) -> dict:
    return {
        "id": m.id,
        "session_name": m.session_name,
        "role": m.role,
        "content": m.content,
        "summarized": m.summarized,
        "created_at": _utc_iso(m.created_at),
    }


@router.get("/recent")
async def get_recent_messages_all(
    request: Request,
    limit: int = Query(30, ge=1, le=200),
) -> list[dict]:
    """Most recent messages across all sessions, newest first."""
    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_recent_messages_all(limit=limit)
    return [_serialize_message(m) for m in msgs]


@router.get("/{session_name}")
async def get_messages(
    session_name: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    """Messages for a session, newest first (reversed for display)."""
    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_recent_messages(session_name, limit=limit)
    return [_serialize_message(m) for m in reversed(msgs)]
