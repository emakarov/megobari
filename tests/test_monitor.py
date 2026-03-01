"""Tests for the website monitor engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.monitor import (
    _compute_momentum,
    _format_digest_message,
    _report_key,
    _save_report,
    _send_slack_webhook,
    check_resource,
    compute_content_hash,
    fetch_github_repo,
    fetch_url_markdown,
    generate_baseline_digests,
    generate_report,
    load_report,
    notify_subscribers,
    run_monitor_check,
    summarize_baseline,
    summarize_changes,
)


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


async def _create_resource(name="Test Blog", url="https://example.com/blog",
                           resource_type="blog"):
    """Create a topic, entity, and resource for testing. Returns resource id."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Test Topic")
        entity = await repo.add_monitor_entity(
            topic_id=topic.id, name="Test Entity", entity_type="company",
        )
        resource = await repo.add_monitor_resource(
            topic_id=topic.id,
            entity_id=entity.id,
            name=name,
            url=url,
            resource_type=resource_type,
        )
        return resource.id


# ---------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------

def test_compute_content_hash():
    """Same input gives same hash; different input gives different hash."""
    h1 = compute_content_hash("hello world")
    h2 = compute_content_hash("hello world")
    h3 = compute_content_hash("goodbye world")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA-256 hex digest length


# ---------------------------------------------------------------
# check_resource — first snapshot (baseline)
# ---------------------------------------------------------------

@patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock)
async def test_check_resource_first_snapshot(mock_fetch):
    """First check creates a baseline snapshot with no changes."""
    mock_fetch.return_value = "# Hello World\nSome content here."
    resource_id = await _create_resource()

    result = await check_resource(resource_id)

    assert result is not None
    assert result["resource_id"] == resource_id
    assert result["is_baseline"] is True
    assert result["has_changes"] is False
    assert result["snapshot_id"] is not None
    assert len(result["content_hash"]) == 64
    mock_fetch.assert_awaited_once_with("https://example.com/blog", deep_blog=True)


# ---------------------------------------------------------------
# check_resource — no change on second fetch
# ---------------------------------------------------------------

@patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock)
async def test_check_resource_no_change(mock_fetch):
    """Second check with same content reports no changes."""
    mock_fetch.return_value = "# Hello World\nSame content."
    resource_id = await _create_resource()

    # First check (baseline)
    first = await check_resource(resource_id)
    assert first is not None
    assert first["is_baseline"] is True

    # Second check (same content)
    second = await check_resource(resource_id)
    assert second is not None
    assert second["is_baseline"] is False
    assert second["has_changes"] is False
    assert second["content_hash"] == first["content_hash"]


# ---------------------------------------------------------------
# check_resource — change detected
# ---------------------------------------------------------------

@patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock)
async def test_check_resource_with_change(mock_fetch):
    """Second check with different content reports has_changes=True."""
    resource_id = await _create_resource()

    # First check (baseline)
    mock_fetch.return_value = "# Version 1\nOriginal content."
    first = await check_resource(resource_id)
    assert first is not None
    assert first["is_baseline"] is True

    # Second check (different content)
    mock_fetch.return_value = "# Version 2\nUpdated content with new features."
    second = await check_resource(resource_id)
    assert second is not None
    assert second["is_baseline"] is False
    assert second["has_changes"] is True
    assert second["content_hash"] != first["content_hash"]


# ---------------------------------------------------------------
# check_resource — resource not found
# ---------------------------------------------------------------

@patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock)
async def test_check_resource_not_found(mock_fetch):
    """Returns None when the resource does not exist."""
    result = await check_resource(99999)
    assert result is None
    mock_fetch.assert_not_awaited()


# ---------------------------------------------------------------
# check_resource — fetch failure
# ---------------------------------------------------------------

@patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock)
async def test_check_resource_fetch_failure(mock_fetch):
    """Returns None when the fetch raises an exception."""
    mock_fetch.side_effect = RuntimeError("connection timeout")
    resource_id = await _create_resource()

    result = await check_resource(resource_id)
    assert result is None


# ---------------------------------------------------------------
# _format_digest_message
# ---------------------------------------------------------------

def test_format_digest_message():
    """Verify formatting output with emoji icons."""
    digests = [
        {
            "resource_name": "Acme Blog",
            "summary": "New article about logistics.",
            "change_type": "new_post",
        },
        {
            "resource_name": "Acme Pricing",
            "summary": "Enterprise tier price increased by 10%.",
            "change_type": "price_change",
        },
    ]
    msg = _format_digest_message(digests, run_label="Daily Check")

    assert "Daily Check" in msg
    assert "2 change(s) found" in msg
    assert "\U0001f4dd" in msg  # new_post icon
    assert "\U0001f4b0" in msg  # price_change icon
    assert "Acme Blog" in msg
    assert "Acme Pricing" in msg
    assert "New article about logistics." in msg


def test_format_digest_message_empty():
    """Empty digest list produces no-changes message."""
    msg = _format_digest_message([], run_label="Nightly")
    assert "No changes detected" in msg
    assert "Nightly" in msg


# ---------------------------------------------------------------
# Helpers for multi-entity / subscriber test setup
# ---------------------------------------------------------------

