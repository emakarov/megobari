"""Website monitor engine — fetch, diff, summarize, notify."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import httpx
from sqlalchemy import select

from megobari.db import Repository, get_session
from megobari.db.models import MonitorDigest, MonitorEntity, MonitorResource, MonitorSnapshot
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
    "baseline": "\U0001f4cb",
}


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hex digest of a content string."""
    return hashlib.sha256(content.encode()).hexdigest()


async def fetch_url_markdown(url: str, deep_blog: bool = False) -> str:
    """Fetch a URL and return its content as clean markdown via Crawl4AI.

    If *deep_blog* is True, crawl the page, extract article links, then
    crawl the top-N posts and combine their content.
    """
    import re
    from urllib.parse import urlparse

    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

    config = CrawlerRunConfig(
        remove_overlay_elements=True,
        excluded_selector=(
            "[class*=cookie],[id*=cookie],"
            "[class*=consent],[id*=consent],"
            "[class*=banner],[id*=banner]"
        ),
        wait_until="domcontentloaded",
        delay_before_return_html=2.0,
        scan_full_page=True,
        page_timeout=30000,
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        index_md = result.markdown or ""

        if not deep_blog:
            return index_md

        # Extract article links from the blog index markdown.
        # We look for markdown links with long titles (actual articles)
        # from the same domain, filtering out nav/footer/language links.
        parsed = urlparse(url)
        base_domain = parsed.netloc.lstrip("www.")
        article_urls: list[str] = []
        seen: set[str] = set()

        _SKIP_PATH_RE = re.compile(
            r"/(tag|category|page|author|feed|wp-|legal|contact|faq|"
            r"about|pricing|solution|clients|testimonial|video|"
            r"industries|case-stud|fr/|de/|es/|it/|pt/)",
            re.IGNORECASE,
        )

        for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", index_md):
            title = match.group(1).strip()
            href = match.group(2).rstrip("/")
            if href in seen:
                continue
            link_parsed = urlparse(href)
            if link_parsed.netloc.lstrip("www.") != base_domain:
                continue
            if href.rstrip("/") == url.rstrip("/"):
                continue
            if _SKIP_PATH_RE.search(link_parsed.path):
                continue
            # Article titles are typically >20 chars; nav links are short
            if len(title) < 20:
                continue
            # Article slugs contain hyphens (e.g., /blog/my-article-title/)
            slug = link_parsed.path.rstrip("/").rsplit("/", 1)[-1]
            if "-" not in slug:
                continue
            seen.add(href)
            article_urls.append(href)

        if not article_urls:
            logger.info("No article links found on %s", url)
            return index_md

        # Crawl top N articles (most recent are usually listed first)
        max_articles = 10
        articles_to_crawl = article_urls[:max_articles]
        logger.info(
            "Deep-crawling %d/%d articles from %s",
            len(articles_to_crawl), len(article_urls), url,
        )

        parts = [f"# Blog Index: {url}\n\n{index_md}\n\n---\n"]
        for article_url in articles_to_crawl:
            try:
                art_result = await crawler.arun(url=article_url, config=config)
                art_md = (art_result.markdown or "").strip()
                if art_md:
                    parts.append(
                        f"\n# Article: {article_url}\n\n{art_md}\n\n---\n"
                    )
                    logger.info("Crawled article: %s (%d chars)", article_url, len(art_md))
            except Exception:
                logger.warning("Failed to crawl article: %s", article_url, exc_info=True)

        return "\n".join(parts)


async def fetch_github_repo(url: str) -> str:
    """Fetch GitHub repo info via API: description, stars, latest releases, recent commits.

    Accepts URLs like https://github.com/owner/repo and returns a markdown summary.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]

    headers = {"Accept": "application/vnd.github.v3+json"}
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        # Repo info
        resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        if resp.status_code != 200:
            logger.warning("GitHub API %d for %s/%s", resp.status_code, owner, repo)
            return f"# {owner}/{repo}\n\nFailed to fetch (HTTP {resp.status_code})."
        info = resp.json()

        lines = [
            f"# {info.get('full_name', f'{owner}/{repo}')}",
            "",
            f"**Description:** {info.get('description', 'N/A')}",
            f"**Stars:** {info.get('stargazers_count', 0):,}",
            f"**Forks:** {info.get('forks_count', 0):,}",
            f"**Language:** {info.get('language', 'N/A')}",
            f"**License:** {(info.get('license') or {}).get('spdx_id', 'N/A')}",
            f"**Last pushed:** {info.get('pushed_at', 'N/A')}",
            f"**Open issues:** {info.get('open_issues_count', 0):,}",
            "",
        ]

        # Latest releases (up to 5)
        resp_rel = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases",
            params={"per_page": 5},
        )
        if resp_rel.status_code == 200:
            releases = resp_rel.json()
            if releases:
                lines.append("## Recent Releases")
                for r in releases:
                    tag = r.get("tag_name", "")
                    name = r.get("name", tag)
                    date = (r.get("published_at") or "")[:10]
                    body = (r.get("body") or "")[:500]
                    lines.append(f"\n### {name} ({date})")
                    if body:
                        lines.append(body)
            else:
                lines.append("## Releases\nNo releases found (may use tags only).")

        # Recent commits (last 10)
        resp_commits = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            params={"per_page": 10},
        )
        if resp_commits.status_code == 200:
            commits = resp_commits.json()
            if commits:
                lines.append("\n## Recent Commits")
                for c in commits:
                    sha = c.get("sha", "")[:7]
                    msg = (c.get("commit", {}).get("message") or "").split("\n")[0]
                    date = (c.get("commit", {}).get("author", {}).get("date") or "")[:10]
                    lines.append(f"- `{sha}` ({date}) {msg}")

    return "\n".join(lines)


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

        # Fetch content based on resource type
        try:
            if resource.resource_type == "repo" and "github.com" in resource.url:
                markdown = await fetch_github_repo(resource.url)
            else:
                is_blog = resource.resource_type == "blog"
                markdown = await fetch_url_markdown(resource.url, deep_blog=is_blog)
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


async def summarize_baseline(
    resource_id: int,
    snapshot_id: int,
    content_markdown: str,
    resource_name: str,
    resource_type: str,
    entity_name: str,
) -> dict | None:
    """Use Claude to summarize a baseline snapshot (initial state, no diff).

    Returns dict with 'summary' and 'change_type', or None on failure.
    """
    from megobari.claude_bridge import send_to_claude

    if not content_markdown.strip():
        return {"summary": "Page returned empty content.", "change_type": "baseline"}

    prompt = (
        f"You are analyzing a scraped {resource_type} page for '{entity_name}'.\n\n"
        f"Extract the most important SPECIFIC facts from this content:\n"
        f"- Recent blog post titles with dates\n"
        f"- Product announcements and feature launches\n"
        f"- Pricing details (exact numbers, tiers, free plans)\n"
        f"- Job openings or hiring signals\n"
        f"- Partnerships, funding, acquisitions\n\n"
        f"Write 2-4 sentences with concrete details — names, dates, numbers. "
        f"Do NOT describe what the page is (e.g. 'serves as a marketing hub'). "
        f"Only state actual facts found in the content.\n\n"
        f"Respond with ONLY valid JSON, no markdown fences:\n"
        f'{{"summary": "..."}}\n\n'
        f"--- CONTENT ---\n{content_markdown[:8000]}"
    )

    session = Session(name="monitor:baseline", cwd="/tmp")
    session.permission_mode = "bypassPermissions"
    session.max_turns = 1

    try:
        response, _, _, _ = await send_to_claude(prompt, session)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        data = json.loads(text)
        return {
            "summary": data.get("summary", ""),
            "change_type": "baseline",
        }
    except Exception:
        logger.exception(
            "Failed to summarize baseline for resource %d snapshot %d",
            resource_id, snapshot_id,
        )
        return None


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


async def generate_baseline_digests(
    topic_name: str | None = None,
) -> list[dict]:
    """Generate initial-state digests for baseline snapshots that have no digest yet.

    Uses Claude to summarize what each page currently contains.
    Returns list of digest dicts.
    """
    digests: list[dict] = []

    async with get_session() as s:
        repo = Repository(s)

        # Resolve topic filter
        topic_id: int | None = None
        if topic_name:
            topic = await repo.get_monitor_topic(topic_name)
            if topic is None:
                logger.warning("Topic '%s' not found", topic_name)
                return []
            topic_id = topic.id

        resources = await repo.list_monitor_resources(
            topic_id=topic_id,
            enabled_only=True,
        )

    for resource in resources:
        async with get_session() as s:
            repo = Repository(s)

            # Get the latest snapshot for this resource
            latest = await repo.get_latest_monitor_snapshot(resource.id)
            if latest is None:
                continue

            # Check if a digest already exists for this snapshot
            stmt = (
                select(MonitorDigest)
                .where(MonitorDigest.snapshot_id == latest.id)
                .limit(1)
            )
            result = await s.execute(stmt)
            if result.scalar_one_or_none() is not None:
                continue  # digest already exists

            # Get entity name for context
            stmt_ent = select(MonitorEntity).where(MonitorEntity.id == resource.entity_id)
            result_ent = await s.execute(stmt_ent)
            entity = result_ent.scalar_one_or_none()
            entity_name = entity.name if entity else "Unknown"

        # Summarize baseline content
        summary_result = await summarize_baseline(
            resource_id=resource.id,
            snapshot_id=latest.id,
            content_markdown=latest.content_markdown,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            entity_name=entity_name,
        )
        if summary_result is None:
            continue

        # Save digest
        async with get_session() as s:
            repo = Repository(s)
            digest = await repo.add_monitor_digest(
                topic_id=resource.topic_id,
                entity_id=resource.entity_id,
                resource_id=resource.id,
                snapshot_id=latest.id,
                summary=summary_result["summary"],
                change_type=summary_result["change_type"],
            )
            digests.append({
                "digest_id": digest.id,
                "resource_id": resource.id,
                "resource_name": resource.name,
                "topic_id": resource.topic_id,
                "entity_id": resource.entity_id,
                "snapshot_id": latest.id,
                "summary": summary_result["summary"],
                "change_type": "baseline",
                "entity_name": entity_name,
            })

        logger.info(
            "Baseline digest for %s / %s: %s",
            entity_name, resource.name, summary_result["summary"][:80],
        )

    return digests


async def _compute_momentum(
    entity_id: int,
    resources: list,
    digest_by_resource: dict[int, str],
) -> dict:
    """Compute momentum/activity metrics for an entity.

    Analyzes GitHub repos (commits, releases, stars) and blog freshness
    to produce a simple activity score.
    """
    import re

    metrics: dict = {"github_stars": 0, "recent_commits": 0, "releases": []}
    blog_dates: list[str] = []

    for resource in resources:
        if resource.entity_id != entity_id:
            continue

        async with get_session() as s:
            repo = Repository(s)
            snap = await repo.get_latest_monitor_snapshot(resource.id)
        if not snap or not snap.content_markdown.strip():
            continue

        content = snap.content_markdown

        if resource.resource_type == "repo":
            # Extract stars
            m = re.search(r"\*\*Stars:\*\*\s*([\d,]+)", content)
            if m:
                metrics["github_stars"] += int(m.group(1).replace(",", ""))
            # Count recent commits
            commits = content.count("- `")
            metrics["recent_commits"] += commits
            # Extract release names + dates
            for rm in re.finditer(r"###\s+(.+?)\s+\((\d{4}-\d{2}-\d{2})\)", content):
                metrics["releases"].append(
                    {"name": rm.group(1), "date": rm.group(2)}
                )

        elif resource.resource_type == "blog":
            # Extract dates from digest or content
            digest = digest_by_resource.get(resource.id, "")
            for dm in re.finditer(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b", digest):
                blog_dates.append(dm.group(1))
            for dm in re.finditer(
                r"\b(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+\d{1,2},?\s+20\d{2}\b",
                digest,
            ):
                blog_dates.append(dm.group(0))

    # Compute a simple score (0-100)
    score = 0
    if metrics["github_stars"] > 1000:
        score += 20
    elif metrics["github_stars"] > 100:
        score += 10
    if metrics["recent_commits"] >= 10:
        score += 25
    elif metrics["recent_commits"] >= 5:
        score += 15
    if len(metrics["releases"]) >= 3:
        score += 25
    elif len(metrics["releases"]) >= 1:
        score += 15
    if blog_dates:
        score += 20
    # Extra points for very recent releases (2026)
    for rel in metrics["releases"]:
        if rel["date"].startswith("2026"):
            score += 10
            break

    metrics["blog_dates"] = blog_dates[:5]
    metrics["score"] = min(score, 100)
    return metrics


async def generate_report(topic_name: str | None = None) -> str:
    """Generate a market intelligence report using Claude.

    Gathers all snapshot content, sends to Claude for a proper analytical
    report with highlights, recent news, pricing, and competitive insights.
    Includes momentum scoring and change tracking vs previous report.
    """
    from megobari.claude_bridge import send_to_claude

    async with get_session() as s:
        repo = Repository(s)

        # Resolve topic
        topic_id: int | None = None
        topic_display: str = "All Topics"
        if topic_name:
            topic = await repo.get_monitor_topic(topic_name)
            if topic is None:
                return f"Topic '{topic_name}' not found."
            topic_id = topic.id
            topic_display = topic.name
        else:
            topics = await repo.list_monitor_topics()
            if topics:
                topic_display = ", ".join(t.name for t in topics)

        # Get entities, resources, and latest snapshots
        entities = await repo.list_monitor_entities(topic_id=topic_id)
        entity_map = {e.id: e for e in entities}

        resources = await repo.list_monitor_resources(topic_id=topic_id)

    if not resources:
        return "No resources to report on."

    # Build per-entity data blocks from snapshots + digests
    entity_blocks: dict[int, list[str]] = {}

    # Pre-load digests for richer blog context
    async with get_session() as s:
        repo = Repository(s)
        all_digests = await repo.list_monitor_digests(topic_id=topic_id, limit=500)
    digest_by_resource: dict[int, str] = {}
    for d in all_digests:
        if d.resource_id not in digest_by_resource:
            digest_by_resource[d.resource_id] = d.summary

    for resource in resources:
        async with get_session() as s:
            repo = Repository(s)
            snap = await repo.get_latest_monitor_snapshot(resource.id)

        if snap is None or not snap.content_markdown.strip():
            continue

        eid = resource.entity_id
        entity_blocks.setdefault(eid, [])

        # For blog resources, include the AI digest summary (which analyzed
        # the full content) plus raw content. For other types, just raw.
        digest_text = digest_by_resource.get(resource.id, "")
        if resource.resource_type == "blog" and digest_text:
            entity_blocks[eid].append(
                f"### {resource.name} ({resource.resource_type}) — {resource.url}\n"
                f"**AI Summary:** {digest_text}\n\n"
                f"**Raw excerpt:**\n{snap.content_markdown[:2000]}\n"
            )
        else:
            entity_blocks[eid].append(
                f"### {resource.name} ({resource.resource_type}) — {resource.url}\n"
                f"{snap.content_markdown[:2000]}\n"
            )

    # Assemble the data payload for Claude.
    # Budget: keep total data under ~80K chars. If it exceeds that, reduce the
    # per-resource raw excerpt length equally so ALL entities are included.
    max_data = 80000
    sorted_eids = sorted(
        entity_blocks,
        key=lambda x: entity_map.get(x, None) and entity_map[x].name or "",
    )

    def _build_sections() -> str:
        sections = []
        for eid in sorted_eids:
            entity = entity_map.get(eid)
            if not entity:
                continue
            header = f"## {entity.name}"
            if entity.url:
                header += f" ({entity.url})"
            body = "\n".join(entity_blocks[eid])
            sections.append(f"{header}\n{body}")
        return "\n---\n".join(sections)

    all_data = _build_sections()

    # If too large, progressively shrink raw excerpts until it fits
    if len(all_data) > max_data:
        for excerpt_limit in (1200, 800, 500, 300):
            # Rebuild blocks with smaller excerpts
            for resource in resources:
                eid = resource.entity_id
                if eid not in entity_blocks:
                    continue
                async with get_session() as s:
                    repo = Repository(s)
                    snap = await repo.get_latest_monitor_snapshot(resource.id)
                if snap is None or not snap.content_markdown.strip():
                    continue

                # Find and replace this resource's block
                digest_text = digest_by_resource.get(resource.id, "")
                if resource.resource_type == "blog" and digest_text:
                    new_block = (
                        f"### {resource.name} ({resource.resource_type}) — {resource.url}\n"
                        f"**AI Summary:** {digest_text}\n\n"
                        f"**Raw excerpt:**\n{snap.content_markdown[:excerpt_limit]}\n"
                    )
                else:
                    new_block = (
                        f"### {resource.name} ({resource.resource_type}) — {resource.url}\n"
                        f"{snap.content_markdown[:excerpt_limit]}\n"
                    )
                # Replace the matching block by resource name
                for i, blk in enumerate(entity_blocks[eid]):
                    if f"### {resource.name} " in blk:
                        entity_blocks[eid][i] = new_block
                        break

            all_data = _build_sections()
            if len(all_data) <= max_data:
                break

    # Compute momentum scores for each entity
    momentum_lines = []
    for eid in sorted_eids:
        entity = entity_map.get(eid)
        if not entity:
            continue
        metrics = await _compute_momentum(eid, resources, digest_by_resource)
        label = "High" if metrics["score"] >= 60 else "Medium" if metrics["score"] >= 30 else "Low"
        parts = [f"**{entity.name}**: {label} ({metrics['score']}/100)"]
        if metrics["github_stars"]:
            parts.append(f"{metrics['github_stars']:,} stars")
        if metrics["recent_commits"]:
            parts.append(f"{metrics['recent_commits']} recent commits")
        if metrics["releases"]:
            latest = metrics["releases"][0]
            parts.append(f"latest release: {latest['name']} ({latest['date']})")
        momentum_lines.append(" | ".join(parts))

    momentum_section = "\n".join(momentum_lines)

    # Load previous report for change tracking
    previous_report = load_report(topic_name)
    change_tracking = ""
    if previous_report and len(previous_report) > 500:
        # Include a condensed version of the previous report (first 3000 chars)
        change_tracking = (
            "\n\n--- PREVIOUS REPORT (for change tracking) ---\n"
            "Compare against this previous report. In section 2, clearly mark NEW "
            "findings that were NOT in the previous report with a '[NEW]' prefix. "
            "If a company's pricing, features, or strategy changed, call it out.\n\n"
            f"{previous_report[:3000]}\n[... previous report truncated ...]\n"
        )

    # SGERP capabilities context for grounded competitive comparisons
    our_product = (
        "--- OUR PRODUCT (SGERP) — Use as baseline for all comparisons ---\n\n"
        "SGERP is a vertically integrated logistics optimization platform (Singapore HQ + "
        "Bangkok office) that won a competitive tender against Blue Yonder. Key capabilities:\n\n"
        "**Optimization Engine:** Custom OR-Tools fork (486 C++ commits, 10K-15K custom lines). "
        "GLS + LNS metaheuristics, 12+ custom local search operators, 17 first-solution "
        "strategies, 28+ constraint types (time windows, multi-dimensional capacity, PDPTW, "
        "dynamic breaks, geofencing, compound zones, vehicle characteristics/labels with "
        "boolean logic, route compactness, path equalization, LIFO, mutually exclusive groups, "
        "cumulative depot limitations, lateness with penalties, "
        "truck bans, vehicle efficiency).\n\n"
        "**Two-Stage Pipeline:** Multi-strategy optimization "
        "→ time-dependent matrix refinement using actual "
        "departure times from Stage 1 for traffic-accurate "
        "Stage 2 re-optimization.\n\n"
        "**VRPToolbox:** Stateless VRP API (single endpoint, async mode, pre-computed matrix "
        "support, horizontal scaling). 43 releases in 7 months (Jul 2025–Jan 2026).\n\n"
        "**OSRME (custom OSRM fork, 500+ commits):** Time-dependent MLD routing "
        "(tdroute/v1, tdtable/v1), conditional access restrictions, vehicle-specific profiles "
        "(4w/6w/10w/18w), region-specific profiles (left-hand drive, U-turn penalties), "
        "dynamic speed profiles with configurable time quantization.\n\n"
        "**Logistics API:** 10 endpoints — multi-strategy coordinate enrichment (operations "
        "locations → postal code H3 geocoding → full address geocoding), automatic booking "
        "splitting, upload strategies (CLEAR_ALL/KEEP_ASSIGNED/SKIP), dynamic service time.\n\n"
        "**Manual Edit API:** 9 edit action types, dry-run mode, live vehicle protection, "
        "partial success reporting. **SWAT Routes:** Next.js 14 dispatcher UI (AG Grid, "
        "drag-and-drop, auto-planning). **Driver App:** GPS tracking, POD, push notifications.\n\n"
        "**Map Editor:** Next.js, OSM integration, road network graph generation per vehicle "
        "profile, speed profile management with edit history.\n\n"
        "**Simulation:** Fast (prebook) + real-time simulation modes, template system for "
        "scenario cloning, ClickHouse analytics export for post-hoc analysis.\n\n"
        "**SE Asia Expertise:** Bangkok truck bans (automatic time window splitting), Thai "
        "addressing (multi-strategy geocoding), Singapore ERP 2.0 zone cost modeling, "
        "multi-language (TH/VN/KR/ID/CN/JP/EN).\n\n"
        "**Known Gaps (vs enterprise TMS):** No multi-modal transport (air/sea/rail), "
        "no carrier marketplace, no freight settlement/audit, no Gartner/Forrester recognition, "
        "limited self-service configuration UI (API-first), no pre-built KPI dashboards.\n\n"
        "When writing Action Items, frame recommendations relative to what SGERP already has "
        "vs what competitors offer. Don't recommend things SGERP already does well. Focus on "
        "genuine gaps and opportunities where competitors have features SGERP lacks, or where "
        "SGERP's existing strengths can be extended.\n"
        "---\n\n"
    )

    prompt = (
        f"You are a market intelligence analyst. Below is scraped content from "
        f"{len(entities)} companies in the '{topic_display}' space — their websites, "
        f"blogs, pricing pages, and GitHub repositories.\n\n"
        f"Write a comprehensive market intelligence report in markdown. Include:\n\n"
        f"1. **Executive Summary** — 3-5 bullet points of the most important findings\n"
        f"2. **Key Highlights & Recent News** — For each notable blog post, release, "
        f"or announcement, write a short paragraph (2-3 sentences) explaining what was "
        f"published, the key insight or takeaway, and why it matters competitively. "
        f"Group by company. Include source URLs as markdown links. "
        f"Do NOT just list blog titles in a table — extract and explain the actual "
        f"content and insights from each article. If a previous report is provided "
        f"below, prefix genuinely new findings with **[NEW]**.\n"
        f"3. **Momentum & Activity Rankings** — Rank ALL companies by activity level "
        f"using the momentum scores provided below. Show a table with columns: "
        f"Company, Score, GitHub Stars, Recent Releases, Blog Activity, Verdict. "
        f"Highlight who is accelerating vs stagnating.\n"
        f"4. **Pricing Landscape** — a markdown table comparing pricing models, "
        f"tiers, free plans. Link each company name to their pricing page URL.\n"
        f"5. **Company Profiles** — for each company, write 2-4 sentences covering: "
        f"what they do, recent news/activity, pricing model, and anything notable. "
        f"Link the company name in the heading to their main website URL. "
        f"When mentioning blog posts or specific pages, include the URL as a link.\n"
        f"6. **Open Source Landscape** — Dedicated section analyzing OSS projects: "
        f"compare GitHub repos by stars, commit activity, release cadence, language, "
        f"and license. Highlight which OSS tools are gaining traction and what "
        f"features they've added recently.\n"
        f"7. **Competitive Gap Analysis** — For each major competitor category "
        f"(enterprise TMS, mid-market route optimization, open source solvers), "
        f"compare their capabilities against SGERP's strengths listed in OUR PRODUCT "
        f"section. Identify where competitors are catching up, where SGERP leads, "
        f"and where competitors have features SGERP lacks.\n"
        f"8. **Market Observations** — trends, patterns, competitive dynamics\n"
        f"9. **Action Items & Product Opportunities** — Based on competitive gaps, "
        f"emerging features, momentum data, and the OUR PRODUCT capabilities listed "
        f"below, recommend 5-10 specific product features or strategies. For each: "
        f"what it is, which competitors already have it (with links), why it matters, "
        f"and whether it extends an existing SGERP strength or fills a known gap. "
        f"Do NOT recommend features SGERP already has (check OUR PRODUCT section). "
        f"Be concrete. **Sort action items by priority — High first, then Medium, "
        f"then Low.** Within each priority level, order by impact.\n\n"
        f"IMPORTANT: Every fact must link back to its source URL from the raw data. "
        f"The URLs are provided next to each resource name in the data. Use markdown "
        f"links like [text](url) throughout the report.\n\n"
        f"Be specific. Extract actual facts, numbers, dates, product names. "
        f"Skip companies where the content is empty or just a 404 page. "
        f"Write in a professional but concise style.\n\n"
        f"CRITICAL: Output the full report as plain text in your response. "
        f"Do NOT use any tools. Do NOT write to files. Just output the markdown.\n\n"
        f"{our_product}"
        f"--- MOMENTUM SCORES ---\n\n{momentum_section}\n\n"
        f"--- RAW DATA ---\n\n{all_data}"
        f"{change_tracking}"
    )

    session = Session(name="monitor:report", cwd="/tmp")
    session.permission_mode = "bypassPermissions"
    session.max_turns = 3

    try:
        response, _, _, _ = await send_to_claude(prompt, session)
        report = response.strip()
        _save_report(topic_display, report)
        return report
    except Exception:
        logger.exception("Failed to generate report for '%s'", topic_display)
        return "Report generation failed. Check logs."


def _reports_dir() -> Path:
    """Return the directory for saved reports."""
    d = Path(os.path.expanduser("~/.megobari/reports"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _report_key(topic_name: str) -> str:
    """Normalize topic name to a safe filename."""
    return topic_name.lower().replace(" ", "_")


def _save_report(topic_name: str, content: str) -> Path:
    """Save a report to disk."""
    path = _reports_dir() / f"{_report_key(topic_name)}.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Saved report to %s (%d chars)", path, len(content))
    return path


def load_report(topic_name: str | None = None) -> str | None:
    """Load a previously saved report from disk. Returns None if not found.

    If no topic is specified, returns the first available report.
    """
    if topic_name:
        path = _reports_dir() / f"{_report_key(topic_name)}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None
    # No topic specified — return the first available report
    reports = sorted(_reports_dir().glob("*.md"))
    if reports:
        return reports[0].read_text(encoding="utf-8")
    return None


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
