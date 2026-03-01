"""Tests for /monitor command handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.formatting import TelegramFormatter
from megobari.handlers.monitoring import cmd_monitor


@pytest.fixture(autouse=True)
async def db():
    """Initialize in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


class MockTransport:
    """Lightweight mock implementing TransportContext interface for tests."""

    def __init__(self, args=None, text="hello",
                 user_id=12345, chat_id=12345, message_id=99,
                 bot_data=None, caption=None):
        self._args = args or []
        self._text = text
        self._user_id = user_id
        self._chat_id = chat_id
        self._message_id = message_id
        self._caption = caption
        self._formatter = TelegramFormatter()
        self._bot_data = bot_data if bot_data is not None else {}

        # Mock all async methods
        self.reply = AsyncMock(return_value=MagicMock())
        self.reply_document = AsyncMock()
        self.reply_photo = AsyncMock()
        self.send_message = AsyncMock()
        self.edit_message = AsyncMock()
        self.delete_message = AsyncMock()
        self.send_typing = AsyncMock()
        self.set_reaction = AsyncMock()
        self.download_photo = AsyncMock(return_value=None)
        self.download_document = AsyncMock(return_value=None)
        self.download_voice = AsyncMock(return_value=None)

    @property
    def args(self):
        """Return command arguments."""
        return self._args

    @property
    def text(self):
        """Return message text."""
        return self._text

    @property
    def chat_id(self):
        """Return chat ID."""
        return self._chat_id

    @property
    def message_id(self):
        """Return message ID."""
        return self._message_id

    @property
    def user_id(self):
        """Return user ID."""
        return self._user_id

    @property
    def username(self):
        """Return test username."""
        return "testuser"

    @property
    def first_name(self):
        """Return test first name."""
        return "Test"

    @property
    def last_name(self):
        """Return test last name."""
        return "User"

    @property
    def caption(self):
        """Return caption."""
        return self._caption

    @property
    def formatter(self):
        """Return formatter."""
        return self._formatter

    @property
    def bot_data(self):
        """Return bot data dict."""
        return self._bot_data

    @property
    def transport_name(self):
        """Return transport name."""
        return "test"

    @property
    def max_message_length(self):
        """Return max message length."""
        return 4096


# ------------------------------------------------------------------
# Helper to seed DB with test data
# ------------------------------------------------------------------

async def _seed_topic_entity_resource():
    """Create a topic with entity and resource. Returns (topic, entity, resource)."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(
            name="TestTopic", description="desc",
        )
        entity = await repo.add_monitor_entity(
            topic_id=topic.id, name="TestEntity",
            url="https://test.com", entity_type="company",
        )
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="TestBlog", url="https://test.com/blog",
            resource_type="blog",
        )
        return topic, entity, resource


# ------------------------------------------------------------------
# TestCmdMonitor — dispatcher tests
# ------------------------------------------------------------------

class TestCmdMonitor:
    """Tests for cmd_monitor dispatch logic."""

    async def test_no_args_shows_overview(self):
        """No args should call _show_overview."""
        ctx = MockTransport(args=[])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No monitor topics" in text

    async def test_unknown_subcommand_shows_usage(self):
        """Unknown subcommand should show usage text."""
        ctx = MockTransport(args=["foo"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_dispatches_topic(self):
        """'topic list' should dispatch to _handle_topic."""
        ctx = MockTransport(args=["topic", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No topics" in text

    async def test_dispatches_entity(self):
        """'entity list' should dispatch to _handle_entity."""
        ctx = MockTransport(args=["entity", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No entities" in text

    async def test_dispatches_resource(self):
        """'resource list' should dispatch to _handle_resource."""
        ctx = MockTransport(args=["resource", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No resources" in text

    @patch("megobari.monitor.run_monitor_check", new_callable=AsyncMock)
    @patch(
        "megobari.monitor._format_digest_message",
        return_value="No changes detected.",
    )
    @patch("megobari.monitor.notify_subscribers", new_callable=AsyncMock)
    async def test_dispatches_check(self, _notify, _fmt, mock_check):
        """'check' should dispatch to _handle_check."""
        mock_check.return_value = []
        ctx = MockTransport(args=["check"])
        await cmd_monitor(ctx)
        mock_check.assert_awaited_once()

    @patch(
        "megobari.monitor.generate_baseline_digests",
        new_callable=AsyncMock,
    )
    async def test_dispatches_baseline(self, mock_baseline):
        """'baseline' should dispatch to _handle_baseline."""
        mock_baseline.return_value = []
        ctx = MockTransport(args=["baseline"])
        await cmd_monitor(ctx)
        mock_baseline.assert_awaited_once()

    @patch("megobari.monitor.generate_report", new_callable=AsyncMock)
    async def test_dispatches_report(self, mock_report):
        """'report' should dispatch to _handle_report."""
        mock_report.return_value = "Report text"
        ctx = MockTransport(args=["report"])
        await cmd_monitor(ctx)
        mock_report.assert_awaited_once()

    async def test_dispatches_digest(self):
        """'digest' should dispatch to _handle_digest."""
        ctx = MockTransport(args=["digest"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No digests" in text


# ------------------------------------------------------------------
# TestShowOverview
# ------------------------------------------------------------------

class TestShowOverview:
    """Tests for _show_overview."""

    async def test_no_topics(self):
        """Empty DB shows 'No monitor topics'."""
        ctx = MockTransport(args=[])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No monitor topics" in text

    async def test_with_topics(self):
        """Topics with entities/resources show counts."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=[])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestTopic" in text
        assert "1 entities" in text
        assert "1 resources" in text
        assert "desc" in text


