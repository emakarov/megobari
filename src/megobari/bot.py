"""Telegram bot handlers and application factory."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from megobari.actions import execute_actions, parse_actions
from megobari.claude_bridge import send_to_claude
from megobari.config import Config
from megobari.formatting import Formatter, TelegramFormatter
from megobari.message_utils import (
    format_help,
    format_session_info,
    format_session_list,
    format_tool_summary,
    split_message,
    tool_status_text,
)
from megobari.session import VALID_PERMISSION_MODES, SessionManager

logger = logging.getLogger(__name__)

# Client-specific formatter — swap this out for other frontends.
fmt: Formatter = TelegramFormatter()


def _get_sm(context: ContextTypes.DEFAULT_TYPE) -> SessionManager:
    return context.bot_data["session_manager"]


def _reply(update: Update, text: str, formatted: bool = False):
    """Helper: reply with or without parse_mode."""
    kwargs = {}
    if formatted:
        kwargs["parse_mode"] = fmt.parse_mode
    return update.message.reply_text(text, **kwargs)


# -- Command handlers --


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    sm = _get_sm(context)
    if not sm.list_all():
        sm.create("default")
    await _reply(
        update,
        "Megobari is ready.\n\n"
        "Send a message to talk to Claude.\n"
        "Use /help to see all commands.",
    )


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new command to create a new session."""
    if not context.args:
        await _reply(update, "Usage: /new <name>")
        return
    name = context.args[0]
    sm = _get_sm(context)
    session = sm.create(name)
    if session is None:
        await _reply(update, f"Session '{name}' already exists.")
        return
    await _reply(update, f"Created and switched to session '{name}'.")


async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sessions command to list all sessions."""
    sm = _get_sm(context)
    text = format_session_list(sm.list_all(), sm.active_name, fmt)
    await _reply(update, text, formatted=True)


async def cmd_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /switch command to switch to a session."""
    if not context.args:
        await _reply(update, "Usage: /switch <name>")
        return
    name = context.args[0]
    sm = _get_sm(context)
    session = sm.switch(name)
    if session is None:
        await _reply(update, f"Session '{name}' not found.")
        return
    await _reply(update, f"Switched to session '{name}'.")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command to delete a session."""
    if not context.args:
        await _reply(update, "Usage: /delete <name>")
        return
    name = context.args[0]
    sm = _get_sm(context)
    if not sm.delete(name):
        await _reply(update, f"Session '{name}' not found.")
        return
    active = sm.active_name
    if active:
        await _reply(update, f"Deleted '{name}'. Active session is now '{active}'.")
    else:
        await _reply(
            update,
            f"Deleted '{name}'. No sessions left. Use /new <name> to create one.",
        )


async def cmd_stream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stream command to enable/disable streaming responses."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    if not context.args or context.args[0] not in ("on", "off"):
        await _reply(
            update,
            f"Usage: /stream on|off\nCurrently: {'on' if session.streaming else 'off'}",
        )
        return
    session.streaming = context.args[0] == "on"
    sm._save()
    await _reply(
        update,
        f"Streaming {'enabled' if session.streaming else 'disabled'} for '{session.name}'.",
    )


async def cmd_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /permissions command to set session permission mode."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    if not context.args or context.args[0] not in VALID_PERMISSION_MODES:
        modes = ", ".join(sorted(VALID_PERMISSION_MODES))
        await _reply(
            update,
            f"Usage: /permissions <mode>\nModes: {modes}\n"
            f"Currently: {session.permission_mode}",
        )
        return
    session.permission_mode = context.args[0]  # type: ignore[assignment]
    sm._save()
    await _reply(
        update,
        f"Permission mode set to '{session.permission_mode}' for '{session.name}'.",
    )


async def cmd_cd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cd command to change the working directory."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    if not context.args:
        await _reply(update, f"Current directory: {session.cwd}\n\nUsage: /cd <path>")
        return
    path = " ".join(context.args)  # support paths with spaces
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        await _reply(update, f"Directory not found: {resolved}")
        return
    session.cwd = str(resolved)
    sm._save()
    await _reply(update, f"Working directory: {session.cwd}")


async def cmd_dirs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /dirs command to manage session directories."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    if not context.args:
        # List directories
        lines = [fmt.bold("Directories:"), ""]
        lines.append(f"▸ {fmt.code(fmt.escape(session.cwd))} (cwd)")
        for d in session.dirs:
            lines.append(f"  {fmt.code(fmt.escape(d))}")
        if not session.dirs:
            lines.append(fmt.italic("No extra directories. Use /dirs add <path>"))
        await _reply(update, "\n".join(lines), formatted=True)
        return

    action = context.args[0]

    if action == "add":
        if len(context.args) < 2:
            await _reply(update, "Usage: /dirs add <path>")
            return
        path = " ".join(context.args[1:])
        resolved = str(Path(path).expanduser().resolve())
        if not Path(resolved).is_dir():
            await _reply(update, f"Directory not found: {resolved}")
            return
        if resolved in session.dirs or resolved == session.cwd:
            await _reply(update, f"Already added: {resolved}")
            return
        session.dirs.append(resolved)
        sm._save()
        await _reply(update, f"Added: {resolved}")

    elif action == "rm":
        if len(context.args) < 2:
            await _reply(update, "Usage: /dirs rm <path>")
            return
        path = " ".join(context.args[1:])
        resolved = str(Path(path).expanduser().resolve())
        if resolved not in session.dirs:
            await _reply(update, f"Not in directory list: {resolved}")
            return
        session.dirs.remove(resolved)
        sm._save()
        await _reply(update, f"Removed: {resolved}")

    else:
        await _reply(update, "Usage: /dirs [add|rm] <path>")


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rename command to rename a session."""
    if not context.args or len(context.args) < 2:
        await _reply(update, "Usage: /rename <old_name> <new_name>")
        return
    old_name, new_name = context.args[0], context.args[1]
    sm = _get_sm(context)
    error = sm.rename(old_name, new_name)
    if error:
        await _reply(update, error)
        return
    await _reply(update, f"Renamed '{old_name}' → '{new_name}'.")