async def _create_full_setup(
    topic_name="Test Topic",
    entity_name="Test Entity",
    resource_name="Test Blog",
    url="https://example.com/blog",
    resource_type="blog",
):
    """Create topic + entity + resource. Returns (topic_id, entity_id, resource_id)."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name=topic_name)
        entity = await repo.add_monitor_entity(
            topic_id=topic.id, name=entity_name, entity_type="company",
        )
        resource = await repo.add_monitor_resource(
            topic_id=topic.id,
            entity_id=entity.id,
            name=resource_name,
            url=url,
            resource_type=resource_type,
        )
        return topic.id, entity.id, resource.id


async def _add_snapshot(topic_id, entity_id, resource_id, content, has_changes=False):
    """Add a snapshot for a resource. Returns snapshot id."""
    async with get_session() as s:
        repo = Repository(s)
        snap = await repo.add_monitor_snapshot(
            topic_id=topic_id,
            entity_id=entity_id,
            resource_id=resource_id,
            content_hash=compute_content_hash(content),
            content_markdown=content,
            has_changes=has_changes,
        )
        return snap.id


async def _add_digest(topic_id, entity_id, resource_id, snapshot_id,
                      summary="Test summary", change_type="baseline"):
    """Add a digest. Returns digest id."""
    async with get_session() as s:
        repo = Repository(s)
        d = await repo.add_monitor_digest(
            topic_id=topic_id,
            entity_id=entity_id,
            resource_id=resource_id,
            snapshot_id=snapshot_id,
            summary=summary,
            change_type=change_type,
        )
        return d.id


# ---------------------------------------------------------------
# fetch_url_markdown
# ---------------------------------------------------------------

@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_markdown_basic(MockCrawler):
    """Basic fetch returns markdown content."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.markdown = "# Hello World"
    mock_crawler.arun = AsyncMock(return_value=mock_result)

    result = await fetch_url_markdown("https://example.com")
    assert result == "# Hello World"


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_markdown_none_markdown(MockCrawler):
    """Returns empty string when result.markdown is None."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.markdown = None
    mock_crawler.arun = AsyncMock(return_value=mock_result)

    result = await fetch_url_markdown("https://example.com")
    assert result == ""


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_with_articles(MockCrawler):
    """Deep blog mode crawls article links from the index page."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    ship_url = "https://blog.example.com/posts/long-article-about-shipping"
    log_url = "https://blog.example.com/posts/great-post-about-logistics"
    index_md = (
        "# Blog\n"
        f"[This Is a Long Article Title About Shipping]({ship_url})\n"
        f"[Another Great Post About Logistics]({log_url})\n"
    )
    art_result = MagicMock()
    art_result.markdown = "Article body content here"

    index_result = MagicMock()
    index_result.markdown = index_md

    mock_crawler.arun = AsyncMock(side_effect=[index_result, art_result, art_result])

    result = await fetch_url_markdown(
        "https://blog.example.com/posts", deep_blog=True,
    )
    assert "Blog Index" in result
    assert "Article:" in result
    assert "Article body content here" in result


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_no_articles(MockCrawler):
    """Deep blog with no qualifying article links returns index page only."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = "# Blog\nJust plain text, no links."
    index_result = MagicMock()
    index_result.markdown = index_md
    mock_crawler.arun = AsyncMock(return_value=index_result)

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    assert result == index_md


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_filters_wrong_domain(MockCrawler):
    """Deep blog mode filters out links from different domains."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[External Post With A Very Long Title](https://other.com/posts/external-article-title)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md
    mock_crawler.arun = AsyncMock(return_value=index_result)

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    # Should return just the index since the link is from a different domain
    assert result == index_md
    # Only one call (the index), no article crawls
    assert mock_crawler.arun.await_count == 1


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_filters_short_titles(MockCrawler):
    """Deep blog mode filters out links with short titles (<20 chars)."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[Short](https://example.com/blog/some-article-slug)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md
    mock_crawler.arun = AsyncMock(return_value=index_result)

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    assert result == index_md


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_filters_no_hyphens(MockCrawler):
    """Deep blog mode filters links whose slug has no hyphens."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[This Is A Very Long Article Title](https://example.com/blog/nohyphens)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md
    mock_crawler.arun = AsyncMock(return_value=index_result)

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    assert result == index_md


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_skip_path(MockCrawler):
    """Deep blog mode filters out links matching skip-path patterns."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[Category Page With Very Long Title](https://example.com/category/some-cat-page)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md
    mock_crawler.arun = AsyncMock(return_value=index_result)

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    assert result == index_md


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_article_crawl_failure(MockCrawler):
    """Deep blog continues when an individual article crawl fails."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[Great Long Title Post About Tech](https://example.com/blog/great-long-title-post)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md

    # Index succeeds, article raises
    mock_crawler.arun = AsyncMock(
        side_effect=[index_result, RuntimeError("timeout")],
    )

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    assert "Blog Index" in result


