"""Usage statistics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from megobari.db import Repository, get_session

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def get_total_usage(request: Request) -> dict:
    """Aggregated usage across all sessions."""
    async with get_session() as s:
        repo = Repository(s)
        return await repo.get_total_usage()


@router.get("/records")
async def get_usage_records(
    request: Request,
    session: str | None = Query(None, description="Filter by session name"),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    """Raw usage records, newest first."""
    async with get_session() as s:
        repo = Repository(s)
        records = await repo.get_usage_records(
            session_name=session, limit=limit
        )
    return [
        {
            "id": r.id,
            "session_name": r.session_name,
            "cost_usd": r.cost_usd,
            "num_turns": r.num_turns,
            "duration_ms": r.duration_ms,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


@router.get("/{session_name}")
async def get_session_usage(session_name: str, request: Request) -> dict:
    """Aggregated usage for a single session."""
    async with get_session() as s:
        repo = Repository(s)
        return await repo.get_session_usage(session_name)