async def cmd_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /file command to send a file to the user."""
    sm = _get_sm(context)
    session = sm.current
    if not context.args:
        await _reply(update, "Usage: /file <path>")
        return
    raw_path = " ".join(context.args)
    resolved = Path(raw_path).expanduser()
    if not resolved.is_absolute() and session:
        resolved = Path(session.cwd) / resolved
    resolved = resolved.resolve()
    if not resolved.is_file():
        await _reply(update, f"File not found: {resolved}")
        return
    try:
        await update.message.reply_document(
            document=open(resolved, "rb"),
            filename=resolved.name,
        )
    except Exception as e:
        await _reply(update, f"Failed to send file: {e}")


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restart command to restart the bot process."""
    from megobari.actions import _do_restart, save_restart_marker

    chat_id = update.effective_chat.id
    save_restart_marker(chat_id)
    await _reply(update, "🔄 Restarting...")
    _do_restart()


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages: transcribe and send to Claude."""
    try:
        from megobari.voice import INSTALL_HINT, get_transcriber, is_available
    except ImportError:
        await _reply(update, "⚠️ Voice support requires faster-whisper.\n"
                     "Install with: pip install megobari[voice]")
        return

    if not is_available():
        await _reply(update, f"⚠️ {INSTALL_HINT}")
        return

    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    config: Config = context.bot_data.get("config")
    model_size = config.whisper_model if config else "small"

    voice = update.message.voice
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    # React with eyes to show we're working
    await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")

    tmp_path = None
    try:
        # Download voice file to temp .ogg
        voice_file = await voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

        # Transcribe (run in thread to avoid blocking the event loop)
        transcriber = get_transcriber(model_size)
        transcription = await asyncio.to_thread(transcriber.transcribe, tmp_path)

        if not transcription.strip():
            await _reply(update, "Could not transcribe voice message.")
            return

        # Show transcription
        await _reply(update, f"\U0001f3a4 {transcription}")

        # Now process as regular text message
        update.message.text = transcription
        await handle_message(update, context)

    except Exception as e:
        logger.exception("Error handling voice message")
        await _reply(update, f"Something went wrong with voice: {e}")
    finally:
        await _set_reaction(context.bot, chat_id, message_id, None)
        # Clean up temp file
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command to display help text."""
    await _reply(update, format_help(fmt), formatted=True)