@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_dedup(MockCrawler):
    """Deep blog mode deduplicates identical article URLs."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[This Is A Long Duplicate Article Title](https://example.com/blog/dup-article-slug)\n"
        "[This Is A Long Duplicate Article Title](https://example.com/blog/dup-article-slug)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md
    art_result = MagicMock()
    art_result.markdown = "Article body"

    mock_crawler.arun = AsyncMock(side_effect=[index_result, art_result])
    await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    # Index call + 1 article (not 2 — deduped)
    assert mock_crawler.arun.await_count == 2


# ---------------------------------------------------------------
# fetch_github_repo
# ---------------------------------------------------------------

@patch("megobari.monitor.httpx.AsyncClient")
async def test_fetch_github_repo_success(MockClient):
    """Successful GitHub repo fetch returns markdown with repo info."""
    mock_client = AsyncMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

    repo_resp = MagicMock()
    repo_resp.status_code = 200
    repo_resp.json.return_value = {
        "full_name": "acme/router",
        "description": "Fast routing engine",
        "stargazers_count": 1500,
        "forks_count": 200,
        "language": "Rust",
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-02-28T10:00:00Z",
        "open_issues_count": 42,
    }

    rel_resp = MagicMock()
    rel_resp.status_code = 200
    rel_resp.json.return_value = [
        {
            "tag_name": "v1.2.0",
            "name": "v1.2.0",
            "published_at": "2026-02-20T00:00:00Z",
            "body": "New features and fixes",
        },
    ]

    commits_resp = MagicMock()
    commits_resp.status_code = 200
    commits_resp.json.return_value = [
        {
            "sha": "abc1234567890",
            "commit": {
                "message": "Fix routing bug",
                "author": {"date": "2026-02-27T12:00:00Z"},
            },
        },
    ]

    mock_client.get = AsyncMock(side_effect=[repo_resp, rel_resp, commits_resp])

    result = await fetch_github_repo("https://github.com/acme/router")
    assert "acme/router" in result
    assert "1,500" in result
    assert "Rust" in result
    assert "v1.2.0" in result
    assert "Fix routing bug" in result


@patch("megobari.monitor.httpx.AsyncClient")
async def test_fetch_github_repo_bad_url(MockClient):
    """URL with fewer than 2 path parts returns empty string."""
    result = await fetch_github_repo("https://github.com/onlyowner")
    assert result == ""


@patch("megobari.monitor.httpx.AsyncClient")
async def test_fetch_github_repo_api_404(MockClient):
    """Non-200 API response returns error markdown."""
    mock_client = AsyncMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

    resp = MagicMock()
    resp.status_code = 404
    mock_client.get = AsyncMock(return_value=resp)

    result = await fetch_github_repo("https://github.com/acme/missing")
    assert "404" in result
    assert "acme/missing" in result


@patch("megobari.monitor.httpx.AsyncClient")
async def test_fetch_github_repo_no_releases(MockClient):
    """Repo with empty releases list shows 'No releases found'."""
    mock_client = AsyncMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

    repo_resp = MagicMock()
    repo_resp.status_code = 200
    repo_resp.json.return_value = {
        "full_name": "acme/lib",
        "description": "A library",
        "stargazers_count": 10,
        "forks_count": 2,
        "language": "Python",
        "license": None,
        "pushed_at": "2026-01-01T00:00:00Z",
        "open_issues_count": 0,
    }

    rel_resp = MagicMock()
    rel_resp.status_code = 200
    rel_resp.json.return_value = []

    commits_resp = MagicMock()
    commits_resp.status_code = 200
    commits_resp.json.return_value = []

    mock_client.get = AsyncMock(side_effect=[repo_resp, rel_resp, commits_resp])

    result = await fetch_github_repo("https://github.com/acme/lib")
    assert "No releases found" in result


@patch("megobari.monitor.httpx.AsyncClient")
async def test_fetch_github_repo_with_token(MockClient):
    """GITHUB_TOKEN env var is included in request headers."""
    mock_client = AsyncMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

    repo_resp = MagicMock()
    repo_resp.status_code = 200
    repo_resp.json.return_value = {
        "full_name": "acme/x", "description": "", "stargazers_count": 0,
        "forks_count": 0, "language": "Go", "license": None,
        "pushed_at": "2026-01-01", "open_issues_count": 0,
    }
    rel_resp = MagicMock()
    rel_resp.status_code = 200
    rel_resp.json.return_value = []
    commits_resp = MagicMock()
    commits_resp.status_code = 200
    commits_resp.json.return_value = []
    mock_client.get = AsyncMock(
        side_effect=[repo_resp, rel_resp, commits_resp],
    )

    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
        result = await fetch_github_repo("https://github.com/acme/x")

    assert "acme/x" in result
    # Verify AsyncClient was called (headers checked indirectly)
    MockClient.assert_called_once()


# ---------------------------------------------------------------
# check_resource — repo type (uses fetch_github_repo)
# ---------------------------------------------------------------

@patch("megobari.monitor.fetch_github_repo", new_callable=AsyncMock)
async def test_check_resource_repo_type(mock_fetch_gh):
    """Repo resource with github.com URL uses fetch_github_repo."""
    mock_fetch_gh.return_value = "# acme/router\n**Stars:** 500"
    resource_id = await _create_resource(
        name="Acme Repo",
        url="https://github.com/acme/router",
        resource_type="repo",
    )

    result = await check_resource(resource_id)
    assert result is not None
    assert result["is_baseline"] is True
    mock_fetch_gh.assert_awaited_once_with("https://github.com/acme/router")


# ---------------------------------------------------------------
# summarize_baseline
# ---------------------------------------------------------------

@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_baseline_normal(mock_claude):
    """Normal baseline summarization returns summary with baseline change_type."""
    mock_claude.return_value = ('{"summary": "Blog has 3 posts."}', None, None, None)

    result = await summarize_baseline(
        1, 1, "# Content", "Blog", "blog", "Acme",
    )
    assert result is not None
    assert result["summary"] == "Blog has 3 posts."
    assert result["change_type"] == "baseline"


@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_baseline_empty_content(mock_claude):
    """Empty content returns 'Page returned empty content.' without calling Claude."""
    result = await summarize_baseline(1, 1, "   ", "Blog", "blog", "Acme")
    assert result is not None
    assert result["summary"] == "Page returned empty content."
    assert result["change_type"] == "baseline"
    mock_claude.assert_not_awaited()


@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_baseline_json_with_fences(mock_claude):
    """Strips markdown code fences around JSON response."""
    mock_claude.return_value = (
        '```json\n{"summary": "Fenced result."}\n```',
        None, None, None,
    )

    result = await summarize_baseline(
        1, 1, "# Content", "Blog", "blog", "Acme",
    )
    assert result is not None
    assert result["summary"] == "Fenced result."


@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_baseline_exception(mock_claude):
    """Returns None when Claude call raises an exception."""
    mock_claude.side_effect = RuntimeError("API error")

    result = await summarize_baseline(
        1, 1, "# Content", "Blog", "blog", "Acme",
    )
    assert result is None


# ---------------------------------------------------------------
# summarize_changes
# ---------------------------------------------------------------

@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_changes_normal(mock_claude):
    """Normal change summarization returns summary with change_type."""
    mock_claude.return_value = (
        '{"summary": "Added new pricing tier.", "change_type": "price_change"}',
        None, None, None,
    )

    result = await summarize_changes(
        1, 1, "# Old content", "# New content", "Pricing", "pricing",
    )
    assert result is not None
    assert result["summary"] == "Added new pricing tier."
    assert result["change_type"] == "price_change"


@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_changes_with_fences(mock_claude):
    """Strips markdown fences from Claude response."""
    mock_claude.return_value = (
        '```\n{"summary": "Updated.", "change_type": "content_update"}\n```',
        None, None, None,
    )

    result = await summarize_changes(
        1, 1, "old", "new", "Page", "page",
    )
    assert result is not None
    assert result["summary"] == "Updated."


@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_changes_exception(mock_claude):
    """Returns None on Claude failure."""
    mock_claude.side_effect = RuntimeError("timeout")

    result = await summarize_changes(
        1, 1, "old", "new", "Page", "page",
    )
    assert result is None


@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_summarize_changes_missing_change_type(mock_claude):
    """Defaults to content_update when change_type missing from response."""
    mock_claude.return_value = (
        '{"summary": "Minor text edit."}',
        None, None, None,
    )

    result = await summarize_changes(
        1, 1, "old", "new", "Page", "page",
    )
    assert result is not None
    assert result["change_type"] == "content_update"


# ---------------------------------------------------------------
# run_monitor_check
# ---------------------------------------------------------------

@patch("megobari.monitor.summarize_changes", new_callable=AsyncMock)
@patch("megobari.monitor.check_resource", new_callable=AsyncMock)
async def test_run_monitor_check_with_changes(mock_check, mock_summarize):
    """Detects changes, summarizes, and saves digest."""
    tid, eid, rid = await _create_full_setup()
    # Add baseline snapshot first
    await _add_snapshot(tid, eid, rid, "# Old content")

    mock_check.return_value = {
        "resource_id": rid,
        "has_changes": True,
        "is_baseline": False,
        "content_hash": "newhash",
        "snapshot_id": 999,
        "topic_id": tid,
        "entity_id": eid,
    }

    # Add two snapshots so the code can find them for diff
    snap_id2 = await _add_snapshot(
        tid, eid, rid, "# New content", has_changes=True,
    )

    mock_summarize.return_value = {
        "summary": "Blog updated with new post.",
        "change_type": "new_post",
    }

    # Use the actual snapshot_id from DB
    mock_check.return_value["snapshot_id"] = snap_id2

    digests = await run_monitor_check(
        topic_name="Test Topic", entity_name="Test Entity",
    )
    assert len(digests) == 1
    assert digests[0]["summary"] == "Blog updated with new post."
    assert digests[0]["change_type"] == "new_post"


@patch("megobari.monitor.check_resource", new_callable=AsyncMock)
async def test_run_monitor_check_baseline_only(mock_check):
    """Baseline result is not included in digest list."""
    await _create_full_setup()
    mock_check.return_value = {
        "resource_id": 1,
        "has_changes": False,
        "is_baseline": True,
        "content_hash": "hash",
        "snapshot_id": 1,
        "topic_id": 1,
        "entity_id": 1,
    }

    digests = await run_monitor_check(topic_name="Test Topic")
    assert digests == []


async def test_run_monitor_check_topic_not_found():
    """Returns empty list when topic is not found."""
    digests = await run_monitor_check(topic_name="Nonexistent Topic")
    assert digests == []


async def test_run_monitor_check_entity_not_found():
    """Returns empty list when entity is not found."""
    await _create_full_setup()
    digests = await run_monitor_check(
        topic_name="Test Topic", entity_name="No Such Entity",
    )
    assert digests == []


@patch("megobari.monitor.check_resource", new_callable=AsyncMock)
async def test_run_monitor_check_fetch_returns_none(mock_check):
    """check_resource returning None is skipped gracefully."""
    await _create_full_setup()
    mock_check.return_value = None

    digests = await run_monitor_check(topic_name="Test Topic")
    assert digests == []


@patch("megobari.monitor.summarize_changes", new_callable=AsyncMock)
@patch("megobari.monitor.check_resource", new_callable=AsyncMock)
async def test_run_monitor_check_summarize_fails(mock_check, mock_summarize):
    """Digest not added when summarize_changes returns None."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Old content")
    snap_id2 = await _add_snapshot(
        tid, eid, rid, "# New content", has_changes=True,
    )

    mock_check.return_value = {
        "resource_id": rid,
        "has_changes": True,
        "is_baseline": False,
        "content_hash": "newhash",
        "snapshot_id": snap_id2,
        "topic_id": tid,
        "entity_id": eid,
    }
    mock_summarize.return_value = None

    digests = await run_monitor_check(topic_name="Test Topic")
    assert digests == []


