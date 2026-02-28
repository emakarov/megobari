"""Tests for the website monitor engine."""

from unittest.mock import AsyncMock, patch

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.monitor import _format_digest_message, check_resource, compute_content_hash


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
    mock_fetch.assert_awaited_once_with("https://example.com/blog")


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
