"""Core message processing: handle_message, handle_photo, handle_document, handle_voice."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

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
from megobari.transport import MessageHandle, TransportContext

from ._common import _accumulate_usage, _busy_sessions, _track_user

logger = logging.getLogger(__name__)


async def _send_typing_periodically(ctx: TransportContext) -> None:
    """Periodically send typing indicator until cancelled."""
    try:
        while True:
            await ctx.send_typing()
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


class StreamingAccumulator:
    """Accumulates streamed text chunks and edits a single message."""

    def __init__(self, ctx: TransportContext):
        self.ctx = ctx
        self.accumulated = ""
        self.handle: MessageHandle | None = None
        self.last_edit_len = 0
        self.edit_threshold = 200
        self._text_started = False

    async def initialize(self):
        """Send initial placeholder message."""
        self.handle = await self.ctx.reply("\u2026")

    async def on_tool_use(self, tool_name: str, tool_input: dict) -> None:
        """Update placeholder with tool activity before text starts streaming."""
        if self._text_started or not self.handle:
            return
        status = tool_status_text(tool_name, tool_input)
        try:
            await self.ctx.edit_message(self.handle, status)
        except Exception:
            pass

    async def on_chunk(self, text: str) -> None:
        """Accumulate text chunk and update message if threshold reached."""
        self._text_started = True
        self.accumulated += text
        if len(self.accumulated) - self.last_edit_len >= self.edit_threshold:
            await self._do_edit()

    async def _do_edit(self) -> None:
        max_len = self.ctx.max_message_length
        display = self.accumulated[:max_len]
        try:
            rendered = sanitize_html(markdown_to_html(display))
            await self.ctx.edit_message(
                self.handle, rendered, formatted=True
            )
            self.last_edit_len = len(self.accumulated)
        except Exception:
            # Fallback to plain text if HTML parsing fails
            try:
                await self.ctx.edit_message(self.handle, display)
                self.last_edit_len = len(self.accumulated)
            except Exception:
                pass  # ignore edit failures (e.g., text unchanged)

    async def finalize(self) -> str:
        """Finalize streaming and return accumulated text."""
        max_len = self.ctx.max_message_length
        if self.accumulated and self.handle:
            if len(self.accumulated) <= max_len:
                await self._do_edit()
            else:
                try:
                    await self.ctx.delete_message(self.handle)
                except Exception:
                    pass
        return self.accumulated


async def handle_message(ctx: TransportContext) -> None:
    """Handle incoming text messages and send to Claude."""
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return

    user_text = ctx.text

    # If this session is already processing, reject with hint to switch
    if session.name in _busy_sessions:
        await ctx.set_reaction("\u23f3")
        await ctx.reply(f"⏳ Session *{session.name}* is busy. "
                        f"`/switch` to another or wait.")
        return

    await ctx.set_reaction("\U0001f440")

    # Fire-and-forget: track user in DB without blocking the handler
    asyncio.create_task(_track_user(ctx))

    logger.info(
        "[%s] User: %s",
        session.name,
        user_text[:200] + ("..." if len(user_text) > 200 else ""),
    )

    _busy_sessions.add(session.name)
    try:
        await _process_prompt(user_text, ctx)
    finally:
        _busy_sessions.discard(session.name)
        await ctx.set_reaction(None)


async def _process_prompt(user_text: str, ctx: TransportContext) -> None:
    """Send a prompt to Claude and deliver the response."""
    sm = ctx.session_manager
    session = sm.current
    fmt = ctx.formatter

    # Start typing indicator
    typing_task = asyncio.create_task(_send_typing_periodically(ctx))

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

    # Log user message immediately (fire-and-forget) so it appears on
    # the dashboard before the assistant finishes processing.
    asyncio.create_task(log_message(session.name, "user", user_text))

    try:
        if session.streaming:
            accumulator = StreamingAccumulator(ctx)
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
                uid = ctx.user_id or None
                action_errors = await execute_actions(
                    actions, ctx, user_id=uid
                )
                for err in action_errors:
                    await ctx.reply(f"⚠️ {err}")

            # Send tool summary as a separate formatted message
            if tool_uses:
                summary = format_tool_summary(tool_uses, fmt)
                await ctx.reply(summary, formatted=True)

            # If streaming message was edited with full text including
            # action blocks, re-edit with cleaned text
            max_len = ctx.max_message_length
            if actions and accumulator.handle and cleaned_text:
                if len(cleaned_text) <= max_len:
                    try:
                        rendered = markdown_to_html(cleaned_text)
                        await ctx.edit_message(
                            accumulator.handle, rendered, formatted=True,
                        )
                    except Exception:
                        try:
                            await ctx.edit_message(
                                accumulator.handle, cleaned_text
                            )
                        except Exception:
                            pass
                else:
                    try:
                        await ctx.delete_message(accumulator.handle)
                    except Exception:
                        pass
                    for chunk in split_message(cleaned_text):
                        await ctx.reply(
                            markdown_to_html(chunk), formatted=True,
                        )
            elif len(full_text) > max_len:
                for chunk in split_message(full_text):
                    await ctx.reply(
                        markdown_to_html(chunk), formatted=True,
                    )
        else:
            # Non-streaming: show tool activity in a status message
            status_handle: MessageHandle | None = None

            async def _on_tool_use_ns(tool_name: str, tool_input: dict) -> None:
                nonlocal status_handle
                status = tool_status_text(tool_name, tool_input)
                try:
                    if status_handle is None:
                        status_handle = await ctx.reply(status)
                    else:
                        await ctx.edit_message(status_handle, status)
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
            if status_handle:
                try:
                    await ctx.delete_message(status_handle)
                except Exception:
                    pass

            # Parse and execute action blocks
            cleaned_text, actions = parse_actions(response_text)
            if actions:
                uid = ctx.user_id or None
                action_errors = await execute_actions(
                    actions, ctx, user_id=uid
                )
                for err in action_errors:
                    await ctx.reply(f"⚠️ {err}")
                response_text = cleaned_text

            if tool_uses:
                summary = format_tool_summary(tool_uses, fmt)
                rendered = sanitize_html(markdown_to_html(response_text))
                combined = f"{summary}\n\n{rendered}"
                for chunk in split_message(combined):
                    await ctx.reply(chunk, formatted=True)
            else:
                rendered = sanitize_html(markdown_to_html(response_text))
                for chunk in split_message(rendered):
                    await ctx.reply(chunk, formatted=True)

        # Update session
        if new_session_id:
            sm.update_session_id(session.name, new_session_id)

        # Accumulate usage stats
        uid = ctx.user_id or None
        _accumulate_usage(ctx, session.name, usage, user_id=uid)

        # Log assistant message (user was logged before processing)
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
        await ctx.reply(f"Something went wrong: {e}")

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


async def handle_photo(ctx: TransportContext) -> None:
    """Handle incoming photos: save to session cwd and forward path to Claude."""
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return

    if session.name in _busy_sessions:
        await ctx.set_reaction("\u23f3")
        await ctx.reply(f"⏳ Session *{session.name}* is busy. "
                        f"`/switch` to another or wait.")
        return

    caption = ctx.caption or ""

    await ctx.set_reaction("\U0001f440")
    asyncio.create_task(_track_user(ctx))
    _busy_sessions.add(session.name)

    try:
        save_path = await ctx.download_photo()
        if not save_path:
            await ctx.reply("Failed to download photo.")
            return

        prompt = f"The user sent a photo saved at: {save_path}"
        if caption:
            prompt += f"\nCaption: {caption}"
        prompt += "\nPlease look at the image and respond."

        await _process_prompt(prompt, ctx)

    except Exception as e:
        logger.exception("Error handling photo")
        await ctx.reply(f"Something went wrong with photo: {e}")
    finally:
        _busy_sessions.discard(session.name)
        await ctx.set_reaction(None)


async def handle_document(ctx: TransportContext) -> None:
    """Handle incoming documents: save to session cwd and forward path to Claude."""
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return

    if session.name in _busy_sessions:
        await ctx.set_reaction("\u23f3")
        await ctx.reply(f"⏳ Session *{session.name}* is busy. "
                        f"`/switch` to another or wait.")
        return

    caption = ctx.caption or ""

    await ctx.set_reaction("\U0001f440")
    asyncio.create_task(_track_user(ctx))
    _busy_sessions.add(session.name)

    try:
        result = await ctx.download_document()
        if not result:
            await ctx.reply("Failed to download document.")
            return
        save_path, filename = result

        prompt = f"The user sent a file saved at: {save_path}"
        if caption:
            prompt += f"\nCaption: {caption}"
        prompt += "\nPlease examine the file and respond."

        await _process_prompt(prompt, ctx)

    except Exception as e:
        logger.exception("Error handling document")
        await ctx.reply(f"Something went wrong with document: {e}")
    finally:
        _busy_sessions.discard(session.name)
        await ctx.set_reaction(None)


async def handle_voice(ctx: TransportContext) -> None:
    """Handle incoming voice messages: transcribe and send to Claude."""
    try:
        from megobari.voice import INSTALL_HINT, get_transcriber, is_available
    except ImportError:
        await ctx.reply("⚠️ Voice support requires faster-whisper.\n"
                        "Install with: pip install megobari[voice]")
        return

    if not is_available():
        await ctx.reply(f"⚠️ {INSTALL_HINT}")
        return

    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return

    if session.name in _busy_sessions:
        await ctx.set_reaction("\u23f3")
        await ctx.reply(f"⏳ Session *{session.name}* is busy. "
                        f"`/switch` to another or wait.")
        return

    config: Config = ctx.bot_data.get("config")
    model_size = config.whisper_model if config else "small"

    await ctx.set_reaction("\U0001f440")
    asyncio.create_task(_track_user(ctx))
    _busy_sessions.add(session.name)

    tmp_path = None
    try:
        tmp_path = await ctx.download_voice()
        if not tmp_path:
            await ctx.reply("Failed to download voice message.")
            return

        # Transcribe (run in thread to avoid blocking the event loop)
        transcriber = get_transcriber(model_size)
        transcription = await asyncio.to_thread(
            transcriber.transcribe, str(tmp_path)
        )

        if not transcription.strip():
            await ctx.reply("Could not transcribe voice message.")
            return

        # Show transcription
        await ctx.reply(f"\U0001f3a4 {transcription}")

        # Process transcription as a prompt
        await _process_prompt(transcription, ctx)

    except Exception as e:
        logger.exception("Error handling voice message")
        await ctx.reply(f"Something went wrong with voice: {e}")
    finally:
        _busy_sessions.discard(session.name)
        await ctx.set_reaction(None)
        # Clean up temp file
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