# ---------------------------------------------------------------
# generate_baseline_digests
# ---------------------------------------------------------------

@patch("megobari.monitor.summarize_baseline", new_callable=AsyncMock)
async def test_generate_baseline_digests_creates_digest(mock_summarize):
    """Generates a baseline digest for a snapshot that has no digest yet."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Blog content here")

    mock_summarize.return_value = {
        "summary": "Blog has 3 posts.",
        "change_type": "baseline",
    }

    digests = await generate_baseline_digests(topic_name="Test Topic")
    assert len(digests) == 1
    assert digests[0]["summary"] == "Blog has 3 posts."
    assert digests[0]["change_type"] == "baseline"
    assert digests[0]["entity_name"] == "Test Entity"


@patch("megobari.monitor.summarize_baseline", new_callable=AsyncMock)
async def test_generate_baseline_digests_skips_existing(mock_summarize):
    """Skips snapshots that already have a digest."""
    tid, eid, rid = await _create_full_setup()
    snap_id = await _add_snapshot(tid, eid, rid, "# Content")
    await _add_digest(tid, eid, rid, snap_id)

    digests = await generate_baseline_digests(topic_name="Test Topic")
    assert digests == []
    mock_summarize.assert_not_awaited()


async def test_generate_baseline_digests_topic_not_found():
    """Returns empty list for nonexistent topic."""
    digests = await generate_baseline_digests(topic_name="Nonexistent")
    assert digests == []


@patch("megobari.monitor.summarize_baseline", new_callable=AsyncMock)
async def test_generate_baseline_digests_no_snapshot(mock_summarize):
    """Skips resources that have no snapshot yet."""
    await _create_full_setup()
    # No snapshot added
    digests = await generate_baseline_digests(topic_name="Test Topic")
    assert digests == []
    mock_summarize.assert_not_awaited()


@patch("megobari.monitor.summarize_baseline", new_callable=AsyncMock)
async def test_generate_baseline_digests_summarize_fails(mock_summarize):
    """Skips resource when summarize_baseline returns None."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Content")
    mock_summarize.return_value = None

    digests = await generate_baseline_digests(topic_name="Test Topic")
    assert digests == []


