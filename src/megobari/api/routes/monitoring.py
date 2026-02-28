"""Website monitoring API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from megobari.db import Repository, get_session

router = APIRouter(tags=["monitoring"])


@router.get("/monitor/topics")
async def list_topics(request: Request) -> list[dict]:
    """List all monitor topics with entity counts."""
    async with get_session() as s:
        repo = Repository(s)
        topics = await repo.list_monitor_topics()
        # Count entities per topic
        result = []
        for t in topics:
            entities = await repo.list_monitor_entities(topic_id=t.id)
            result.append({
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "enabled": t.enabled,
                "entity_count": len(entities),
                "created_at": t.created_at.isoformat(),
            })
    return result


@router.get("/monitor/entities")
async def list_entities(
    request: Request,
    topic_id: int | None = Query(None),
) -> list[dict]:
    """List monitor entities with resource counts."""
    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities(topic_id=topic_id)
        result = []
        for e in entities:
            resources = await repo.list_monitor_resources(entity_id=e.id)
            result.append({
                "id": e.id,
                "topic_id": e.topic_id,
                "name": e.name,
                "url": e.url,
                "entity_type": e.entity_type,
                "description": e.description,
                "enabled": e.enabled,
                "resource_count": len(resources),
                "created_at": e.created_at.isoformat(),
            })
    return result


@router.get("/monitor/resources")
async def list_resources(
    request: Request,
    entity_id: int | None = Query(None),
    topic_id: int | None = Query(None),
) -> list[dict]:
    """List all monitor resources."""
    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(
            entity_id=entity_id,
            topic_id=topic_id,
        )
    return [
        {
            "id": r.id,
            "topic_id": r.topic_id,
            "entity_id": r.entity_id,
            "name": r.name,
            "url": r.url,
            "resource_type": r.resource_type,
            "enabled": r.enabled,
            "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
            "last_changed_at": r.last_changed_at.isoformat() if r.last_changed_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in resources
    ]


@router.get("/monitor/digests")
async def list_digests(
    request: Request,
    topic_id: int | None = Query(None),
    entity_id: int | None = Query(None),
    limit: int = Query(50),
) -> list[dict]:
    """List latest monitor digests."""
    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests(
            topic_id=topic_id,
            entity_id=entity_id,
            limit=limit,
        )
    return [
        {
            "id": d.id,
            "topic_id": d.topic_id,
            "entity_id": d.entity_id,
            "resource_id": d.resource_id,
            "snapshot_id": d.snapshot_id,
            "summary": d.summary,
            "change_type": d.change_type,
            "created_at": d.created_at.isoformat(),
        }
        for d in digests
    ]
