"""Cron jobs and heartbeat checks endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from megobari.db import Repository, get_session

router = APIRouter(tags=["scheduling"])


@router.get("/cron-jobs")
async def list_cron_jobs(request: Request) -> list[dict]:
    """All cron jobs."""
    async with get_session() as s:
        repo = Repository(s)
        jobs = await repo.list_cron_jobs()
    return [
        {
            "id": j.id,
            "name": j.name,
            "cron_expression": j.cron_expression,
            "prompt": j.prompt,
            "session_name": j.session_name,
            "isolated": j.isolated,
            "enabled": j.enabled,
            "timezone": j.timezone,
            "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]


@router.get("/heartbeat-checks")
async def list_heartbeat_checks(request: Request) -> list[dict]:
    """All heartbeat checks."""
    async with get_session() as s:
        repo = Repository(s)
        checks = await repo.list_heartbeat_checks()
    return [
        {
            "id": c.id,
            "name": c.name,
            "prompt": c.prompt,
            "enabled": c.enabled,
            "created_at": c.created_at.isoformat(),
        }
        for c in checks
    ]