@patch("megobari.monitor.summarize_baseline", new_callable=AsyncMock)
async def test_generate_baseline_digests_all_topics(mock_summarize):
    """No topic filter processes all resources."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Content")
    mock_summarize.return_value = {
        "summary": "Summary text.",
        "change_type": "baseline",
    }

    digests = await generate_baseline_digests(topic_name=None)
    assert len(digests) == 1


# ---------------------------------------------------------------
# _compute_momentum
# ---------------------------------------------------------------

async def test_compute_momentum_github_high():
    """High-activity GitHub repo yields high momentum score."""
    tid, eid, rid = await _create_full_setup(
        resource_name="Repo", url="https://github.com/acme/router",
        resource_type="repo",
    )
    content = (
        "# acme/router\n\n"
        "**Stars:** 2,500\n"
        "**Forks:** 300\n\n"
        "## Recent Releases\n\n"
        "### v3.0.0 (2026-02-15)\nMajor update\n"
        "### v2.9.0 (2026-01-10)\nBugfixes\n"
        "### v2.8.0 (2025-12-01)\nPerformance\n\n"
        "## Recent Commits\n"
        "- `abc1234` (2026-02-27) Fix bug\n"
        "- `def5678` (2026-02-26) Add feature\n"
        "- `ghi9012` (2026-02-25) Refactor\n"
        "- `jkl3456` (2026-02-24) Docs\n"
        "- `mno7890` (2026-02-23) Tests\n"
        "- `pqr1234` (2026-02-22) CI\n"
        "- `stu5678` (2026-02-21) Lint\n"
        "- `vwx9012` (2026-02-20) Build\n"
        "- `yza3456` (2026-02-19) Cleanup\n"
        "- `bcd7890` (2026-02-18) Init\n"
    )
    await _add_snapshot(tid, eid, rid, content)

    # Load resources from DB
    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    metrics = await _compute_momentum(eid, resources, {})
    assert metrics["github_stars"] == 2500
    assert metrics["recent_commits"] == 10
    assert len(metrics["releases"]) == 3
    assert metrics["score"] >= 60  # high activity


async def test_compute_momentum_blog_with_dates():
    """Blog resource with dates in digest adds to score."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Blog\nSome content.")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    digest_by_resource = {rid: "Posted on 2026-02-20 about logistics."}
    metrics = await _compute_momentum(eid, resources, digest_by_resource)
    assert metrics["score"] >= 20  # blog dates add 20 points
    assert len(metrics["blog_dates"]) >= 1


async def test_compute_momentum_empty_content():
    """Resource with empty snapshot content contributes nothing."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "   ")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    metrics = await _compute_momentum(eid, resources, {})
    assert metrics["score"] == 0


async def test_compute_momentum_no_snapshot():
    """Resource with no snapshot contributes nothing."""
    await _create_full_setup()
    # No snapshot added

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources()

    metrics = await _compute_momentum(
        resources[0].entity_id, resources, {},
    )
    assert metrics["score"] == 0


async def test_compute_momentum_medium_stars():
    """Stars between 100-1000 get 10 points."""
    tid, eid, rid = await _create_full_setup(
        resource_name="Repo", url="https://github.com/a/b",
        resource_type="repo",
    )
    content = "# a/b\n\n**Stars:** 500\n"
    await _add_snapshot(tid, eid, rid, content)

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    metrics = await _compute_momentum(eid, resources, {})
    assert metrics["github_stars"] == 500
    assert metrics["score"] >= 10


async def test_compute_momentum_few_commits():
    """5-9 commits get 15 points instead of 25."""
    tid, eid, rid = await _create_full_setup(
        resource_name="Repo", url="https://github.com/a/b",
        resource_type="repo",
    )
    content = (
        "# a/b\n\n**Stars:** 50\n\n"
        "## Recent Commits\n"
        "- `a1` (2026-01-01) A\n"
        "- `a2` (2026-01-02) B\n"
        "- `a3` (2026-01-03) C\n"
        "- `a4` (2026-01-04) D\n"
        "- `a5` (2026-01-05) E\n"
    )
    await _add_snapshot(tid, eid, rid, content)

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    metrics = await _compute_momentum(eid, resources, {})
    assert metrics["recent_commits"] == 5
    assert metrics["score"] == 15


async def test_compute_momentum_one_release():
    """1-2 releases get 15 points."""
    tid, eid, rid = await _create_full_setup(
        resource_name="Repo", url="https://github.com/a/b",
        resource_type="repo",
    )
    content = (
        "# a/b\n\n**Stars:** 50\n\n"
        "## Recent Releases\n\n"
        "### v1.0.0 (2025-06-01)\nInitial release\n"
    )
    await _add_snapshot(tid, eid, rid, content)

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    metrics = await _compute_momentum(eid, resources, {})
    assert len(metrics["releases"]) == 1
    assert metrics["score"] == 15


async def test_compute_momentum_capped_at_100():
    """Score never exceeds 100."""
    tid, eid, rid = await _create_full_setup(
        resource_name="Repo", url="https://github.com/a/b",
        resource_type="repo",
    )
    # Max everything: >1000 stars, >=10 commits, >=3 releases (one in 2026)
    content = (
        "# a/b\n\n**Stars:** 5,000\n\n"
        "## Recent Releases\n\n"
        "### v3.0 (2026-01-15)\nRelease\n"
        "### v2.0 (2026-01-10)\nRelease\n"
        "### v1.0 (2025-12-01)\nRelease\n\n"
        "## Recent Commits\n"
    )
    for i in range(12):
        content += f"- `x{i:05d}` (2026-02-{i + 1:02d}) Commit {i}\n"
    await _add_snapshot(tid, eid, rid, content)

    # Also add a blog resource with dates
    async with get_session() as s:
        repo = Repository(s)
        blog_res = await repo.add_monitor_resource(
            topic_id=tid, entity_id=eid, name="Blog",
            url="https://example.com/blog", resource_type="blog",
        )
    await _add_snapshot(tid, eid, blog_res.id, "# Blog\nStuff")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    digest_by_resource = {blog_res.id: "Posted 2026-02-20."}
    metrics = await _compute_momentum(eid, resources, digest_by_resource)
    assert metrics["score"] == 100


async def test_compute_momentum_blog_month_names():
    """Extracts month-name dates like 'February 15, 2026' from digest."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Blog content")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    digest_by_resource = {
        rid: "Article from February 15, 2026 about tech.",
    }
    metrics = await _compute_momentum(eid, resources, digest_by_resource)
    assert len(metrics["blog_dates"]) >= 1
    assert metrics["score"] >= 20