async def cmd_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /current command to display active session info."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    await _reply(update, format_session_info(session, fmt), formatted=True)


# -- Message handler --


async def _send_typing_periodically(chat_id: int, bot) -> None:
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


class StreamingAccumulator:
    """Accumulates streamed text chunks and edits a single Telegram message."""

    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.accumulated = ""
        self.message = None
        self.last_edit_len = 0
        self.edit_threshold = 200
        self._text_started = False

    async def initialize(self):
        """Send initial placeholder message."""
        self.message = await self.update.message.reply_text("\u2026")

    async def on_tool_use(self, tool_name: str, tool_input: dict) -> None:
        """Update placeholder with tool activity before text starts streaming."""
        if self._text_started or not self.message:
            return
        status = tool_status_text(tool_name, tool_input)
        try:
            await self.message.edit_text(status)
        except Exception:
            pass

    async def on_chunk(self, text: str) -> None:
        """Accumulate text chunk and update message if threshold reached."""
        self._text_started = True
        self.accumulated += text
        if len(self.accumulated) - self.last_edit_len >= self.edit_threshold:
            await self._do_edit()

    async def _do_edit(self) -> None:
        display = self.accumulated[:4096]
        try:
            await self.message.edit_text(display)
            self.last_edit_len = len(self.accumulated)
        except Exception:
            pass  # ignore edit failures (e.g., text unchanged)

    async def finalize(self) -> str:
        """Finalize streaming and return accumulated text."""
        if self.accumulated and self.message:
            if len(self.accumulated) <= 4096:
                await self._do_edit()
            else:
                try:
                    await self.message.delete()
                except Exception:
                    pass
        return self.accumulated


async def _set_reaction(bot, chat_id: int, message_id: int, emoji: str | None) -> None:
    """Set or remove a reaction on a message. Failures are silently ignored."""
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=emoji,
        )
    except Exception:
        pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages and send to Claude."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    user_text = update.message.text
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    logger.info(
        "[%s] User: %s",
        session.name,
        user_text[:200] + ("..." if len(user_text) > 200 else ""),
    )

    # React with eyes to show we're working
    await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")

    # Start typing indicator
    typing_task = asyncio.create_task(
        _send_typing_periodically(chat_id, context.bot)
    )

    try:
        if session.streaming:
            accumulator = StreamingAccumulator(update, context)
            await accumulator.initialize()
            response_text, tool_uses, new_session_id = await send_to_claude(
                prompt=user_text,
                session=session,
                on_text_chunk=accumulator.on_chunk,
                on_tool_use=accumulator.on_tool_use,
            )
            full_text = await accumulator.finalize()

            # Parse and execute action blocks
            cleaned_text, actions = parse_actions(full_text)
            if actions:
                action_errors = await execute_actions(
                    actions, context.bot, chat_id
                )
                for err in action_errors:
                    await _reply(update, f"⚠️ {err}")

            # Send tool summary as a separate formatted message
            if tool_uses:
                summary = format_tool_summary(tool_uses, fmt)
                await _reply(update, summary, formatted=True)

            # If streaming message was edited with full text including
            # action blocks, re-edit with cleaned text
            if actions and accumulator.message and cleaned_text:
                if len(cleaned_text) <= 4096:
                    try:
                        await accumulator.message.edit_text(cleaned_text)
                    except Exception:
                        pass
                else:
                    try:
                        await accumulator.message.delete()
                    except Exception:
                        pass
                    for chunk in split_message(cleaned_text):
                        await _reply(update, chunk)
            elif len(full_text) > 4096:
                for chunk in split_message(full_text):
                    await _reply(update, chunk)
        else:
            # Non-streaming: show tool activity in a status message
            status_msg = None

            async def _on_tool_use_ns(tool_name: str, tool_input: dict) -> None:
                nonlocal status_msg
                status = tool_status_text(tool_name, tool_input)
                try:
                    if status_msg is None:
                        status_msg = await update.message.reply_text(status)
                    else:
                        await status_msg.edit_text(status)
                except Exception:
                    pass

            response_text, tool_uses, new_session_id = await send_to_claude(
                prompt=user_text,
                session=session,
                on_tool_use=_on_tool_use_ns,
            )

            # Delete the status message before sending the real response
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

            # Parse and execute action blocks
            cleaned_text, actions = parse_actions(response_text)
            if actions:
                action_errors = await execute_actions(
                    actions, context.bot, chat_id
                )
                for err in action_errors:
                    await _reply(update, f"⚠️ {err}")
                response_text = cleaned_text

            if tool_uses:
                summary = format_tool_summary(tool_uses, fmt)
                # Combine summary + escaped response in one HTML message
                escaped = fmt.escape(response_text)
                combined = f"{summary}\n\n{escaped}"
                for chunk in split_message(combined):
                    await _reply(update, chunk, formatted=True)
            else:
                for chunk in split_message(response_text):
                    await _reply(update, chunk)

        # Update session
        if new_session_id:
            sm.update_session_id(session.name, new_session_id)

    except Exception as e:
        logger.exception("Error handling message")
        await _reply(update, f"Something went wrong: {e}")

    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        # Remove the eyes reaction when done
        await _set_reaction(context.bot, chat_id, message_id, None)


