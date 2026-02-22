"""Tests for the megobari action protocol."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from megobari.actions import execute_actions, parse_actions

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

        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "send_file", "path": str(f)}],
            bot,
            chat_id=123,
        )
        assert errors == []
        bot.send_document.assert_called_once()
        call_kwargs = bot.send_document.call_args[1]
        assert call_kwargs["chat_id"] == 123
        assert call_kwargs["filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_send_file_with_caption(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"data")

        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "send_file", "path": str(f), "caption": "My report"}],
            bot,
            chat_id=123,
        )
        assert errors == []
        call_kwargs = bot.send_document.call_args[1]
        assert call_kwargs["caption"] == "My report"

    @pytest.mark.asyncio
    async def test_send_file_not_found(self):
        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "send_file", "path": "/nonexistent/file.pdf"}],
            bot,
            chat_id=123,
        )
        assert len(errors) == 1
        assert "not found" in errors[0]
        bot.send_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_file_missing_path(self):
        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "send_file"}],
            bot,
            chat_id=123,
        )
        assert len(errors) == 1
        assert "missing" in errors[0]

    @pytest.mark.asyncio
    async def test_send_file_exception(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"data")

        bot = AsyncMock()
        bot.send_document.side_effect = Exception("Telegram error")
        errors = await execute_actions(
            [{"action": "send_file", "path": str(f)}],
            bot,
            chat_id=123,
        )
        assert len(errors) == 1
        assert "failed" in errors[0]

    @pytest.mark.asyncio
    async def test_unknown_action_ignored(self):
        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "unknown_thing", "data": "x"}],
            bot,
            chat_id=123,
        )
        assert errors == []

    @pytest.mark.asyncio
    async def test_multiple_actions(self, tmp_path):
        f1 = tmp_path / "a.pdf"
        f1.write_bytes(b"a")
        f2 = tmp_path / "b.pdf"
        f2.write_bytes(b"b")

        bot = AsyncMock()
        errors = await execute_actions(
            [
                {"action": "send_file", "path": str(f1)},
                {"action": "send_file", "path": str(f2)},
            ],
            bot,
            chat_id=123,
        )
        assert errors == []
        assert bot.send_document.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_actions(self):
        bot = AsyncMock()
        errors = await execute_actions([], bot, chat_id=123)
        assert errors == []

    @pytest.mark.asyncio
    async def test_tilde_expansion(self, tmp_path, monkeypatch):
        f = tmp_path / "home_file.txt"
        f.write_bytes(b"data")

        # Patch expanduser to resolve ~ to tmp_path
        monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path / self.name)
        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "send_file", "path": "~/home_file.txt"}],
            bot,
            chat_id=123,
        )
        assert errors == []
        bot.send_document.assert_called_once()


class TestRestartAction:
    @pytest.mark.asyncio
    @patch("megobari.actions._do_restart")
    async def test_restart_sends_message_and_restarts(self, mock_restart, tmp_path):
        import megobari.actions as actions_mod

        actions_mod._RESTART_MARKER = tmp_path / "restart_notify.json"
        bot = AsyncMock()
        errors = await execute_actions(
            [{"action": "restart"}],
            bot,
            chat_id=123,
        )
        assert errors == []
        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 123
        assert "Restarting" in call_kwargs["text"]
        mock_restart.assert_called_once()

    @pytest.mark.asyncio
    @patch("megobari.actions._do_restart")
    async def test_restart_continues_on_message_failure(self, mock_restart, tmp_path):
        import megobari.actions as actions_mod

        actions_mod._RESTART_MARKER = tmp_path / "restart_notify.json"
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("network error")
        errors = await execute_actions(
            [{"action": "restart"}],
            bot,
            chat_id=123,
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
        bot = AsyncMock()
        await execute_actions(
            [{"action": "restart"}],
            bot,
            chat_id=42,
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


class TestDoRestart:
    @patch("megobari.actions.os.execv")
    def test_calls_execv(self, mock_execv):
        import sys

        from megobari.actions import _do_restart

        _do_restart()
        mock_execv.assert_called_once_with(
            sys.executable, [sys.executable] + sys.argv
        )