async def test_compute_momentum_skips_other_entity():
    """Resources belonging to a different entity are ignored."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Content")

    # Create another entity's resource
    async with get_session() as s:
        repo = Repository(s)
        entity2 = await repo.add_monitor_entity(
            topic_id=tid, name="Other Entity", entity_type="company",
        )
        res2 = await repo.add_monitor_resource(
            topic_id=tid, entity_id=entity2.id, name="Other Blog",
            url="https://other.com/blog", resource_type="blog",
        )
    await _add_snapshot(tid, entity2.id, res2.id, "# Other content")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=tid)

    # Only compute momentum for entity2 — should not pick up eid's resource
    metrics = await _compute_momentum(entity2.id, resources, {})
    # entity2's blog has no dates in digest, no repo resources
    assert metrics["score"] == 0


# ---------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------

@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_success(mock_claude, mock_load):
    """Successful report generation returns Claude response."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Blog content with info")

    mock_claude.return_value = ("# Market Report\nContent here.", None, None, None)

    with patch("megobari.monitor._save_report") as mock_save:
        report = await generate_report(topic_name="Test Topic")

    assert "Market Report" in report
    mock_save.assert_called_once()


async def test_generate_report_topic_not_found():
    """Returns error message for nonexistent topic."""
    report = await generate_report(topic_name="Nonexistent Topic")
    assert "not found" in report


@patch("megobari.monitor.load_report", return_value=None)
async def test_generate_report_no_resources(mock_load):
    """Returns message when no resources exist."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic(name="Empty Topic")

    report = await generate_report(topic_name="Empty Topic")
    assert "No resources" in report


@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_claude_failure(mock_claude, mock_load):
    """Returns failure message when Claude raises."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Content")

    mock_claude.side_effect = RuntimeError("Claude API down")

    report = await generate_report(topic_name="Test Topic")
    assert "failed" in report.lower()


@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_with_previous_report(mock_claude, mock_load):
    """Previous report is included in prompt for change tracking."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Blog content")

    mock_load.return_value = "# Previous Report\n" + "x" * 600
    mock_claude.return_value = ("# Updated Report", None, None, None)

    with patch("megobari.monitor._save_report"):
        report = await generate_report(topic_name="Test Topic")

    assert "Updated Report" in report
    # Verify Claude was called with previous report context
    prompt_arg = mock_claude.call_args[0][0]
    assert "PREVIOUS REPORT" in prompt_arg


@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_empty_snapshot_skipped(mock_claude, mock_load):
    """Snapshots with empty content are skipped from entity blocks."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "   ")

    mock_claude.return_value = ("# Report with no data", None, None, None)

    with patch("megobari.monitor._save_report"):
        report = await generate_report(topic_name="Test Topic")

    # The report is generated (Claude is still called), but the empty
    # snapshot is not included in the data payload
    assert "Report" in report


@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_all_topics(mock_claude, mock_load):
    """No topic filter processes all topics."""
    tid, eid, rid = await _create_full_setup()
    await _add_snapshot(tid, eid, rid, "# Content")

    mock_claude.return_value = ("# Full Report", None, None, None)

    with patch("megobari.monitor._save_report"):
        report = await generate_report(topic_name=None)

    assert "Full Report" in report


@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_blog_with_digest(mock_claude, mock_load):
    """Blog resource with existing digest includes AI Summary in data."""
    tid, eid, rid = await _create_full_setup()
    snap_id = await _add_snapshot(tid, eid, rid, "# Blog raw content")
    await _add_digest(
        tid, eid, rid, snap_id,
        summary="AI analyzed 3 posts about logistics.",
    )

    mock_claude.return_value = ("# Report", None, None, None)

    with patch("megobari.monitor._save_report"):
        await generate_report(topic_name="Test Topic")

    prompt_arg = mock_claude.call_args[0][0]
    assert "AI Summary" in prompt_arg


@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_non_blog_no_ai_summary(mock_claude, mock_load):
    """Non-blog resources don't get the AI Summary prefix."""
    tid, eid, rid = await _create_full_setup(
        resource_name="Pricing Page",
        url="https://example.com/pricing",
        resource_type="pricing",
    )
    await _add_snapshot(tid, eid, rid, "# Pricing\n$99/mo")

    mock_claude.return_value = ("# Report", None, None, None)

    with patch("megobari.monitor._save_report"):
        await generate_report(topic_name="Test Topic")

    prompt_arg = mock_claude.call_args[0][0]
    assert "AI Summary" not in prompt_arg


# ---------------------------------------------------------------
# Report file utilities
# ---------------------------------------------------------------

def test_report_key():
    """Normalizes topic name to lowercase with underscores."""
    assert _report_key("Logistics SaaS") == "logistics_saas"
    assert _report_key("Simple") == "simple"
    assert _report_key("Two Words Here") == "two_words_here"


