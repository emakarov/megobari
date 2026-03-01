"""Conversation summaries endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request

from megobari.db import Repository, get_session

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("")
async def get_summaries(
    request: Request,
    session: str | None = Query(None, description="Filter by session name"),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """Conversation summaries, optionally filtered by session."""
    async with get_session() as s:
        repo = Repository(s)
        summaries = await repo.get_summaries(
            session_name=session, limit=limit
        )
    return [
        {
            "id": sm.id,
            "session_name": sm.session_name,
            "summary": sm.summary,
            "short_summary": sm.short_summary,
            "topics": json.loads(sm.topics) if sm.topics else [],
            "message_count": sm.message_count,
            "is_milestone": sm.is_milestone,
            "created_at": sm.created_at.isoformat(),
        }
        for sm in summaries
    ]