# -- Application factory --


async def _cmd_discover_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Used when ALLOWED_USER_ID is not set — tells the user their numeric ID."""
    user = update.effective_user
    logger.info("User ID discovery: id=%s username=%s", user.id, user.username)
    await update.message.reply_text(
        f"Your Telegram user ID is: {user.id}\n\n"
        f"Set this in your .env file as:\n"
        f"ALLOWED_USER_ID={user.id}\n\n"
        f"Then restart the bot."
    )


def create_application(session_manager: SessionManager, config: Config) -> Application:
    """Create and configure the Telegram application with command handlers."""
    app = Application.builder().token(config.bot_token).build()
    app.bot_data["session_manager"] = session_manager
    app.bot_data["config"] = config

    if config.allowed_user_id is not None:
        user_filter = filters.User(user_id=config.allowed_user_id)
    elif config.allowed_username is not None:
        user_filter = filters.User(username=config.allowed_username)
    else:
        logger.warning("ALLOWED_USER not set — running in ID discovery mode.")
        app.add_handler(MessageHandler(filters.ALL, _cmd_discover_id))
        return app

    app.add_handler(CommandHandler("start", cmd_start, filters=user_filter))
    app.add_handler(CommandHandler("new", cmd_new, filters=user_filter))
    app.add_handler(CommandHandler("sessions", cmd_sessions, filters=user_filter))
    app.add_handler(CommandHandler("switch", cmd_switch, filters=user_filter))
    app.add_handler(CommandHandler("delete", cmd_delete, filters=user_filter))
    app.add_handler(CommandHandler("rename", cmd_rename, filters=user_filter))
    app.add_handler(CommandHandler("cd", cmd_cd, filters=user_filter))
    app.add_handler(CommandHandler("dirs", cmd_dirs, filters=user_filter))
    app.add_handler(CommandHandler("file", cmd_file, filters=user_filter))
    app.add_handler(CommandHandler("help", cmd_help, filters=user_filter))
    app.add_handler(CommandHandler("stream", cmd_stream, filters=user_filter))
    app.add_handler(CommandHandler("permissions", cmd_permissions, filters=user_filter))
    app.add_handler(CommandHandler("current", cmd_current, filters=user_filter))
    app.add_handler(CommandHandler("restart", cmd_restart, filters=user_filter))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & user_filter,
            handle_message,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.VOICE & user_filter,
            handle_voice,
        )
    )

    async def _post_init(application: Application) -> None:
        """Send restart notification if we're coming back from a restart."""
        from megobari.actions import load_restart_marker

        chat_id = load_restart_marker()
        if chat_id:
            try:
                await application.bot.send_message(
                    chat_id=chat_id, text="✅ Bot restarted successfully."
                )
            except Exception:
                logger.warning("Failed to send restart notification")

    app.post_init = _post_init

    return app
