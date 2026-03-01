"""Memories endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request

from megobari.db import Repository, get_session

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("")
async def list_memories(
    request: Request,
    category: str | None = Query(None, description="Filter by category"),
) -> list[dict]:
    """All memories, optionally filtered by category."""
    async with get_session() as s:
        repo = Repository(s)
        memories = await repo.list_memories(category=category)
    return [
        {
            "id": m.id,
            "category": m.category,
            "key": m.key,
            "content": m.content,
            "metadata": json.loads(m.metadata_json) if m.metadata_json else {},
            "created_at": m.created_at.isoformat(),
            "updated_at": m.updated_at.isoformat(),
        }
        for m in memories
    ]