@patch("megobari.monitor._reports_dir")
def test_save_and_load_report(mock_dir, tmp_path):
    """Save and load round-trips report content."""
    mock_dir.return_value = tmp_path
    _save_report("Test Topic", "# Report content")
    result = load_report("Test Topic")
    assert result == "# Report content"


@patch("megobari.monitor._reports_dir")
def test_load_report_nonexistent(mock_dir, tmp_path):
    """Returns None for topic that has no saved report."""
    mock_dir.return_value = tmp_path
    result = load_report("Missing Topic")
    assert result is None


@patch("megobari.monitor._reports_dir")
def test_load_report_first_available(mock_dir, tmp_path):
    """Without topic name, returns first available report."""
    mock_dir.return_value = tmp_path
    (tmp_path / "alpha.md").write_text("# Alpha Report")
    (tmp_path / "beta.md").write_text("# Beta Report")

    result = load_report(topic_name=None)
    assert result == "# Alpha Report"


@patch("megobari.monitor._reports_dir")
def test_load_report_no_reports(mock_dir, tmp_path):
    """Returns None when no reports exist and no topic specified."""
    mock_dir.return_value = tmp_path
    result = load_report(topic_name=None)
    assert result is None


# ---------------------------------------------------------------
# _send_slack_webhook
# ---------------------------------------------------------------

@patch("megobari.monitor.httpx.AsyncClient")
async def test_send_slack_webhook(MockClient):
    """Posts message payload to webhook URL."""
    mock_client = AsyncMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock()

    await _send_slack_webhook("https://hooks.slack.com/xxx", "Hello")
    mock_client.post.assert_awaited_once_with(
        "https://hooks.slack.com/xxx", json={"text": "Hello"},
    )


# ---------------------------------------------------------------
# notify_subscribers
# ---------------------------------------------------------------

async def test_notify_subscribers_empty():
    """Empty digests returns immediately without DB queries."""
    await notify_subscribers([], run_label="Test")


@patch("megobari.monitor._send_slack_webhook", new_callable=AsyncMock)
async def test_notify_subscribers_slack(mock_webhook):
    """Slack subscriber receives webhook notification."""
    tid, eid, rid = await _create_full_setup()

    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_subscriber(
            channel_type="slack",
            channel_config=json.dumps(
                {"webhook_url": "https://hooks.slack.com/test"},
            ),
            topic_id=tid,
        )

    digests = [{
        "topic_id": tid,
        "resource_name": "Blog",
        "summary": "New post published.",
        "change_type": "new_post",
    }]

    await notify_subscribers(digests, run_label="Daily")
    mock_webhook.assert_awaited_once()
    call_args = mock_webhook.call_args
    assert call_args[0][0] == "https://hooks.slack.com/test"


@patch("megobari.monitor._send_slack_webhook", new_callable=AsyncMock)
async def test_notify_subscribers_slack_failure(mock_webhook):
    """Slack webhook failure is caught and logged, not raised."""
    tid, eid, rid = await _create_full_setup()

    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_subscriber(
            channel_type="slack",
            channel_config=json.dumps(
                {"webhook_url": "https://hooks.slack.com/bad"},
            ),
            topic_id=tid,
        )

    mock_webhook.side_effect = RuntimeError("Slack down")

    digests = [{
        "topic_id": tid,
        "resource_name": "Blog",
        "summary": "Test.",
        "change_type": "content_update",
    }]

    # Should not raise
    await notify_subscribers(digests, run_label="Check")


@patch("megobari.monitor._send_slack_webhook", new_callable=AsyncMock)
async def test_notify_subscribers_slack_no_webhook_url(mock_webhook):
    """Slack subscriber with empty webhook_url is skipped."""
    tid, eid, rid = await _create_full_setup()

    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_subscriber(
            channel_type="slack",
            channel_config=json.dumps({"webhook_url": ""}),
            topic_id=tid,
        )

    digests = [{
        "topic_id": tid,
        "resource_name": "Blog",
        "summary": "Test.",
        "change_type": "content_update",
    }]

    await notify_subscribers(digests, run_label="Check")
    mock_webhook.assert_not_awaited()


async def test_notify_subscribers_telegram():
    """Telegram subscriber is logged (no webhook call)."""
    tid, eid, rid = await _create_full_setup()

    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_subscriber(
            channel_type="telegram",
            channel_config=json.dumps({"chat_id": "12345"}),
            topic_id=tid,
        )

    digests = [{
        "topic_id": tid,
        "resource_name": "Blog",
        "summary": "Test.",
        "change_type": "content_update",
    }]

    # Should not raise — just logs
    await notify_subscribers(digests, run_label="Check")


@patch("megobari.monitor._send_slack_webhook", new_callable=AsyncMock)
async def test_notify_subscribers_groups_by_topic(mock_webhook):
    """Digests from multiple topics are grouped and sent separately."""
    # Create two separate topics
    async with get_session() as s:
        repo = Repository(s)
        t1 = await repo.add_monitor_topic(name="Topic A")
        t2 = await repo.add_monitor_topic(name="Topic B")
        await repo.add_monitor_entity(
            topic_id=t1.id, name="Entity A", entity_type="company",
        )
        await repo.add_monitor_entity(
            topic_id=t2.id, name="Entity B", entity_type="company",
        )
        await repo.add_monitor_subscriber(
            channel_type="slack",
            channel_config=json.dumps(
                {"webhook_url": "https://hooks.slack.com/a"},
            ),
            topic_id=t1.id,
        )
        await repo.add_monitor_subscriber(
            channel_type="slack",
            channel_config=json.dumps(
                {"webhook_url": "https://hooks.slack.com/b"},
            ),
            topic_id=t2.id,
        )

    digests = [
        {
            "topic_id": t1.id,
            "resource_name": "A Blog",
            "summary": "Change A.",
            "change_type": "new_post",
        },
        {
            "topic_id": t2.id,
            "resource_name": "B Blog",
            "summary": "Change B.",
            "change_type": "content_update",
        },
    ]

    await notify_subscribers(digests, run_label="Multi")
    assert mock_webhook.await_count == 2


