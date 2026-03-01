"""Tests for the megobari action protocol."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.actions import execute_actions, parse_actions
from megobari.formatting import TelegramFormatter

# -- MockTransport helper --


class MockTransport:
    """Lightweight mock implementing TransportContext interface for tests."""

    def __init__(self, chat_id=123, user_id=42):
        self._chat_id = chat_id
        self._user_id = user_id
        self._formatter = TelegramFormatter()
        self._bot_data = {}

        # Mock all async methods
        self.reply = AsyncMock(return_value=MagicMock())
        self.reply_document = AsyncMock()
        self.reply_photo = AsyncMock()
        self.send_message = AsyncMock()
        self.edit_message = AsyncMock()
        self.delete_message = AsyncMock()
        self.send_typing = AsyncMock()
        self.set_reaction = AsyncMock()

    @property
    def chat_id(self):
        return self._chat_id

    @property
    def user_id(self):
        return self._user_id

    @property
    def bot_data(self):
        return self._bot_data

    @property
    def formatter(self):
        return self._formatter

    @property
    def transport_name(self):
        return "test"

    @property
    def max_message_length(self):
        return 4096


# -- parse_actions tests --


class TestParseActions:
    def test_no_blocks(self):
        text = "Hello, here is some regular text."
        cleaned, actions = parse_actions(text)
        assert cleaned == text
        assert actions == []

    def test_single_block(self):
        text = (
            "Here is a file:\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/test.pdf"}\n'
            "```\n"
            "Enjoy!"
        )
        cleaned, actions = parse_actions(text)
        assert len(actions) == 1
        assert actions[0]["action"] == "send_file"
        assert actions[0]["path"] == "/tmp/test.pdf"
        assert "```megobari" not in cleaned
        assert "Enjoy!" in cleaned

    def test_multiple_blocks(self):
        text = (
            "Two files:\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/a.pdf"}\n'
            "```\n"
            "and\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/b.pdf"}\n'
            "```\n"
            "Done."
        )
        cleaned, actions = parse_actions(text)
        assert len(actions) == 2
        assert actions[0]["path"] == "/tmp/a.pdf"
        assert actions[1]["path"] == "/tmp/b.pdf"
        assert "```megobari" not in cleaned
        assert "Done." in cleaned

    def test_invalid_json_left_in_text(self):
        text = (
            "Bad block:\n"
            "```megobari\n"
            "this is not json\n"
            "```\n"
            "After."
        )
        cleaned, actions = parse_actions(text)
        assert actions == []
        assert "```megobari" in cleaned  # left as-is

    def test_missing_action_key_left_in_text(self):
        text = (
            "```megobari\n"
            '{"path": "/tmp/test.pdf"}\n'
            "```"
        )
        cleaned, actions = parse_actions(text)
        assert actions == []
        assert "```megobari" in cleaned

    def test_block_with_caption(self):
        text = (
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/x.pdf", "caption": "Report"}\n'
            "```"
        )
        cleaned, actions = parse_actions(text)
        assert len(actions) == 1
        assert actions[0]["caption"] == "Report"
        assert cleaned == ""

    def test_block_with_extra_whitespace(self):
        text = (
            "```megobari  \n"
            '  {"action": "send_file", "path": "/tmp/x.pdf"}  \n'
            "  ```"
        )
        cleaned, actions = parse_actions(text)
        assert len(actions) == 1

    def test_mixed_valid_and_invalid(self):
        text = (
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/good.pdf"}\n'
            "```\n"
            "```megobari\n"
            "broken json\n"
            "```\n"
            "End."
        )
        cleaned, actions = parse_actions(text)
        assert len(actions) == 1
        assert actions[0]["path"] == "/tmp/good.pdf"
        # The invalid block stays in the text
        assert "broken json" in cleaned

    def test_empty_text(self):
        cleaned, actions = parse_actions("")
        assert cleaned == ""
        assert actions == []

    def test_cleans_extra_blank_lines(self):
        text = (
            "Before.\n\n\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/x.pdf"}\n'
            "```\n\n\n"
            "After."
        )
        cleaned, actions = parse_actions(text)
        assert len(actions) == 1
        # Should not have 3+ consecutive newlines
        assert "\n\n\n" not in cleaned


# -- execute_actions tests --


class TestExecuteActions:
    @pytest.mark.asyncio
    async def test_send_file_success(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"PDF content")

        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_file", "path": str(f)}],
            ctx,
        )
        assert errors == []
        ctx.reply_document.assert_called_once()
        # reply_document(path, filename, caption=caption)
        call_args = ctx.reply_document.call_args
        assert call_args[0][1] == "test.pdf"  # filename is second positional arg

    @pytest.mark.asyncio
    async def test_send_file_with_caption(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"data")

        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_file", "path": str(f), "caption": "My report"}],
            ctx,
        )
        assert errors == []
        call_kwargs = ctx.reply_document.call_args[1]
        assert call_kwargs["caption"] == "My report"

    @pytest.mark.asyncio
    async def test_send_file_not_found(self):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_file", "path": "/nonexistent/file.pdf"}],
            ctx,
        )
        assert len(errors) == 1
        assert "not found" in errors[0]
        ctx.reply_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_file_missing_path(self):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_file"}],
            ctx,
        )
        assert len(errors) == 1
        assert "missing" in errors[0]

    @pytest.mark.asyncio
    async def test_send_file_exception(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"data")

        ctx = MockTransport()
        ctx.reply_document.side_effect = Exception("Telegram error")
        errors = await execute_actions(
            [{"action": "send_file", "path": str(f)}],
            ctx,
        )
        assert len(errors) == 1
        assert "failed" in errors[0]

    @pytest.mark.asyncio
    async def test_unknown_action_ignored(self):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "unknown_thing", "data": "x"}],
            ctx,
        )
        assert errors == []

    @pytest.mark.asyncio
    async def test_multiple_actions(self, tmp_path):
        f1 = tmp_path / "a.pdf"
        f1.write_bytes(b"a")
        f2 = tmp_path / "b.pdf"
        f2.write_bytes(b"b")

        ctx = MockTransport()
        errors = await execute_actions(
            [
                {"action": "send_file", "path": str(f1)},
                {"action": "send_file", "path": str(f2)},
            ],
            ctx,
        )
        assert errors == []
        assert ctx.reply_document.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_actions(self):
        ctx = MockTransport()
        errors = await execute_actions([], ctx)
        assert errors == []

    @pytest.mark.asyncio
    async def test_tilde_expansion(self, tmp_path, monkeypatch):
        f = tmp_path / "home_file.txt"
        f.write_bytes(b"data")

        # Patch expanduser to resolve ~ to tmp_path
        monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path / self.name)
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_file", "path": "~/home_file.txt"}],
            ctx,
        )
        assert errors == []
        ctx.reply_document.assert_called_once()


class TestRestartAction:
    @pytest.mark.asyncio
    @patch("megobari.actions._do_restart")
    async def test_restart_sends_message_and_restarts(self, mock_restart, tmp_path):
        import megobari.actions as actions_mod

        actions_mod._RESTART_MARKER = tmp_path / "restart_notify.json"
        ctx = MockTransport(chat_id=123)
        errors = await execute_actions(
            [{"action": "restart"}],
            ctx,
        )
        assert errors == []
        ctx.send_message.assert_called_once()
        assert "Restarting" in ctx.send_message.call_args[0][0]
        mock_restart.assert_called_once()

    @pytest.mark.asyncio
    @patch("megobari.actions._do_restart")
    async def test_restart_continues_on_message_failure(self, mock_restart, tmp_path):
        import megobari.actions as actions_mod

        actions_mod._RESTART_MARKER = tmp_path / "restart_notify.json"
        ctx = MockTransport(chat_id=123)
        ctx.send_message.side_effect = Exception("network error")
        errors = await execute_actions(
            [{"action": "restart"}],
            ctx,
        )
        assert errors == []
        mock_restart.assert_called_once()

    @pytest.mark.asyncio
    @patch("megobari.actions._do_restart")
    async def test_restart_saves_marker(self, mock_restart, tmp_path):
        import json

        import megobari.actions as actions_mod

        marker = tmp_path / "restart_notify.json"
        actions_mod._RESTART_MARKER = marker
        ctx = MockTransport(chat_id=42)
        await execute_actions(
            [{"action": "restart"}],
            ctx,
        )
        # Marker should have been written before _do_restart
        assert marker.exists()
        data = json.loads(marker.read_text())
        assert data["chat_id"] == 42


class TestRestartMarker:
    def test_save_and_load(self, tmp_path):
        import megobari.actions as actions_mod

        marker = tmp_path / "restart_notify.json"
        actions_mod._RESTART_MARKER = marker

        actions_mod.save_restart_marker(12345)
        assert marker.exists()

        chat_id = actions_mod.load_restart_marker()
        assert chat_id == 12345
        assert not marker.exists()  # deleted after load

    def test_load_no_marker(self, tmp_path):
        import megobari.actions as actions_mod

        actions_mod._RESTART_MARKER = tmp_path / "nonexistent.json"
        assert actions_mod.load_restart_marker() is None

    def test_load_corrupt_marker(self, tmp_path):
        import megobari.actions as actions_mod

        marker = tmp_path / "restart_notify.json"
        marker.write_text("not json")
        actions_mod._RESTART_MARKER = marker

        assert actions_mod.load_restart_marker() is None
        assert not marker.exists()  # cleaned up


class TestSendPhotoAction:
    @pytest.mark.asyncio
    async def test_send_photo_success(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"PNG data")

        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_photo", "path": str(f)}],
            ctx,
        )
        assert errors == []
        ctx.reply_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_photo_with_caption(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"JPEG data")

        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_photo", "path": str(f), "caption": "Nice pic"}],
            ctx,
        )
        assert errors == []
        call_kwargs = ctx.reply_photo.call_args[1]
        assert call_kwargs["caption"] == "Nice pic"

    @pytest.mark.asyncio
    async def test_send_photo_not_found(self):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_photo", "path": "/nonexistent/image.png"}],
            ctx,
        )
        assert len(errors) == 1
        assert "not found" in errors[0]
        ctx.reply_photo.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_photo_missing_path(self):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "send_photo"}],
            ctx,
        )
        assert len(errors) == 1
        assert "missing" in errors[0]

    @pytest.mark.asyncio
    async def test_send_photo_exception(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"data")

        ctx = MockTransport()
        ctx.reply_photo.side_effect = Exception("Telegram error")
        errors = await execute_actions(
            [{"action": "send_photo", "path": str(f)}],
            ctx,
        )
        assert len(errors) == 1
        assert "failed" in errors[0]


class TestDoRestart:
    @patch("megobari.actions.os.execv")
    def test_calls_execv(self, mock_execv):
        import sys

        from megobari.actions import _do_restart

        _do_restart()
        mock_execv.assert_called_once_with(
            sys.executable, [sys.executable] + sys.argv
        )


# -- Memory action tests (need async DB) --


@pytest.fixture(autouse=False)
async def _init_test_db():
    """Initialize an in-memory DB for memory action tests."""
    from megobari.db import close_db, init_db

    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


class TestMemorySetAction:
    @pytest.mark.asyncio
    async def test_memory_set_success(self, _init_test_db):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "lang", "value": "Georgian"}],
            ctx,
            user_id=42,
        )
        assert errors == []

        # Verify it was saved
        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            mem = await repo.get_memory("prefs", "lang", user_id=42)
            assert mem is not None
            assert mem.content == "Georgian"

    @pytest.mark.asyncio
    async def test_memory_set_missing_fields(self, _init_test_db):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "lang"}],
            ctx,
        )
        assert len(errors) == 1
        assert "requires" in errors[0]

    @pytest.mark.asyncio
    async def test_memory_set_upsert(self, _init_test_db):
        ctx = MockTransport()
        # Set once
        await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "lang", "value": "English"}],
            ctx, user_id=42,
        )
        # Update
        await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "lang", "value": "Georgian"}],
            ctx, user_id=42,
        )

        from megobari.db import Repository, get_session

        async with get_session() as s:
            repo = Repository(s)
            mem = await repo.get_memory("prefs", "lang", user_id=42)
            assert mem.content == "Georgian"


class TestMemoryDeleteAction:
    @pytest.mark.asyncio
    async def test_memory_delete_success(self, _init_test_db):
        ctx = MockTransport()
        # Set first
        await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "lang", "value": "Georgian"}],
            ctx, user_id=42,
        )
        # Delete
        errors = await execute_actions(
            [{"action": "memory_delete", "category": "prefs", "key": "lang"}],
            ctx, user_id=42,
        )
        assert errors == []

    @pytest.mark.asyncio
    async def test_memory_delete_not_found(self, _init_test_db):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "memory_delete", "category": "prefs", "key": "nope"}],
            ctx, user_id=42,
        )
        assert len(errors) == 1
        assert "not found" in errors[0]

    @pytest.mark.asyncio
    async def test_memory_delete_missing_fields(self, _init_test_db):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "memory_delete", "category": "prefs"}],
            ctx,
        )
        assert len(errors) == 1
        assert "requires" in errors[0]


class TestMemoryListAction:
    @pytest.mark.asyncio
    async def test_memory_list_empty(self, _init_test_db):
        ctx = MockTransport()
        errors = await execute_actions(
            [{"action": "memory_list"}],
            ctx, user_id=42,
        )
        assert errors == []
        ctx.send_message.assert_called_once()
        assert "No memories" in ctx.send_message.call_args[0][0]

    @pytest.mark.asyncio
    async def test_memory_list_with_data(self, _init_test_db):
        ctx = MockTransport()
        # Save some memories
        await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "lang", "value": "Georgian"}],
            ctx, user_id=42,
        )
        await execute_actions(
            [{"action": "memory_set", "category": "prefs", "key": "theme", "value": "dark"}],
            ctx, user_id=42,
        )
        ctx.send_message.reset_mock()

        errors = await execute_actions(
            [{"action": "memory_list", "category": "prefs"}],
            ctx, user_id=42,
        )
        assert errors == []
        text = ctx.send_message.call_args[0][0]
        assert "lang" in text
        assert "theme" in text