# ------------------------------------------------------------------
# TestHandleTopic
# ------------------------------------------------------------------

class TestHandleTopic:
    """Tests for _handle_topic."""

    async def test_list_empty(self):
        """No topics shows empty message."""
        ctx = MockTransport(args=["topic", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No topics" in text

    async def test_list_with_topics(self):
        """Topics exist shows their names."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["topic", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestTopic" in text
        assert "Topics:" in text

    async def test_list_implicit(self):
        """No sub-action defaults to list."""
        ctx = MockTransport(args=["topic"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No topics" in text

    async def test_add_missing_name(self):
        """'topic add' without name shows usage."""
        ctx = MockTransport(args=["topic", "add"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_add_success(self):
        """'topic add NewTopic' creates topic."""
        ctx = MockTransport(args=["topic", "add", "NewTopic"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "NewTopic" in text
        assert "created" in text

    async def test_add_with_description(self):
        """'topic add NewTopic A description' creates topic with description."""
        ctx = MockTransport(
            args=["topic", "add", "NewTopic", "A", "description"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "NewTopic" in text
        assert "created" in text
        # Verify description stored
        async with get_session() as s:
            repo = Repository(s)
            topic = await repo.get_monitor_topic("NewTopic")
            assert topic is not None
            assert topic.description == "A description"

    async def test_add_duplicate(self):
        """Adding an existing topic name shows error."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["topic", "add", "TestTopic"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "already exists" in text

    async def test_remove_missing_name(self):
        """'topic remove' without name shows usage."""
        ctx = MockTransport(args=["topic", "remove"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_remove_success(self):
        """'topic remove TestTopic' deletes existing topic."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["topic", "remove", "TestTopic"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Deleted" in text
        assert "TestTopic" in text

    async def test_remove_not_found(self):
        """Removing non-existent topic shows not found."""
        ctx = MockTransport(args=["topic", "remove", "Ghost"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_unknown_action(self):
        """Unknown topic action shows usage."""
        ctx = MockTransport(args=["topic", "foo"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text


# ------------------------------------------------------------------
# TestHandleEntity
# ------------------------------------------------------------------

class TestHandleEntity:
    """Tests for _handle_entity."""

    async def test_list_empty(self):
        """No entities shows empty message."""
        ctx = MockTransport(args=["entity", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No entities" in text

    async def test_list_with_entities(self):
        """Entities exist shows name, type, url."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["entity", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestEntity" in text
        assert "company" in text
        assert "https://test.com" in text

    async def test_list_with_topic_filter(self):
        """Filter entities by topic name."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["entity", "list", "TestTopic"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestEntity" in text

    async def test_list_topic_not_found(self):
        """Filter by non-existent topic shows not found."""
        ctx = MockTransport(args=["entity", "list", "Ghost"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_add_missing_args(self):
        """'entity add' with too few args shows usage."""
        ctx = MockTransport(args=["entity", "add"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_add_success(self):
        """'entity add' creates entity linked to topic."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["entity", "add", "TestTopic", "NewEnt",
                  "https://new.com"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "NewEnt" in text
        assert "added" in text

    async def test_add_with_custom_type(self):
        """'entity add' with explicit type param."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["entity", "add", "TestTopic", "PersonEnt",
                  "https://person.com", "person"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "PersonEnt" in text
        assert "added" in text
        async with get_session() as s:
            repo = Repository(s)
            entity = await repo.get_monitor_entity("PersonEnt")
            assert entity is not None
            assert entity.entity_type == "person"

    async def test_add_invalid_type(self):
        """Invalid entity type shows error."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["entity", "add", "TestTopic", "BadEnt",
                  "https://bad.com", "spaceship"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Invalid type" in text

    async def test_add_topic_not_found(self):
        """Adding entity to non-existent topic shows not found."""
        ctx = MockTransport(
            args=["entity", "add", "Ghost", "Ent",
                  "https://ghost.com"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_add_duplicate(self):
        """Adding entity with existing name shows error."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["entity", "add", "TestTopic", "TestEntity",
                  "https://dup.com"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "already exists" in text

    async def test_remove_success(self):
        """'entity remove TestEntity' deletes it."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["entity", "remove", "TestEntity"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Deleted" in text
        assert "TestEntity" in text

    async def test_remove_not_found(self):
        """Removing non-existent entity shows not found."""
        ctx = MockTransport(args=["entity", "remove", "Ghost"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_unknown_action(self):
        """Unknown entity action shows usage."""
        ctx = MockTransport(args=["entity", "foo"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text


# ------------------------------------------------------------------
# TestHandleResource
# ------------------------------------------------------------------

class TestHandleResource:
    """Tests for _handle_resource."""

    async def test_list_empty(self):
        """No resources shows empty message."""
        ctx = MockTransport(args=["resource", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No resources" in text

    async def test_list_with_resources(self):
        """Resources exist shows id, name, type, url, last checked."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(args=["resource", "list"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestBlog" in text
        assert "blog" in text
        assert "https://test.com/blog" in text
        assert "never" in text  # last_checked_at is None

    async def test_list_with_entity_filter(self):
        """Filter resources by entity name."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["resource", "list", "TestEntity"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestBlog" in text

    async def test_list_entity_not_found(self):
        """Filter by non-existent entity shows not found."""
        ctx = MockTransport(args=["resource", "list", "Ghost"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_add_missing_args(self):
        """'resource add' with too few args shows usage."""
        ctx = MockTransport(args=["resource", "add"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_add_success(self):
        """'resource add' creates resource linked to entity."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["resource", "add", "TestEntity",
                  "https://test.com/pricing", "pricing"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "TestEntity pricing" in text  # default name
        assert "added" in text

    async def test_add_with_custom_name(self):
        """'resource add' with explicit name param."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["resource", "add", "TestEntity",
                  "https://test.com/repo", "repo", "My", "Repo"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "My Repo" in text
        assert "added" in text

    async def test_add_invalid_type(self):
        """Invalid resource type shows error."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["resource", "add", "TestEntity",
                  "https://test.com/x", "spaceship"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Invalid type" in text

    async def test_add_entity_not_found(self):
        """Adding resource to non-existent entity shows not found."""
        ctx = MockTransport(
            args=["resource", "add", "Ghost",
                  "https://ghost.com/blog", "blog"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_remove_missing_id(self):
        """'resource remove' without ID shows usage."""
        ctx = MockTransport(args=["resource", "remove"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_remove_invalid_id(self):
        """Non-numeric resource ID shows error."""
        ctx = MockTransport(args=["resource", "remove", "abc"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "must be a number" in text

    async def test_remove_success(self):
        """'resource remove <id>' deletes existing resource."""
        topic, entity, resource = await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["resource", "remove", str(resource.id)],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Deleted" in text

    async def test_remove_not_found(self):
        """Removing non-existent resource ID shows not found."""
        ctx = MockTransport(args=["resource", "remove", "9999"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_unknown_action(self):
        """Unknown resource action shows usage."""
        ctx = MockTransport(args=["resource", "foo"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text


# ------------------------------------------------------------------
# TestHandleSubscribe
# ------------------------------------------------------------------

class TestHandleSubscribe:
    """Tests for _handle_subscribe."""

    async def test_missing_args(self):
        """Too few args shows usage."""
        ctx = MockTransport(args=["subscribe"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Usage:" in text

    async def test_invalid_channel(self):
        """Invalid channel type shows error."""
        ctx = MockTransport(
            args=["subscribe", "TestTopic", "email"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "telegram" in text.lower() or "slack" in text.lower()

    async def test_telegram_to_topic(self):
        """Subscribe to topic via telegram."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["subscribe", "TestTopic", "telegram"],
            chat_id=42,
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Subscribed" in text
        assert "TestTopic" in text
        assert "telegram" in text

    async def test_slack_missing_webhook(self):
        """Slack without webhook URL shows error."""
        ctx = MockTransport(
            args=["subscribe", "TestTopic", "slack"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "webhook" in text.lower()

    async def test_slack_to_topic(self):
        """Subscribe to topic via slack with webhook."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["subscribe", "TestTopic", "slack",
                  "https://hooks.slack.com/xxx"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Subscribed" in text
        assert "TestTopic" in text
        assert "slack" in text

    async def test_target_not_found(self):
        """Subscribing to non-existent target shows not found."""
        ctx = MockTransport(
            args=["subscribe", "Ghost", "telegram"],
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text

    async def test_subscribe_to_entity(self):
        """Subscribe to entity (not topic) via telegram."""
        await _seed_topic_entity_resource()
        ctx = MockTransport(
            args=["subscribe", "TestEntity", "telegram"],
            chat_id=42,
        )
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Subscribed" in text
        assert "TestEntity" in text


# ------------------------------------------------------------------
# TestHandleCheck
# ------------------------------------------------------------------

class TestHandleCheck:
    """Tests for _handle_check."""

    @patch("megobari.monitor.notify_subscribers", new_callable=AsyncMock)
    @patch(
        "megobari.monitor._format_digest_message",
        return_value="No changes detected.",
    )
    @patch("megobari.monitor.run_monitor_check", new_callable=AsyncMock)
    async def test_check_no_args(self, mock_check, _fmt, _notify):
        """Check with no args calls run_monitor_check with None."""
        mock_check.return_value = []
        ctx = MockTransport(args=["check"])
        await cmd_monitor(ctx)
        mock_check.assert_awaited_once_with(
            topic_name=None, entity_name=None,
        )
        # First reply is the "Running..." message
        assert ctx.reply.call_count == 2

    @patch("megobari.monitor.notify_subscribers", new_callable=AsyncMock)
    @patch("megobari.monitor._format_digest_message")
    @patch("megobari.monitor.run_monitor_check", new_callable=AsyncMock)
    async def test_check_with_topic(self, mock_check, mock_fmt, mock_notify):
        """Check with topic name passes it through."""
        digests = [{"change_type": "new_post", "summary": "New blog post"}]
        mock_check.return_value = digests
        mock_fmt.return_value = "1 change(s) found"
        ctx = MockTransport(args=["check", "MyTopic"])
        await cmd_monitor(ctx)
        mock_check.assert_awaited_once_with(
            topic_name="MyTopic", entity_name=None,
        )
        mock_notify.assert_awaited_once()

    @patch("megobari.monitor.notify_subscribers", new_callable=AsyncMock)
    @patch(
        "megobari.monitor._format_digest_message",
        return_value="No changes.",
    )
    @patch("megobari.monitor.run_monitor_check", new_callable=AsyncMock)
    async def test_check_error(self, mock_check, _fmt, _notify):
        """Exception during check shows error message."""
        mock_check.side_effect = RuntimeError("boom")
        ctx = MockTransport(args=["check"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert "failed" in last_text.lower()


# ------------------------------------------------------------------
# TestHandleBaseline
# ------------------------------------------------------------------

class TestHandleBaseline:
    """Tests for _handle_baseline."""

    @patch(
        "megobari.monitor.generate_baseline_digests",
        new_callable=AsyncMock,
    )
    async def test_baseline_no_digests(self, mock_baseline):
        """Empty baseline returns 'No new baseline digests'."""
        mock_baseline.return_value = []
        ctx = MockTransport(args=["baseline"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert "No new baseline" in last_text

    @patch(
        "megobari.monitor.generate_baseline_digests",
        new_callable=AsyncMock,
    )
    async def test_baseline_with_digests(self, mock_baseline):
        """Baseline with digests shows grouped by entity."""
        mock_baseline.return_value = [
            {
                "entity_name": "Acme",
                "resource_name": "Blog",
                "summary": "Initial blog content",
            },
            {
                "entity_name": "Acme",
                "resource_name": "Pricing",
                "summary": "Current pricing page",
            },
        ]
        ctx = MockTransport(args=["baseline"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert "Baseline Digests" in last_text
        assert "2 summaries" in last_text
        assert "Acme" in last_text
        assert "Blog" in last_text
        assert "Pricing" in last_text

    @patch(
        "megobari.monitor.generate_baseline_digests",
        new_callable=AsyncMock,
    )
    async def test_baseline_error(self, mock_baseline):
        """Exception during baseline shows error message."""
        mock_baseline.side_effect = RuntimeError("boom")
        ctx = MockTransport(args=["baseline"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert "failed" in last_text.lower()


# ------------------------------------------------------------------
# TestHandleReport
# ------------------------------------------------------------------

class TestHandleReport:
    """Tests for _handle_report."""

    @patch("megobari.monitor.generate_report", new_callable=AsyncMock)
    async def test_report_short(self, mock_report):
        """Short report is sent in full."""
        mock_report.return_value = "Short market report."
        ctx = MockTransport(args=["report"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert "Short market report." == last_text

    @patch("megobari.monitor.generate_report", new_callable=AsyncMock)
    async def test_report_long(self, mock_report):
        """Report >3500 chars is truncated with dashboard note."""
        long_text = "A" * 4000
        mock_report.return_value = long_text
        ctx = MockTransport(args=["report"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert len(last_text) < 4000
        assert "dashboard" in last_text

    @patch("megobari.monitor.generate_report", new_callable=AsyncMock)
    async def test_report_error(self, mock_report):
        """Exception during report shows error message."""
        mock_report.side_effect = RuntimeError("boom")
        ctx = MockTransport(args=["report"])
        await cmd_monitor(ctx)
        last_text = ctx.reply.call_args[0][0]
        assert "failed" in last_text.lower()


# ------------------------------------------------------------------
# TestHandleDigest
# ------------------------------------------------------------------

class TestHandleDigest:
    """Tests for _handle_digest."""

    async def test_no_digests(self):
        """No digests shows 'No digests found'."""
        ctx = MockTransport(args=["digest"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "No digests" in text

    @patch("megobari.monitor._CHANGE_ICONS", {"new_post": "\U0001f4dd"})
    async def test_with_digests(self):
        """Digests in DB are formatted with icon, timestamp, type, summary."""
        topic, entity, resource = await _seed_topic_entity_resource()
        async with get_session() as s:
            repo = Repository(s)
            snapshot = await repo.add_monitor_snapshot(
                topic_id=topic.id, entity_id=entity.id,
                resource_id=resource.id,
                content_hash="abc123",
                content_markdown="# Hello",
            )
            await repo.add_monitor_digest(
                topic_id=topic.id, entity_id=entity.id,
                resource_id=resource.id, snapshot_id=snapshot.id,
                summary="New blog post published",
                change_type="new_post",
            )
        ctx = MockTransport(args=["digest"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Recent Digests" in text
        assert "new_post" in text
        assert "New blog post published" in text

    @patch("megobari.monitor._CHANGE_ICONS", {"new_post": "\U0001f4dd"})
    async def test_filter_by_topic(self):
        """Filter digests by topic name."""
        topic, entity, resource = await _seed_topic_entity_resource()
        async with get_session() as s:
            repo = Repository(s)
            snapshot = await repo.add_monitor_snapshot(
                topic_id=topic.id, entity_id=entity.id,
                resource_id=resource.id,
                content_hash="abc123",
                content_markdown="# Hello",
            )
            await repo.add_monitor_digest(
                topic_id=topic.id, entity_id=entity.id,
                resource_id=resource.id, snapshot_id=snapshot.id,
                summary="Filtered digest",
                change_type="new_post",
            )
        ctx = MockTransport(args=["digest", "TestTopic"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "Filtered digest" in text

    async def test_filter_not_found(self):
        """Filter by non-existent topic/entity shows not found."""
        ctx = MockTransport(args=["digest", "Ghost"])
        await cmd_monitor(ctx)
        text = ctx.reply.call_args[0][0]
        assert "not found" in text