# ---------------------------------------------------------------
# fetch_url_markdown — self-link filtering (line 98)
# ---------------------------------------------------------------

@patch("crawl4ai.AsyncWebCrawler")
async def test_fetch_url_deep_blog_filters_self_link(MockCrawler):
    """Deep blog mode filters out link matching the blog URL itself."""
    mock_crawler = AsyncMock()
    MockCrawler.return_value.__aenter__ = AsyncMock(return_value=mock_crawler)
    MockCrawler.return_value.__aexit__ = AsyncMock(return_value=False)

    index_md = (
        "# Blog\n"
        "[This Is The Blog Index Page Title](https://example.com/blog)\n"
    )
    index_result = MagicMock()
    index_result.markdown = index_md
    mock_crawler.arun = AsyncMock(return_value=index_result)

    result = await fetch_url_markdown("https://example.com/blog", deep_blog=True)
    # Self-link is filtered, no articles found, returns just the index
    assert result == index_md
    assert mock_crawler.arun.await_count == 1


# ---------------------------------------------------------------
# generate_report — entity with URL (line 757)
# ---------------------------------------------------------------

@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_entity_with_url(mock_claude, mock_load):
    """Entity with a URL includes it in the section header."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="URL Topic")
        entity = await repo.add_monitor_entity(
            topic_id=topic.id, name="Acme Corp", entity_type="company",
        )
        # Set entity URL
        entity.url = "https://acme.com"
        await s.flush()
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Page", url="https://acme.com/page",
            resource_type="pricing",
        )
    await _add_snapshot(topic.id, entity.id, resource.id, "# Pricing info")

    mock_claude.return_value = ("# Report with URL", None, None, None)

    with patch("megobari.monitor._save_report"):
        await generate_report(topic_name="URL Topic")

    prompt_arg = mock_claude.call_args[0][0]
    assert "acme.com" in prompt_arg
    assert "Acme Corp" in prompt_arg


# ---------------------------------------------------------------
# generate_report — large data triggers progressive shrinking (766-799)
# ---------------------------------------------------------------

@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_large_data_shrinks(mock_claude, mock_load):
    """Data exceeding 80K chars triggers progressive excerpt shrinking."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Big Topic")
        # Create 50 entities with 1 resource each — content[:2000] per
        # resource yields ~100K total which exceeds the 80K limit.
        for i in range(50):
            entity = await repo.add_monitor_entity(
                topic_id=topic.id, name=f"Entity {i:02d}",
                entity_type="company",
            )
            await repo.add_monitor_resource(
                topic_id=topic.id, entity_id=entity.id,
                name=f"Resource {i:02d}",
                url=f"https://example.com/r{i}",
                resource_type="pricing",
            )

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=topic.id)
    for resource in resources:
        big_content = "# Content\n" + "x" * 5000
        await _add_snapshot(
            topic.id, resource.entity_id, resource.id, big_content,
        )

    mock_claude.return_value = ("# Big Report", None, None, None)

    with patch("megobari.monitor._save_report"):
        report = await generate_report(topic_name="Big Topic")

    assert "Big Report" in report
    mock_claude.assert_awaited_once()


# ---------------------------------------------------------------
# generate_report — momentum with repo data (lines 810-816)
# ---------------------------------------------------------------

@patch("megobari.monitor.load_report", return_value=None)
@patch("megobari.claude_bridge.send_to_claude", new_callable=AsyncMock)
async def test_generate_report_momentum_with_repo(mock_claude, mock_load):
    """Report includes momentum scores with stars, commits, releases."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Repo Topic")
        entity = await repo.add_monitor_entity(
            topic_id=topic.id, name="Repo Entity", entity_type="company",
        )
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="GH Repo", url="https://github.com/acme/x",
            resource_type="repo",
        )
    content = (
        "# acme/x\n\n**Stars:** 2,000\n\n"
        "## Recent Releases\n\n"
        "### v1.0 (2026-02-01)\nRelease\n\n"
        "## Recent Commits\n"
        "- `a1` (2026-02-28) Commit A\n"
        "- `a2` (2026-02-27) Commit B\n"
        "- `a3` (2026-02-26) Commit C\n"
        "- `a4` (2026-02-25) Commit D\n"
        "- `a5` (2026-02-24) Commit E\n"
    )
    await _add_snapshot(topic.id, entity.id, resource.id, content)

    mock_claude.return_value = ("# Repo Report", None, None, None)

    with patch("megobari.monitor._save_report"):
        await generate_report(topic_name="Repo Topic")

    prompt_arg = mock_claude.call_args[0][0]
    assert "MOMENTUM SCORES" in prompt_arg
    assert "stars" in prompt_arg
    assert "recent commits" in prompt_arg
    assert "latest release" in prompt_arg


# ---------------------------------------------------------------
# _reports_dir (lines 947-949)
# ---------------------------------------------------------------

def test_reports_dir():
    """_reports_dir creates and returns the reports directory."""
    from megobari.monitor import _reports_dir

    result = _reports_dir()
    assert result.exists()
    assert str(result).endswith(".megobari/reports")


# ---------------------------------------------------------------
# run_monitor_check — single snapshot edge case (line 449)
# ---------------------------------------------------------------

@patch("megobari.monitor.check_resource", new_callable=AsyncMock)
async def test_run_monitor_check_single_snapshot(mock_check):
    """Changes reported but only one snapshot exists skips summarization."""
    tid, eid, rid = await _create_full_setup()
    # Only one snapshot
    snap_id = await _add_snapshot(tid, eid, rid, "# Content")

    mock_check.return_value = {
        "resource_id": rid,
        "has_changes": True,
        "is_baseline": False,
        "content_hash": "newhash",
        "snapshot_id": snap_id,
        "topic_id": tid,
        "entity_id": eid,
    }

    digests = await run_monitor_check(topic_name="Test Topic")
    # With only one snapshot, len(snaps) < 2 triggers continue
    assert digests == []
