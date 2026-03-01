"""Persona endpoints (read-only for Phase 1)."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from megobari.db import Repository, get_session

router = APIRouter(prefix="/personas", tags=["personas"])


def _serialize_persona(p) -> dict:
    """Convert a Persona ORM object to a JSON-serializable dict."""
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "system_prompt": p.system_prompt,
        "mcp_servers": json.loads(p.mcp_servers) if p.mcp_servers else [],
        "skills": json.loads(p.skills) if p.skills else [],
        "config": json.loads(p.config) if p.config else {},
        "is_default": p.is_default,
        "created_at": p.created_at.isoformat(),
    }


@router.get("")
async def list_personas(request: Request) -> list[dict]:
    """All personas."""
    async with get_session() as s:
        repo = Repository(s)
        personas = await repo.list_personas()
    return [_serialize_persona(p) for p in personas]


@router.get("/{name}")
async def get_persona(name: str, request: Request) -> dict:
    """Single persona detail."""
    async with get_session() as s:
        repo = Repository(s)
        p = await repo.get_persona(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")
    return _serialize_persona(p)
