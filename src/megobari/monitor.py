"""Website monitor engine — fetch, diff, summarize, notify."""

from __future__ import annotations

import hashlib
import json
import logging

import httpx
from sqlalchemy import select

from megobari.db import Repository, get_session
from megobari.db.models import MonitorResource, MonitorSnapshot
from megobari.session import Session

logger = logging.getLogger(__name__)

# Change-type icons for digest messages
_CHANGE_ICONS: dict[str, str] = {
    "new_post": "\U0001f4dd",
    "price_change": "\U0001f4b0",
    "new_release": "\U0001f504",
    "new_job": "\U0001f465",
    "new_deal": "\U0001f91d",
    "content_update": "\U0001f4c4",
    "new_feature": "\u2728",
}


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hex digest of a content string."""
    return hashlib.sha256(content.encode()).hexdigest()


async def fetch_url_markdown(url: str) -> str:
    """Fetch a URL and return its content as clean markdown via Crawl4AI."""
    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown or ""


async def check_resource(resource_id: int) -> dict | None:
    """Check a single resource for changes.

    Fetches content, computes hash, compares to latest snapshot, and saves
    a new snapshot. Returns a result dict or None if resource not found or
    fetch fails.
    """
    async with get_session() as s:
        repo = Repository(s)

        # Load resource by ID
        stmt = select(MonitorResource).where(MonitorResource.id == resource_id)
        result = await s.execute(stmt)
        resource = result.scalar_one_or_none()
        if resource is None:
            logger.warning("Resource %d not found", resource_id)
            return None

        # Fetch content
        try:
            markdown = await fetch_url_markdown(resource.url)
        except Exception:
            logger.exception("Failed to fetch resource %d (%s)", resource_id, resource.url)
            return None

        content_hash = compute_content_hash(markdown)

        # Compare to latest snapshot
        latest = await repo.get_latest_monitor_snapshot(resource_id)
        is_baseline = latest is None
        has_changes = not is_baseline and latest.content_hash != content_hash

        # Save new snapshot
        snap = await repo.add_monitor_snapshot(
            topic_id=resource.topic_id,
            entity_id=resource.entity_id,
            resource_id=resource_id,
            content_hash=content_hash,
            content_markdown=markdown,
            has_changes=has_changes,
        )

        # Update resource timestamps
        await repo.update_monitor_resource_checked(
            resource_id=resource_id,
            changed=has_changes,
        )

        return {
            "resource_id": resource_id,
            "has_changes": has_changes,
            "is_baseline": is_baseline,
            "content_hash": content_hash,
            "snapshot_id": snap.id,
            "topic_id": resource.topic_id,
            "entity_id": resource.entity_id,
        }


async def summarize_changes(
    resource_id: int,
    snapshot_id: int,
    previous_markdown: str,
    new_markdown: str,
    resource_name: str,
    resource_type: str,
) -> dict | None:
    """Use Claude to summarize changes between two snapshots.

    Returns dict with 'summary' and 'change_type', or None on failure.
    """
    from megobari.claude_bridge import send_to_claude

    prompt = (
        f"Compare the OLD and NEW versions of the page '{resource_name}' "
        f"(type: {resource_type}). Summarize what changed in 1-2 sentences.\n\n"
        f"Classify the change_type as ONE of: new_post, price_change, "
        f"new_release, new_job, new_deal, content_update, new_feature.\n\n"
        f"Respond with ONLY valid JSON, no markdown fences:\n"
        f'{{"summary": "...", "change_type": "..."}}\n\n'
        f"--- OLD ---\n{previous_markdown[:3000]}\n\n"
        f"--- NEW ---\n{new_markdown[:3000]}"
    )

    session = Session(name="monitor:summarize", cwd="/tmp")
    session.permission_mode = "bypassPermissions"
    session.max_turns = 1

    try:
        response, _, _, _ = await send_to_claude(prompt, session)
        # Strip markdown fences if present
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        data = json.loads(text)
        return {
            "summary": data.get("summary", ""),
            "change_type": data.get("change_type", "content_update"),
        }
    except Exception:
        logger.exception(
            "Failed to summarize changes for resource %d snapshot %d",
            resource_id, snapshot_id,
        )
        return None


async def run_monitor_check(
    topic_name: str | None = None,
    entity_name: str | None = None,
) -> list[dict]:
    """Run monitor checks on enabled resources.

    Optionally filter by topic or entity name. Returns list of digest dicts
    for resources that had changes and were successfully summarized.
    """
    digests: list[dict] = []

    # Resolve filters
    topic_id: int | None = None
    entity_id: int | None = None

    async with get_session() as s:
        repo = Repository(s)

        if topic_name:
            topic = await repo.get_monitor_topic(topic_name)
            if topic is None:
                logger.warning("Topic '%s' not found", topic_name)
                return []
            topic_id = topic.id

        if entity_name:
            entity = await repo.get_monitor_entity(entity_name)
            if entity is None:
                logger.warning("Entity '%s' not found", entity_name)
                return []
            entity_id = entity.id

        resources = await repo.list_monitor_resources(
            topic_id=topic_id,
            enabled_only=True,
        )
        # Additional entity filter if specified
        if entity_id is not None:
            resources = [r for r in resources if r.entity_id == entity_id]

    # Check each resource
    for resource in resources:
        result = await check_resource(resource.id)
        if result is None:
            continue
        if result["is_baseline"] or not result["has_changes"]:
            continue

        # Load previous and new snapshots for summarization
        async with get_session() as s:
            # Get the two most recent snapshots
            stmt = (
                select(MonitorSnapshot)
                .where(MonitorSnapshot.resource_id == resource.id)
                .order_by(MonitorSnapshot.fetched_at.desc())
                .limit(2)
            )
            rows = await s.execute(stmt)
            snaps = list(rows.scalars().all())

            if len(snaps) < 2:
                continue

            new_snap = snaps[0]
            prev_snap = snaps[1]

        # Summarize
        summary_result = await summarize_changes(
            resource_id=resource.id,
            snapshot_id=result["snapshot_id"],
            previous_markdown=prev_snap.content_markdown,
            new_markdown=new_snap.content_markdown,
            resource_name=resource.name,
            resource_type=resource.resource_type,
        )
        if summary_result is None:
            continue

        # Save digest
        async with get_session() as s:
            repo = Repository(s)
            digest = await repo.add_monitor_digest(
                topic_id=result["topic_id"],
                entity_id=result["entity_id"],
                resource_id=resource.id,
                snapshot_id=result["snapshot_id"],
                summary=summary_result["summary"],
                change_type=summary_result["change_type"],
            )
            digests.append({
                "digest_id": digest.id,
                "resource_id": resource.id,
                "resource_name": resource.name,
                "topic_id": result["topic_id"],
                "entity_id": result["entity_id"],
                "snapshot_id": result["snapshot_id"],
                "summary": summary_result["summary"],
                "change_type": summary_result["change_type"],
            })

    return digests


def _format_digest_message(digests: list[dict], run_label: str = "Check") -> str:
    """Format a list of digest dicts into a readable notification message."""
    if not digests:
        return f"\U0001f50d {run_label}: No changes detected."

    lines = [f"\U0001f50d {run_label}: {len(digests)} change(s) found\n"]
    for d in digests:
        icon = _CHANGE_ICONS.get(d.get("change_type", ""), "\U0001f4c4")
        name = d.get("resource_name", "Unknown")
        summary = d.get("summary", "")
        lines.append(f"{icon} <b>{name}</b>: {summary}")

    return "\n".join(lines)


async def _send_slack_webhook(webhook_url: str, message: str) -> None:
    """POST a message to a Slack incoming webhook."""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook_url, json={"text": message})


async def notify_subscribers(
    digests: list[dict],
    run_label: str = "Check",
) -> None:
    """Notify subscribers about digest results.

    Groups digests by topic_id and finds matching subscribers.
    Slack subscribers get a webhook POST; Telegram subscribers are logged
    (caller handles actual send via bot instance).
    """
    if not digests:
        return

    # Group by topic_id
    by_topic: dict[int, list[dict]] = {}
    for d in digests:
        tid = d.get("topic_id")
        if tid is not None:
            by_topic.setdefault(tid, []).append(d)

    for topic_id, topic_digests in by_topic.items():
        async with get_session() as s:
            repo = Repository(s)
            subscribers = await repo.list_monitor_subscribers(topic_id=topic_id)

        message = _format_digest_message(topic_digests, run_label)

        for sub in subscribers:
            if sub.channel_type == "slack":
                try:
                    config = json.loads(sub.channel_config)
                    webhook_url = config.get("webhook_url", "")
                    if webhook_url:
                        await _send_slack_webhook(webhook_url, message)
                        logger.info("Sent Slack notification to subscriber %d", sub.id)
                except Exception:
                    logger.exception(
                        "Failed to send Slack notification to subscriber %d", sub.id
                    )
            elif sub.channel_type == "telegram":
                logger.info(
                    "Telegram notification for subscriber %d (topic %d): %d digest(s)",
                    sub.id, topic_id, len(topic_digests),
                )
