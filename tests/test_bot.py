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

    async def test_no_args(self, session_manager):
        from megobari.bot import cmd_delete

        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_delete(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


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
        text = update.message.reply_text.call_args[0][0]
        assert "No extra directories" in text

    async def test_list_with_dirs(self, session_manager, tmp_path):
        from megobari.bot import cmd_dirs

        session_manager.create("s")
        session_manager.get("s").dirs.append(str(tmp_path))
        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_dirs(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert str(tmp_path) in text
        assert "Directories" in text

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


class TestCmdFile:
    async def test_send_file(self, session_manager, tmp_path):
        from megobari.bot import cmd_file

        session_manager.create("s")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        update = _make_update()
        update.message.reply_document = AsyncMock()
        ctx = _make_context(session_manager, args=[str(f)])

        await cmd_file(update, ctx)

        update.message.reply_document.assert_called_once()
        call_kwargs = update.message.reply_document.call_args[1]
        assert call_kwargs["filename"] == "test.txt"

    async def test_no_args(self, session_manager):
        from megobari.bot import cmd_file

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=[])

        await cmd_file(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_file_not_found(self, session_manager):
        from megobari.bot import cmd_file

        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["/nonexistent/file.txt"])

        await cmd_file(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not found" in text

    async def test_relative_path_resolved_from_cwd(self, session_manager, tmp_path):
        from megobari.bot import cmd_file

        session_manager.create("s")
        session_manager.get("s").cwd = str(tmp_path)
        f = tmp_path / "data.pdf"
        f.write_text("pdf content")
        update = _make_update()
        update.message.reply_document = AsyncMock()
        ctx = _make_context(session_manager, args=["data.pdf"])

        await cmd_file(update, ctx)

        update.message.reply_document.assert_called_once()

    async def test_send_failure(self, session_manager, tmp_path):
        from megobari.bot import cmd_file

        session_manager.create("s")
        f = tmp_path / "fail.txt"
        f.write_text("data")
        update = _make_update()
        update.message.reply_document = AsyncMock(
            side_effect=Exception("too large")
        )
        ctx = _make_context(session_manager, args=[str(f)])

        await cmd_file(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Failed to send" in text


class TestCmdRestart:
    @patch("megobari.actions._do_restart")
    async def test_restart_sends_message_and_restarts(self, mock_restart, tmp_path):
        import megobari.actions as actions_mod
        from megobari.bot import cmd_restart

        actions_mod._RESTART_MARKER = tmp_path / "restart_notify.json"
        update = _make_update()
        ctx = _make_context(MagicMock())

        await cmd_restart(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Restarting" in text
        mock_restart.assert_called_once()
        # Should have saved restart marker
        assert (tmp_path / "restart_notify.json").exists()


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


class TestSetReaction:
    async def test_set_reaction(self):
        from megobari.bot import _set_reaction

        bot = AsyncMock()
        await _set_reaction(bot, 123, 456, "\U0001f440")

        bot.set_message_reaction.assert_called_once_with(
            chat_id=123, message_id=456, reaction="\U0001f440",
        )

    async def test_remove_reaction(self):
        from megobari.bot import _set_reaction

        bot = AsyncMock()
        await _set_reaction(bot, 123, 456, None)

        bot.set_message_reaction.assert_called_once_with(
            chat_id=123, message_id=456, reaction=None,
        )

    async def test_failure_ignored(self):
        from megobari.bot import _set_reaction

        bot = AsyncMock()
        bot.set_message_reaction.side_effect = Exception("not supported")

        # Should not raise
        await _set_reaction(bot, 123, 456, "\U0001f440")


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
        update.message.message_id = 99
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        mock_send.assert_called_once()
        # Should have replied (reply_text called at least once)
        assert update.message.reply_text.call_count >= 1
        # Reaction should have been set and cleared
        calls = ctx.bot.set_message_reaction.call_args_list
        assert len(calls) >= 2
        assert calls[0][1]["reaction"] == "\U0001f440"
        assert calls[-1][1]["reaction"] is None

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
        update.message.message_id = 99
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
        update.message.message_id = 99
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        assert session_manager.get("s").session_id == "new-sid"

    @patch("megobari.bot.send_to_claude")
    async def test_error_handling(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.side_effect = RuntimeError("boom")
        session_manager.create("s")
        update = _make_update()
        update.message.message_id = 99
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Something went wrong" in text
        # Reaction should still be cleared in finally
        last_reaction = ctx.bot.set_message_reaction.call_args_list[-1]
        assert last_reaction[1]["reaction"] is None

    @patch("megobari.bot.send_to_claude")
    async def test_non_streaming_tool_status_message(self, mock_send, session_manager):
        from megobari.bot import handle_message

        async def fake_send(prompt, session, on_text_chunk=None, on_tool_use=None):
            if on_tool_use:
                await on_tool_use("Read", {"file_path": "/a/b/foo.py"})
                await on_tool_use("Bash", {"command": "ls"})
            return ("Done!", [("Read", {"file_path": "/a/b/foo.py"})], "sid")

        mock_send.side_effect = fake_send
        session_manager.create("s")
        update = _make_update()
        update.message.message_id = 99
        status_msg = AsyncMock()
        # First reply_text call returns the status message
        update.message.reply_text.side_effect = [status_msg, AsyncMock()]
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        # Status message should have been created and then deleted
        status_msg.delete.assert_called_once()


class TestHandleMessageStreaming:
    @patch("megobari.bot.send_to_claude")
    async def test_streaming_basic(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.return_value = ("Streamed!", [], "sid-s")
        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        update.message.message_id = 99
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        mock_send.assert_called_once()
        # on_text_chunk and on_tool_use callbacks should have been passed
        call_kwargs = mock_send.call_args[1]
        assert "on_text_chunk" in call_kwargs
        assert "on_tool_use" in call_kwargs

    @patch("megobari.bot.send_to_claude")
    async def test_streaming_with_tools(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.return_value = (
            "Done!",
            [("Bash", {"command": "ls"})],
            "sid-s",
        )
        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        update.message.message_id = 99
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        # Tool summary should be sent
        calls = update.message.reply_text.call_args_list
        any_tool_call = any("\u26a1" in str(c) for c in calls)
        assert any_tool_call

    @patch("megobari.bot.send_to_claude")
    async def test_streaming_long_text_splits(self, mock_send, session_manager):
        from megobari.bot import handle_message

        long_text = "word " * 2000  # well beyond 4096

        async def fake_send(prompt, session, on_text_chunk=None, on_tool_use=None):
            if on_text_chunk:
                await on_text_chunk(long_text)
            return (long_text, [], "sid-s")

        mock_send.side_effect = fake_send
        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        update.message.message_id = 99
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        # initialize() + split chunks = at least 2 calls
        # (delete of original msg + split messages)
        assert update.message.reply_text.call_count >= 2

    @patch("megobari.bot.send_to_claude")
    async def test_streaming_no_session_id_update(self, mock_send, session_manager):
        from megobari.bot import handle_message

        mock_send.return_value = ("ok", [], None)
        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        update.message.message_id = 99
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        assert session_manager.get("s").session_id is None

    @patch("megobari.bot.send_to_claude")
    @patch("megobari.bot.execute_actions", new_callable=AsyncMock)
    async def test_streaming_action_blocks(
        self, mock_exec, mock_send, session_manager
    ):
        from megobari.bot import handle_message

        response_with_action = (
            "Here is the file:\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/test.pdf"}\n'
            "```\n"
            "Enjoy!"
        )

        async def fake_send(prompt, session, on_text_chunk=None, on_tool_use=None):
            if on_text_chunk:
                await on_text_chunk(response_with_action)
            return (response_with_action, [], "sid-s")

        mock_send.side_effect = fake_send
        mock_exec.return_value = []
        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        update.message.message_id = 99
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        # execute_actions should have been called with parsed actions
        mock_exec.assert_called_once()
        actions_arg = mock_exec.call_args[0][0]
        assert len(actions_arg) == 1
        assert actions_arg[0]["action"] == "send_file"

        # Streaming message should be re-edited with cleaned text
        edit_calls = msg.edit_text.call_args_list
        last_edit = edit_calls[-1][0][0]
        assert "```megobari" not in last_edit

    @patch("megobari.bot.send_to_claude")
    @patch("megobari.bot.execute_actions", new_callable=AsyncMock)
    async def test_streaming_action_errors_reported(
        self, mock_exec, mock_send, session_manager
    ):
        from megobari.bot import handle_message

        response_with_action = (
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/x.pdf"}\n'
            "```\n"
            "Done."
        )

        async def fake_send(prompt, session, on_text_chunk=None, on_tool_use=None):
            if on_text_chunk:
                await on_text_chunk(response_with_action)
            return (response_with_action, [], "sid-s")

        mock_send.side_effect = fake_send
        mock_exec.return_value = ["send_file: file not found: /tmp/x.pdf"]
        session_manager.create("s")
        session_manager.get("s").streaming = True
        update = _make_update()
        update.message.message_id = 99
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        # Error message should be sent
        reply_calls = update.message.reply_text.call_args_list
        any_error = any("⚠️" in str(c) for c in reply_calls)
        assert any_error


class TestHandleMessageActions:
    """Test action protocol integration in non-streaming handle_message."""

    @patch("megobari.bot.send_to_claude")
    @patch("megobari.bot.execute_actions", new_callable=AsyncMock)
    async def test_non_streaming_action_blocks(
        self, mock_exec, mock_send, session_manager
    ):
        from megobari.bot import handle_message

        response_with_action = (
            "Here is your file:\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/report.pdf"}\n'
            "```\n"
            "Let me know if you need more."
        )
        mock_send.return_value = (response_with_action, [], "sid-123")
        mock_exec.return_value = []
        session_manager.create("s")
        update = _make_update()
        update.message.message_id = 99
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        mock_exec.assert_called_once()
        actions_arg = mock_exec.call_args[0][0]
        assert len(actions_arg) == 1
        assert actions_arg[0]["action"] == "send_file"

        # Response text sent to user should not contain the action block
        reply_text = update.message.reply_text.call_args[0][0]
        assert "```megobari" not in reply_text

    @patch("megobari.bot.send_to_claude")
    @patch("megobari.bot.execute_actions", new_callable=AsyncMock)
    async def test_non_streaming_action_errors(
        self, mock_exec, mock_send, session_manager
    ):
        from megobari.bot import handle_message

        response_with_action = (
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/nope.pdf"}\n'
            "```\n"
            "Here you go."
        )
        mock_send.return_value = (response_with_action, [], "sid-123")
        mock_exec.return_value = ["send_file: file not found: /tmp/nope.pdf"]
        session_manager.create("s")
        update = _make_update()
        update.message.message_id = 99
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        reply_calls = update.message.reply_text.call_args_list
        any_error = any("⚠️" in str(c) for c in reply_calls)
        assert any_error

    @patch("megobari.bot.send_to_claude")
    @patch("megobari.bot.execute_actions", new_callable=AsyncMock)
    async def test_non_streaming_action_with_tools(
        self, mock_exec, mock_send, session_manager
    ):
        from megobari.bot import handle_message

        response_with_action = (
            "Found the file.\n"
            "```megobari\n"
            '{"action": "send_file", "path": "/tmp/data.csv"}\n'
            "```"
        )
        mock_send.return_value = (
            response_with_action,
            [("Read", {"file_path": "/tmp/data.csv"})],
            "sid-123",
        )
        mock_exec.return_value = []
        session_manager.create("s")
        update = _make_update()
        update.message.message_id = 99
        ctx = _make_context(session_manager)

        await handle_message(update, ctx)

        mock_exec.assert_called_once()
        # Tool summary should also be present in formatted reply
        reply_calls = update.message.reply_text.call_args_list
        any_tool = any("✏️" in str(c) for c in reply_calls)
        assert any_tool


class TestSendTypingPeriodically:
    async def test_typing_cancelled(self):
        import asyncio

        from megobari.bot import _send_typing_periodically

        bot = AsyncMock()
        task = asyncio.create_task(_send_typing_periodically(12345, bot))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        bot.send_chat_action.assert_called()


class TestCmdDiscoverId:
    async def test_discover_id(self):
        from megobari.bot import _cmd_discover_id

        update = _make_update()
        ctx = _make_context(MagicMock())

        await _cmd_discover_id(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "12345" in text
        assert "ALLOWED_USER_ID" in text


class TestCreateApplication:
    def test_creates_with_user_id(self, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config

        config = Config(bot_token="fake-token", allowed_user_id=12345)
        app = create_application(session_manager, config)
        assert app is not None
        assert app.bot_data["session_manager"] is session_manager
        # Should have handlers registered
        assert len(app.handlers[0]) > 0

    def test_creates_with_username(self, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config

        config = Config(bot_token="fake-token", allowed_username="testuser")
        app = create_application(session_manager, config)
        assert app is not None
        assert len(app.handlers[0]) > 0

    def test_discovery_mode(self, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config

        config = Config(bot_token="fake-token")
        app = create_application(session_manager, config)
        assert app is not None
        # In discovery mode, should have exactly 1 handler (catch-all)
        assert len(app.handlers[0]) == 1

    def test_post_init_set(self, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config

        config = Config(bot_token="fake-token", allowed_user_id=12345)
        app = create_application(session_manager, config)
        assert app.post_init is not None

    @patch("megobari.actions.load_restart_marker", return_value=12345)
    async def test_post_init_sends_notification(self, mock_load, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config

        config = Config(bot_token="fake-token", allowed_user_id=12345)
        app = create_application(session_manager, config)
        app.bot = AsyncMock()

        await app.post_init(app)

        app.bot.send_message.assert_called_once()
        call_kwargs = app.bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 12345
        assert "restarted" in call_kwargs["text"]

    @patch("megobari.actions.load_restart_marker", return_value=None)
    async def test_post_init_no_marker(self, mock_load, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config

        config = Config(bot_token="fake-token", allowed_user_id=12345)
        app = create_application(session_manager, config)
        app.bot = AsyncMock()

        await app.post_init(app)

        app.bot.send_message.assert_not_called()


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

    async def test_edit_failure_ignored(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        msg.edit_text.side_effect = Exception("edit failed")
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Trigger edit by exceeding threshold
        await acc.on_chunk("x" * 300)
        # Should not raise despite edit failure
        result = await acc.finalize()
        assert len(result) == 300

    async def test_delete_failure_ignored(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        msg.delete.side_effect = Exception("delete failed")
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        await acc.on_chunk("x" * 5000)
        # Should not raise despite delete failure
        result = await acc.finalize()
        assert len(result) == 5000

    async def test_finalize_empty(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Finalize without any chunks
        result = await acc.finalize()
        assert result == ""

    async def test_tool_status_before_text(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Tool use before any text
        await acc.on_tool_use("Read", {"file_path": "/a/b/foo.py"})
        msg.edit_text.assert_called_once()
        status = msg.edit_text.call_args[0][0]
        assert "Reading" in status
        assert "foo.py" in status

    async def test_tool_status_ignored_after_text(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Text arrives first
        await acc.on_chunk("hello")
        msg.edit_text.reset_mock()

        # Tool use after text — should be ignored
        await acc.on_tool_use("Bash", {"command": "ls"})
        msg.edit_text.assert_not_called()

    async def test_tool_status_edit_failure_ignored(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        msg.edit_text.side_effect = Exception("edit failed")
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Should not raise
        await acc.on_tool_use("Grep", {"pattern": "TODO"})

    async def test_threshold_edits(self):
        from megobari.bot import StreamingAccumulator

        update = _make_update()
        msg = AsyncMock()
        update.message.reply_text.return_value = msg
        ctx = _make_context(MagicMock())

        acc = StreamingAccumulator(update, ctx)
        await acc.initialize()

        # Add text in small chunks — no edit until threshold
        await acc.on_chunk("a" * 50)
        msg.edit_text.assert_not_called()

        # Exceed threshold
        await acc.on_chunk("b" * 200)
        msg.edit_text.assert_called_once()
