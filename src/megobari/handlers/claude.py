"""Core message processing: handle_message, handle_photo, handle_document, handle_voice."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from megobari.actions import execute_actions, parse_actions
from megobari.claude_bridge import send_to_claude
from megobari.config import Config
from megobari.markdown_html import markdown_to_html
from megobari.mcp_config import filter_mcp_servers, load_mcp_registry
from megobari.message_utils import (
    format_tool_summary,
    sanitize_html,
    split_message,
    tool_status_text,
)
from megobari.recall import build_recall_context
from megobari.summarizer import log_message, maybe_summarize_background

from ._common import (
    _accumulate_usage,
    _busy_sessions,
    _get_sm,
    _reply,
    _set_reaction,
    _track_user,
    fmt,
)

logger = logging.getLogger(__name__)


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
            rendered = sanitize_html(markdown_to_html(display))
            await self.message.edit_text(rendered, parse_mode="HTML")
            self.last_edit_len = len(self.accumulated)
        except Exception:
            # Fallback to plain text if HTML parsing fails
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

    # If this session is already processing, reject with hint to switch
    if session.name in _busy_sessions:
        await _set_reaction(context.bot, chat_id, message_id, "\u23f3")
        await _reply(update, f"⏳ Session *{session.name}* is busy. "
                     f"`/switch` to another or wait.")
        return

    await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")

    # Fire-and-forget: track user in DB without blocking the handler
    asyncio.create_task(_track_user(update))

    logger.info(
        "[%s] User: %s",
        session.name,
        user_text[:200] + ("..." if len(user_text) > 200 else ""),
    )

    _busy_sessions.add(session.name)
    try:
        await _process_prompt(user_text, update, context)
    finally:
        _busy_sessions.discard(session.name)
        await _set_reaction(context.bot, chat_id, message_id, None)


async def _process_prompt(
    user_text: str, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Send a prompt to Claude and deliver the response. Used by both text and voice."""
    sm = _get_sm(context)
    session = sm.current
    chat_id = update.effective_chat.id

    # Start typing indicator
    typing_task = asyncio.create_task(
        _send_typing_periodically(chat_id, context.bot)
    )

    # Build recall context (summaries + memories + persona metadata)
    recall_result = await build_recall_context(session.name)

    # Extract context string and resolve persona MCP servers
    recall_context: str | None = None
    mcp_servers: dict[str, dict] | None = None
    if recall_result is not None:
        from megobari.recall import RecallResult
        if isinstance(recall_result, RecallResult):
            recall_context = recall_result.context
            if recall_result.persona_mcp_servers:
                registry = load_mcp_registry()
                filtered = filter_mcp_servers(
                    registry, recall_result.persona_mcp_servers
                )
                if filtered:
                    mcp_servers = filtered
        else:
            # Legacy: plain string return
            recall_context = recall_result

    try:
        if session.streaming:
            accumulator = StreamingAccumulator(update, context)
            await accumulator.initialize()
            response_text, tool_uses, new_session_id, usage = await send_to_claude(
                prompt=user_text,
                session=session,
                on_text_chunk=accumulator.on_chunk,
                on_tool_use=accumulator.on_tool_use,
                recall_context=recall_context,
                mcp_servers=mcp_servers,
            )
            full_text = await accumulator.finalize()

            # Parse and execute action blocks
            cleaned_text, actions = parse_actions(full_text)
            if actions:
                uid = update.effective_user.id if update.effective_user else None
                action_errors = await execute_actions(
                    actions, context.bot, chat_id, user_id=uid
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
                        rendered = markdown_to_html(cleaned_text)
                        await accumulator.message.edit_text(
                            rendered, parse_mode="HTML",
                        )
                    except Exception:
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
                        await _reply(
                            update, markdown_to_html(chunk), formatted=True,
                        )
            elif len(full_text) > 4096:
                for chunk in split_message(full_text):
                    await _reply(
                        update, markdown_to_html(chunk), formatted=True,
                    )
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

            response_text, tool_uses, new_session_id, usage = await send_to_claude(
                prompt=user_text,
                session=session,
                on_tool_use=_on_tool_use_ns,
                recall_context=recall_context,
                mcp_servers=mcp_servers,
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
                uid = update.effective_user.id if update.effective_user else None
                action_errors = await execute_actions(
                    actions, context.bot, chat_id, user_id=uid
                )
                for err in action_errors:
                    await _reply(update, f"⚠️ {err}")
                response_text = cleaned_text

            if tool_uses:
                summary = format_tool_summary(tool_uses, fmt)
                rendered = sanitize_html(markdown_to_html(response_text))
                combined = f"{summary}\n\n{rendered}"
                for chunk in split_message(combined):
                    await _reply(update, chunk, formatted=True)
            else:
                rendered = sanitize_html(markdown_to_html(response_text))
                for chunk in split_message(rendered):
                    await _reply(update, chunk, formatted=True)

        # Update session
        if new_session_id:
            sm.update_session_id(session.name, new_session_id)

        # Accumulate usage stats
        uid = update.effective_user.id if update.effective_user else None
        _accumulate_usage(context, session.name, usage, user_id=uid)

        # Log messages and trigger summarization (fire-and-forget)
        asyncio.create_task(log_message(session.name, "user", user_text))
        asyncio.create_task(log_message(session.name, "assistant", response_text))

        async def _summarize_send(prompt: str) -> str:
            """Lightweight Claude call for summarization (fresh session)."""
            from megobari.session import Session as _Session
            tmp_session = _Session(name="_summarizer", cwd=session.cwd)
            text, _, _, _ = await send_to_claude(prompt=prompt, session=tmp_session)
            return text

        asyncio.create_task(
            maybe_summarize_background(session.name, _summarize_send)
        )

    except Exception as e:
        logger.exception("Error handling message")
        await _reply(update, f"Something went wrong: {e}")

    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


def _busy_emoji(session_name: str | None = None) -> str:
    """Return hourglass if session is busy, eyes if idle.

    Args:
        session_name: Session to check. If None, checks if any session is busy.
    """
    if session_name is not None:
        return "\u23f3" if session_name in _busy_sessions else "\U0001f440"
    return "\u23f3" if _busy_sessions else "\U0001f440"


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photos: save to session cwd and forward path to Claude."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    if session.name in _busy_sessions:
        await _set_reaction(context.bot, chat_id, message_id, "\u23f3")
        await _reply(update, f"⏳ Session *{session.name}* is busy. "
                     f"`/switch` to another or wait.")
        return

    caption = update.message.caption or ""
    photo = update.message.photo[-1]

    await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")
    asyncio.create_task(_track_user(update))
    _busy_sessions.add(session.name)

    try:
        photo_file = await photo.get_file()
        ext = Path(photo_file.file_path).suffix if photo_file.file_path else ".jpg"
        filename = f"photo_{message_id}{ext}"
        save_path = Path(session.cwd) / filename
        await photo_file.download_to_drive(str(save_path))

        prompt = f"The user sent a photo saved at: {save_path}"
        if caption:
            prompt += f"\nCaption: {caption}"
        prompt += "\nPlease look at the image and respond."

        await _process_prompt(prompt, update, context)

    except Exception as e:
        logger.exception("Error handling photo")
        await _reply(update, f"Something went wrong with photo: {e}")
    finally:
        _busy_sessions.discard(session.name)
        await _set_reaction(context.bot, chat_id, message_id, None)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming documents: save to session cwd and forward path to Claude."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    if session.name in _busy_sessions:
        await _set_reaction(context.bot, chat_id, message_id, "\u23f3")
        await _reply(update, f"⏳ Session *{session.name}* is busy. "
                     f"`/switch` to another or wait.")
        return

    caption = update.message.caption or ""
    doc = update.message.document

    await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")
    asyncio.create_task(_track_user(update))
    _busy_sessions.add(session.name)

    try:
        doc_file = await doc.get_file()
        filename = doc.file_name or f"document_{message_id}"
        save_path = Path(session.cwd) / filename
        await doc_file.download_to_drive(str(save_path))

        prompt = f"The user sent a file saved at: {save_path}"
        if caption:
            prompt += f"\nCaption: {caption}"
        prompt += "\nPlease examine the file and respond."

        await _process_prompt(prompt, update, context)

    except Exception as e:
        logger.exception("Error handling document")
        await _reply(update, f"Something went wrong with document: {e}")
    finally:
        _busy_sessions.discard(session.name)
        await _set_reaction(context.bot, chat_id, message_id, None)


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

    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    if session.name in _busy_sessions:
        await _set_reaction(context.bot, chat_id, message_id, "\u23f3")
        await _reply(update, f"⏳ Session *{session.name}* is busy. "
                     f"`/switch` to another or wait.")
        return

    config: Config = context.bot_data.get("config")
    model_size = config.whisper_model if config else "small"

    voice = update.message.voice

    await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")
    asyncio.create_task(_track_user(update))
    _busy_sessions.add(session.name)

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

        # Process transcription as a prompt
        await _process_prompt(transcription, update, context)

    except Exception as e:
        logger.exception("Error handling voice message")
        await _reply(update, f"Something went wrong with voice: {e}")
    finally:
        _busy_sessions.discard(session.name)
        await _set_reaction(context.bot, chat_id, message_id, None)
        # Clean up temp file
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
