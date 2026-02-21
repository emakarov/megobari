"""Tests for Telegram bot command handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from megobari.session import SessionManager


def _make_context(session_manager: SessionManager, args: list[str] | None = None):
    """Create a mock telegram context with session_manager in bot_data."""
    ctx = MagicMock()
    ctx.bot_data = {"session_manager": session_manager}
    ctx.args = args or []
    ctx.bot = AsyncMock()
    return ctx


def _make_update():
    """Create a mock telegram Update with reply_text."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = "hello"
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"
    return update


class TestCmdStart:
    async def test_creates_default_session(self, session_manager):
        from megobari.bot import cmd_start

        update = _make_update()
        ctx = _make_context(session_manager)

        await cmd_start(update, ctx)

        assert session_manager.get("default") is not None
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Megobari is ready" in text

    async def test_does_not_recreate_default(self, session_manager):
        from megobari.bot import cmd_start

        session_manager.create("existing")
        update = _make_update()
        ctx = _make_context(session_manager)

        await cmd_start(update, ctx)

        assert session_manager.get("default") is None
        assert len(session_manager.list_all()) == 1


class TestCmdNew:
    async def test_creates_session(self, session_manager):
        from megobari.bot import cmd_new

        update = _make_update()
        ctx = _make_context(session_manager, args=["mysession"])

        await cmd_new(update, ctx)

        assert session_manager.get("mysession") is not None
        text = update.message.reply_text.call_args[0][0]
        assert "mysession" in text

    async def test_no_args(self, session_manager):
        from megobari.bot import cmd_new

        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_new(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_duplicate(self, session_manager):
        from megobari.bot import cmd_new

        session_manager.create("dup")
        update = _make_update()
        ctx = _make_context(session_manager, args=["dup"])

        await cmd_new(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "already exists" in text


class TestCmdSwitch:
    async def test_switch(self, session_manager):
        from megobari.bot import cmd_switch

        session_manager.create("a")
        session_manager.create("b")
        update = _make_update()
        ctx = _make_context(session_manager, args=["a"])

        await cmd_switch(update, ctx)

        assert session_manager.active_name == "a"

    async def test_not_found(self, session_manager):
        from megobari.bot import cmd_switch

        update = _make_update()
        ctx = _make_context(session_manager, args=["nope"])

        await cmd_switch(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_no_args(self, session_manager):
        from megobari.bot import cmd_switch

        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_switch(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


class TestCmdDelete:
    async def test_delete(self, session_manager):
        from megobari.bot import cmd_delete

        session_manager.create("a")
        session_manager.create("b")
        update = _make_update()
        ctx = _make_context(session_manager, args=["a"])

        await cmd_delete(update, ctx)

        assert session_manager.get("a") is None
        text = update.message.reply_text.call_args[0][0]
        assert "Deleted" in text

    async def test_delete_last(self, session_manager):
        from megobari.bot import cmd_delete

        session_manager.create("only")
        update = _make_update()
        ctx = _make_context(session_manager, args=["only"])

        await cmd_delete(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No sessions left" in text

    async def test_not_found(self, session_manager):
        from megobari.bot import cmd_delete

        update = _make_update()
        ctx = _make_context(session_manager, args=["nope"])

        await cmd_delete(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text


class TestCmdSessions:
    async def test_list(self, session_manager):
        from megobari.bot import cmd_sessions

        session_manager.create("a")
        session_manager.create("b")
        update = _make_update()
        ctx = _make_context(session_manager)

        await cmd_sessions(update, ctx)

        update.message.reply_text.assert_called_once()


class TestCmdStream:
    async def test_enable(self, session_manager):
        from megobari.bot import cmd_stream

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["on"])

        await cmd_stream(update, ctx)

        assert session_manager.get("s").streaming is True

    async def test_disable(self, session_manager):
        from megobari.bot import cmd_stream

        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        ctx = _make_context(session_manager, args=["off"])

        await cmd_stream(update, ctx)

        assert session_manager.get("s").streaming is False

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_stream

        update = _make_update()
        ctx = _make_context(session_manager, args=["on"])

        await cmd_stream(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_bad_arg(self, session_manager):
        from megobari.bot import cmd_stream

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["maybe"])

        await cmd_stream(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


class TestCmdPermissions:
    async def test_set_mode(self, session_manager):
        from megobari.bot import cmd_permissions

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["acceptEdits"])

        await cmd_permissions(update, ctx)

        assert session_manager.get("s").permission_mode == "acceptEdits"

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_permissions

        update = _make_update()
        ctx = _make_context(session_manager, args=["default"])

        await cmd_permissions(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_invalid_mode(self, session_manager):
        from megobari.bot import cmd_permissions

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["yolo"])

        await cmd_permissions(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


class TestCmdCd:
    async def test_change_dir(self, session_manager, tmp_path):
        from megobari.bot import cmd_cd

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=[str(tmp_path)])

        await cmd_cd(update, ctx)

        assert session_manager.get("s").cwd == str(tmp_path)

    async def test_no_args_shows_current(self, session_manager):
        from megobari.bot import cmd_cd

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_cd(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Current directory" in text

    async def test_nonexistent_dir(self, session_manager):
        from megobari.bot import cmd_cd

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["/nonexistent/path/xyz"])

        await cmd_cd(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_cd

        update = _make_update()
        ctx = _make_context(session_manager, args=["/tmp"])

        await cmd_cd(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text


class TestCmdDirs:
    async def test_list_empty(self, session_manager):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_dirs(update, ctx)

        update.message.reply_text.assert_called_once()

    async def test_add_dir(self, session_manager, tmp_path):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["add", str(tmp_path)])

        await cmd_dirs(update, ctx)

        assert str(tmp_path) in session_manager.get("s").dirs

    async def test_add_nonexistent(self, session_manager):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["add", "/no/such/dir/xyz"])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_add_duplicate(self, session_manager, tmp_path):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        session_manager.get("s").dirs.append(str(tmp_path))
        update = _make_update()
        ctx = _make_context(session_manager, args=["add", str(tmp_path)])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Already added" in text

    async def test_rm_dir(self, session_manager, tmp_path):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        resolved = str(Path(tmp_path).resolve())
        session_manager.get("s").dirs.append(resolved)
        update = _make_update()
        ctx = _make_context(session_manager, args=["rm", str(tmp_path)])

        await cmd_dirs(update, ctx)

        assert resolved not in session_manager.get("s").dirs

    async def test_rm_not_in_list(self, session_manager, tmp_path):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["rm", str(tmp_path)])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Not in directory list" in text

    async def test_bad_action(self, session_manager):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["wat"])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_dirs

        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_add_no_path(self, session_manager):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["add"])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_rm_no_path(self, session_manager):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["rm"])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


class TestCmdRename:
    async def test_rename(self, session_manager):
        from megobari.bot import cmd_rename

        session_manager.create("old")
        update = _make_update()
        ctx = _make_context(session_manager, args=["old", "new"])

        await cmd_rename(update, ctx)

        assert session_manager.get("old") is None
        assert session_manager.get("new") is not None

    async def test_no_args(self, session_manager):
        from megobari.bot import cmd_rename

        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_rename(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_error(self, session_manager):
        from megobari.bot import cmd_rename

        update = _make_update()
        ctx = _make_context(session_manager, args=["nope", "new"])

        await cmd_rename(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text


class TestCmdHelp:
    async def test_help(self, session_manager):
        from megobari.bot import cmd_help

        update = _make_update()
        ctx = _make_context(session_manager)

        await cmd_help(update, ctx)

        update.message.reply_text.assert_called_once()


class TestCmdCurrent:
    async def test_current(self, session_manager):
        from megobari.bot import cmd_current

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)

        await cmd_current(update, ctx)

        update.message.reply_text.assert_called_once()

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_current

        update = _make_update()
        ctx = _make_context(session_manager)

        await cmd_current(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text


class TestHandleMessage:
    async def test_no_session(self, session_manager):
        from megobari.bot import handle_message

        update = _make_update()
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    @patch("megobari.bot.send_to_claude")
    async def test_basic_response(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.return_value = ("Hello!", [], "sid-123")
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        mock_send.assert_called_once()
        # Should have replied (reply_text called at least once)
        assert update.message.reply_text.call_count >= 1

    @patch("megobari.bot.send_to_claude")
    async def test_with_tool_uses(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.return_value = (
            "Done!",
            [("Bash", {"command": "ls"})],
            "sid-123",
        )
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        # Should have sent at least one reply with formatted tool summary
        assert update.message.reply_text.call_count >= 1

    @patch("megobari.bot.send_to_claude")
    async def test_updates_session_id(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.return_value = ("Hello!", [], "new-sid")
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        assert session_manager.get("s").session_id == "new-sid"

    @patch("megobari.bot.send_to_claude")
    async def test_error_handling(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.side_effect = RuntimeError("boom")
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Something went wrong" in text


class TestStreamingAccumulator:
    async def test_basic_flow(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        assert acc.message is not None

        await acc.on_chunk("hello ")
        await acc.on_chunk("world")
        result = await acc.finalize()

        assert result == "hello world"

    async def test_long_text_deletes_message(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Add text beyond 4096 limit
        await acc.on_chunk("x" * 5000)
        result = await acc.finalize()

        assert len(result) == 5000
        msg.delete.assert_called_once()
