"""Telegram bot handlers and application factory."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from megobari.actions import execute_actions, parse_actions
from megobari.claude_bridge import QueryUsage, send_to_claude
from megobari.config import Config
from megobari.db import Repository, get_session, init_db
from megobari.formatting import Formatter, TelegramFormatter
from megobari.markdown_html import markdown_to_html
from megobari.message_utils import (
    format_help,
    format_session_info,
    format_session_list,
    format_tool_summary,
    split_message,
    tool_status_text,
)
from megobari.recall import build_recall_context
from megobari.session import (
    MODEL_ALIASES,
    VALID_EFFORT_LEVELS,
    VALID_PERMISSION_MODES,
    VALID_THINKING_MODES,
    SessionManager,
)
from megobari.summarizer import log_message, maybe_summarize_background

logger = logging.getLogger(__name__)

# Client-specific formatter — swap this out for other frontends.
fmt: Formatter = TelegramFormatter()

# Track whether Claude is currently processing a message.
_busy = False


def _get_sm(context: ContextTypes.DEFAULT_TYPE) -> SessionManager:
    return context.bot_data["session_manager"]


def _reply(update: Update, text: str, formatted: bool = False):
    """Helper: reply with or without parse_mode."""
    kwargs = {}
    if formatted:
        kwargs["parse_mode"] = fmt.parse_mode
    return update.message.reply_text(text, **kwargs)


async def _track_user(update: Update) -> None:
    """Upsert the Telegram user in the local database."""
    user = update.effective_user
    if user is None:
        return
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.upsert_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
    except Exception:
        logger.debug("Failed to track user", exc_info=True)


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


async def cmd_release(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /release command to bump version, tag, push, and trigger PyPI publish."""
    import re
    import subprocess

    if not context.args:
        await _reply(update, "Usage: /release <version>\nExample: /release 0.2.0")
        return

    version = context.args[0].lstrip("v")
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        await _reply(update, f"Invalid version format: {version}\nExpected: X.Y.Z")
        return

    tag = f"v{version}"
    sm = _get_sm(context)
    session = sm.current
    project_root = session.cwd if session else str(Path.cwd())
    pyproject = Path(project_root) / "pyproject.toml"

    if not pyproject.is_file():
        await _reply(update, f"pyproject.toml not found in {project_root}")
        return

    await _reply(update, f"📦 Releasing {tag}...")

    try:
        # Update version in pyproject.toml
        content = pyproject.read_text()
        new_content = re.sub(
            r'^version\s*=\s*"[^"]*"',
            f'version = "{version}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if new_content == content:
            await _reply(update, "⚠️ Could not find version field in pyproject.toml")
            return
        pyproject.write_text(new_content)

        # Git commit, tag, push
        def _run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd, cwd=project_root, capture_output=True, text=True, check=True
            )

        _run(["git", "add", "pyproject.toml"])
        _run(["git", "commit", "-m", f"Release {tag}"])
        _run(["git", "tag", tag])
        _run(["git", "push"])
        _run(["git", "push", "--tags"])

        await _reply(
            update,
            f"✅ Released {tag}\n"
            f"• Version bumped to {version}\n"
            f"• Tag {tag} pushed\n"
            f"• GitHub Actions will publish to PyPI",
        )

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else str(e)
        await _reply(update, f"❌ Release failed:\n{stderr}")
    except Exception as e:
        await _reply(update, f"❌ Release failed: {e}")


def _busy_emoji() -> str:
    """Return hourglass if busy, eyes if idle."""
    return "\u23f3" if _busy else "\U0001f440"


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photos: save to session cwd and forward path to Claude."""
    global _busy

    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    caption = update.message.caption or ""

    # Get highest resolution photo
    photo = update.message.photo[-1]

    await _set_reaction(context.bot, chat_id, message_id, _busy_emoji())
    asyncio.create_task(_track_user(update))
    _busy = True

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
        _busy = False
        await _set_reaction(context.bot, chat_id, message_id, None)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming documents: save to session cwd and forward path to Claude."""
    global _busy

    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    caption = update.message.caption or ""
    doc = update.message.document

    await _set_reaction(context.bot, chat_id, message_id, _busy_emoji())
    asyncio.create_task(_track_user(update))
    _busy = True

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
        _busy = False
        await _set_reaction(context.bot, chat_id, message_id, None)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages: transcribe and send to Claude."""
    global _busy
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

    # React with appropriate emoji based on busy state
    await _set_reaction(context.bot, chat_id, message_id, _busy_emoji())
    asyncio.create_task(_track_user(update))
    _busy = True

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
        _busy = False
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


# -- Persona / Memory / Summary commands --


async def cmd_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /persona command: create, list, switch, delete, info."""
    args = context.args or []
    if not args:
        await _reply(
            update,
            "Usage:\n"
            "/persona list\n"
            "/persona create <name> [description]\n"
            "/persona info <name>\n"
            "/persona default <name>\n"
            "/persona delete <name>\n"
            "/persona prompt <name> <text>\n"
            "/persona mcp <name> <server1,server2,...>",
        )
        return

    sub = args[0].lower()

    if sub == "list":
        async with get_session() as s:
            repo = Repository(s)
            personas = await repo.list_personas()
        if not personas:
            await _reply(update, "No personas yet. Use /persona create <name>")
            return
        lines = []
        for p in personas:
            marker = " (default)" if p.is_default else ""
            lines.append(f"{'>' if p.is_default else ' '} {fmt.bold(p.name)}{marker}")
            if p.description:
                lines.append(f"   {fmt.escape(p.description)}")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "create":
        if len(args) < 2:
            await _reply(update, "Usage: /persona create <name> [description]")
            return
        name = args[1]
        desc = " ".join(args[2:]) if len(args) > 2 else None
        async with get_session() as s:
            repo = Repository(s)
            existing = await repo.get_persona(name)
            if existing:
                await _reply(update, f"Persona '{name}' already exists.")
                return
            await repo.create_persona(name=name, description=desc)
        await _reply(update, f"Created persona '{name}'.")

    elif sub == "info":
        if len(args) < 2:
            await _reply(update, "Usage: /persona info <name>")
            return
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.get_persona(args[1])
        if not p:
            await _reply(update, f"Persona '{args[1]}' not found.")
            return
        lines = [
            fmt.bold(p.name),
            f"Description: {p.description or '—'}",
            f"Default: {'yes' if p.is_default else 'no'}",
            f"System prompt: {(p.system_prompt[:100] + '...') if p.system_prompt else '—'}",
            f"MCP servers: {p.mcp_servers or '—'}",
        ]
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "default":
        if len(args) < 2:
            await _reply(update, "Usage: /persona default <name>")
            return
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.set_default_persona(args[1])
        if not p:
            await _reply(update, f"Persona '{args[1]}' not found.")
            return
        await _reply(update, f"Default persona set to '{p.name}'.")

    elif sub == "delete":
        if len(args) < 2:
            await _reply(update, "Usage: /persona delete <name>")
            return
        async with get_session() as s:
            repo = Repository(s)
            deleted = await repo.delete_persona(args[1])
        if deleted:
            await _reply(update, f"Deleted persona '{args[1]}'.")
        else:
            await _reply(update, f"Persona '{args[1]}' not found.")

    elif sub == "prompt":
        if len(args) < 3:
            await _reply(update, "Usage: /persona prompt <name> <text>")
            return
        name = args[1]
        prompt_text = " ".join(args[2:])
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.update_persona(name, system_prompt=prompt_text)
        if not p:
            await _reply(update, f"Persona '{name}' not found.")
            return
        await _reply(update, f"System prompt updated for '{name}'.")

    elif sub == "mcp":
        if len(args) < 3:
            await _reply(update, "Usage: /persona mcp <name> <server1,server2,...>")
            return
        name = args[1]
        servers = [s.strip() for s in args[2].split(",")]
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.update_persona(name, mcp_servers=servers)
        if not p:
            await _reply(update, f"Persona '{name}' not found.")
            return
        await _reply(update, f"MCP servers for '{name}': {servers}")

    else:
        await _reply(update, f"Unknown subcommand: {sub}. Use /persona for help.")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /memory command: set, get, list, delete."""
    args = context.args or []
    if not args:
        await _reply(
            update,
            "Usage:\n"
            "/memory list [category]\n"
            "/memory set <category> <key> <value>\n"
            "/memory get <category> <key>\n"
            "/memory delete <category> <key>",
        )
        return

    sub = args[0].lower()

    if sub == "list":
        category = args[1] if len(args) > 1 else None
        async with get_session() as s:
            repo = Repository(s)
            mems = await repo.list_memories(category=category)
        if not mems:
            await _reply(update, "No memories found.")
            return
        lines = []
        for m in mems:
            lines.append(f"{fmt.bold(m.category)}/{fmt.code(m.key)}: {fmt.escape(m.content[:80])}")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "set":
        if len(args) < 4:
            await _reply(update, "Usage: /memory set <category> <key> <value>")
            return
        category, key = args[1], args[2]
        value = " ".join(args[3:])
        async with get_session() as s:
            repo = Repository(s)
            await repo.set_memory(category=category, key=key, content=value)
        await _reply(update, f"Saved: {category}/{key}")

    elif sub == "get":
        if len(args) < 3:
            await _reply(update, "Usage: /memory get <category> <key>")
            return
        async with get_session() as s:
            repo = Repository(s)
            mem = await repo.get_memory(args[1], args[2])
        if not mem:
            await _reply(update, "Not found.")
            return
        meta = Repository.memory_metadata(mem)
        text = f"{fmt.bold(mem.category)}/{fmt.code(mem.key)}\n{fmt.escape(mem.content)}"
        if meta:
            text += f"\n\nMetadata: {fmt.code(_json.dumps(meta))}"
        await _reply(update, text, formatted=True)

    elif sub == "delete":
        if len(args) < 3:
            await _reply(update, "Usage: /memory delete <category> <key>")
            return
        async with get_session() as s:
            repo = Repository(s)
            deleted = await repo.delete_memory(args[1], args[2])
        if deleted:
            await _reply(update, f"Deleted: {args[1]}/{args[2]}")
        else:
            await _reply(update, "Not found.")

    else:
        await _reply(update, f"Unknown subcommand: {sub}. Use /memory for help.")


async def cmd_summaries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /summaries command: list, search, milestones."""
    args = context.args or []
    sm = _get_sm(context)
    session = sm.current

    if not args:
        # Default: show recent summaries for current session
        session_name = session.name if session else None
        async with get_session() as s:
            repo = Repository(s)
            sums = await repo.get_summaries(session_name=session_name, limit=5)
        if not sums:
            await _reply(update, "No summaries yet.")
            return
        lines = []
        for cs in sums:
            ts = cs.created_at.strftime("%Y-%m-%d %H:%M") if cs.created_at else "?"
            marker = " *" if cs.is_milestone else ""
            lines.append(f"{fmt.bold(ts)}{marker} [{cs.session_name}] ({cs.message_count} msgs)")
            # Show first 150 chars of summary
            preview = cs.summary[:150] + ("..." if len(cs.summary) > 150 else "")
            lines.append(f"  {fmt.escape(preview)}")
            lines.append("")
        await _reply(update, "\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub == "all":
        async with get_session() as s:
            repo = Repository(s)
            sums = await repo.get_summaries(limit=10)
        if not sums:
            await _reply(update, "No summaries found.")
            return
        lines = []
        for cs in sums:
            ts = cs.created_at.strftime("%Y-%m-%d %H:%M") if cs.created_at else "?"
            lines.append(f"{fmt.bold(ts)} [{cs.session_name}] ({cs.message_count} msgs)")
            preview = cs.summary[:100] + ("..." if len(cs.summary) > 100 else "")
            lines.append(f"  {fmt.escape(preview)}")
            lines.append("")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "search":
        if len(args) < 2:
            await _reply(update, "Usage: /summaries search <query>")
            return
        query = " ".join(args[1:])
        async with get_session() as s:
            repo = Repository(s)
            sums = await repo.search_summaries(query)
        if not sums:
            await _reply(update, f"No summaries matching '{query}'.")
            return
        lines = []
        for cs in sums:
            ts = cs.created_at.strftime("%Y-%m-%d %H:%M") if cs.created_at else "?"
            lines.append(f"{fmt.bold(ts)} [{cs.session_name}]")
            preview = cs.summary[:150] + ("..." if len(cs.summary) > 150 else "")
            lines.append(f"  {fmt.escape(preview)}")
            lines.append("")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "milestones":
        async with get_session() as s:
            repo = Repository(s)
            sums = await repo.get_summaries(milestones_only=True, limit=10)
        if not sums:
            await _reply(update, "No milestones found.")
            return
        lines = []
        for cs in sums:
            ts = cs.created_at.strftime("%Y-%m-%d %H:%M") if cs.created_at else "?"
            lines.append(f"{fmt.bold(ts)} * [{cs.session_name}]")
            preview = cs.summary[:150] + ("..." if len(cs.summary) > 150 else "")
            lines.append(f"  {fmt.escape(preview)}")
            lines.append("")
        await _reply(update, "\n".join(lines), formatted=True)

    else:
        await _reply(
            update,
            "Usage:\n"
            "/summaries — recent for current session\n"
            "/summaries all — recent across all sessions\n"
            "/summaries search <query>\n"
            "/summaries milestones",
        )


# -- /think command --


async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /think command: control extended thinking."""
    sm = _get_sm(context)
    session = sm.current

    args = context.args or []

    if not args:
        budget_info = ""
        if session.thinking == "enabled" and session.thinking_budget:
            budget_info = f" (budget: {session.thinking_budget:,} tokens)"
        msg = f"Thinking: {fmt.bold(session.thinking)}{budget_info}"
        await _reply(update, msg, formatted=True)
        return

    mode = args[0].lower()

    if mode == "on":
        session.thinking = "enabled"
        budget = 10000
        if len(args) > 1:
            try:
                budget = int(args[1])
            except ValueError:
                await _reply(update, "Invalid budget. Use: /think on [budget_tokens]")
                return
        session.thinking_budget = budget
        sm._save()
        await _reply(update, f"✅ Thinking enabled (budget: {budget:,} tokens)")
    elif mode == "off":
        session.thinking = "disabled"
        session.thinking_budget = None
        sm._save()
        await _reply(update, "✅ Thinking disabled")
    elif mode in VALID_THINKING_MODES:
        session.thinking = mode
        if mode != "enabled":
            session.thinking_budget = None
        sm._save()
        await _reply(update, f"✅ Thinking: {mode}")
    else:
        await _reply(
            update,
            "Usage:\n"
            "/think — show current setting\n"
            "/think adaptive — let Claude decide (default)\n"
            "/think on [budget] — enable with optional budget (default 10000)\n"
            "/think off — disable thinking",
        )


# -- /effort command --


async def cmd_effort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /effort command: control effort level."""
    sm = _get_sm(context)
    session = sm.current
    args = context.args or []

    if not args:
        level = session.effort or "not set (SDK default)"
        await _reply(update, f"Effort: {fmt.bold(str(level))}", formatted=True)
        return

    level = args[0].lower()

    if level == "off":
        session.effort = None
        sm._save()
        await _reply(update, "✅ Effort cleared (using SDK default)")
    elif level in VALID_EFFORT_LEVELS:
        session.effort = level
        sm._save()
        await _reply(update, f"✅ Effort: {level}")
    else:
        await _reply(
            update,
            "Usage:\n"
            "/effort — show current setting\n"
            "/effort low|medium|high|max — set level\n"
            "/effort off — clear (use SDK default)",
        )


# -- /usage command --


@dataclass
class SessionUsage:
    """Accumulated usage for a session (in-memory, resets on restart)."""

    total_cost_usd: float = 0.0
    total_turns: int = 0
    total_duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    message_count: int = 0


def _accumulate_usage(
    context: ContextTypes.DEFAULT_TYPE,
    session_name: str,
    query_usage: QueryUsage,
    user_id: int | None = None,
) -> None:
    """Accumulate usage stats from a query into bot_data and persist to DB."""
    # In-memory accumulation
    usage_map: dict[str, SessionUsage] = context.bot_data.setdefault("usage", {})
    su = usage_map.setdefault(session_name, SessionUsage())
    su.total_cost_usd += query_usage.cost_usd
    su.total_turns += query_usage.num_turns
    su.total_duration_ms += query_usage.duration_api_ms
    su.input_tokens += query_usage.input_tokens
    su.output_tokens += query_usage.output_tokens
    su.message_count += 1

    # Persist to DB (fire-and-forget)
    asyncio.create_task(
        _persist_usage(session_name, query_usage, user_id)
    )


async def _persist_usage(
    session_name: str, query_usage: QueryUsage, user_id: int | None
) -> None:
    """Save a usage record to the database."""
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_usage(
                session_name=session_name,
                cost_usd=query_usage.cost_usd,
                num_turns=query_usage.num_turns,
                duration_ms=query_usage.duration_api_ms,
                input_tokens=query_usage.input_tokens,
                output_tokens=query_usage.output_tokens,
                user_id=user_id,
            )
    except Exception:
        logger.warning("Failed to persist usage record", exc_info=True)


async def cmd_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /usage command: show session and historical usage stats."""
    sm = _get_sm(context)
    session = sm.current
    args = context.args or []

    if args and args[0].lower() == "all":
        # Show all-time totals from DB
        try:
            async with get_session() as s:
                repo = Repository(s)
                total = await repo.get_total_usage()
        except Exception:
            await _reply(update, "Failed to read usage from DB.")
            return

        if total["query_count"] == 0:
            await _reply(update, "No usage recorded yet.")
            return

        duration_s = total["total_duration_ms"] / 1000
        lines = [
            fmt.bold("All-time usage:"),
            f"{fmt.bold('Cost:')} ${total['total_cost']:.4f}",
            f"{fmt.bold('Turns:')} {total['total_turns']} ({total['query_count']} queries)",
            f"{fmt.bold('Sessions:')} {total['session_count']}",
            f"{fmt.bold('API time:')} {duration_s:.1f}s",
        ]
        await _reply(update, "\n".join(lines), formatted=True)
        return

    # Show current session usage — combine in-memory + DB historical
    lines = [f"{fmt.bold('Session:')} {fmt.escape(session.name)}"]

    # Current run (in-memory)
    usage_map: dict[str, SessionUsage] = context.bot_data.get("usage", {})
    su = usage_map.get(session.name)

    # Historical (DB)
    try:
        async with get_session() as s:
            repo = Repository(s)
            db_usage = await repo.get_session_usage(session.name)
    except Exception:
        db_usage = None

    if su and su.message_count > 0:
        duration_s = su.total_duration_ms / 1000
        lines.append("")
        lines.append(fmt.bold("This run:"))
        lines.append(f"  Cost: ${su.total_cost_usd:.4f}")
        lines.append(f"  Turns: {su.total_turns} ({su.message_count} messages)")
        lines.append(f"  API time: {duration_s:.1f}s")

    if db_usage and db_usage["query_count"] > 0:
        duration_s = db_usage["total_duration_ms"] / 1000
        lines.append("")
        lines.append(fmt.bold("All-time (this session):"))
        lines.append(f"  Cost: ${db_usage['total_cost']:.4f}")
        lines.append(f"  Turns: {db_usage['total_turns']} ({db_usage['query_count']} queries)")
        lines.append(f"  API time: {duration_s:.1f}s")

    if (not su or su.message_count == 0) and (not db_usage or db_usage["query_count"] == 0):
        await _reply(update, "No usage recorded yet for this session.")
        return

    await _reply(update, "\n".join(lines), formatted=True)


# -- /compact command --


async def cmd_compact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /compact command: summarize conversation and reset context."""
    sm = _get_sm(context)
    session = sm.current
    chat_id = update.effective_chat.id

    if not session.session_id:
        await _reply(update, "No active context to compact.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Ask Claude to summarize the conversation
    summary_prompt = (
        "Summarize our conversation. Produce two parts separated by the "
        "exact delimiter '---FULL---' on its own line:\n"
        "1. First, a SHORT one-line summary (max 150 chars) capturing the essence.\n"
        "2. Then '---FULL---'\n"
        "3. Then a FULL summary with bullet points covering decisions made, "
        "tasks completed, and any ongoing work."
    )

    response_text, _, _, _ = await send_to_claude(
        prompt=summary_prompt, session=session,
    )

    # Parse short + full summary from response
    from megobari.summarizer import _parse_summary
    short_summary, full_summary = _parse_summary(response_text)

    # Clear context (break session)
    session.session_id = None
    sm._save()

    # Seed new context with the summary
    seed_prompt = (
        f"Here is a summary of our previous conversation context:\n\n"
        f"{full_summary}\n\n"
        f"Continue from here. The user has compacted the conversation."
    )
    _, _, new_session_id, _ = await send_to_claude(
        prompt=seed_prompt, session=session,
    )

    if new_session_id:
        sm.update_session_id(session.name, new_session_id)

    # Save as a summary in DB
    uid = update.effective_user.id if update.effective_user else None
    try:
        async with get_session() as s:
            repo = Repository(s)
            await repo.add_summary(
                session_name=session.name,
                summary=full_summary,
                short_summary=short_summary,
                message_count=0,
                is_milestone=True,
                user_id=uid,
            )
    except Exception:
        logger.warning("Failed to save compact summary to DB")

    compact_msg = f"📦 Context compacted.\n\n{fmt.bold('Summary:')}\n{fmt.escape(full_summary)}"
    for chunk in split_message(compact_msg):
        await _reply(update, chunk, formatted=True)


# -- /doctor command --


async def cmd_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /doctor command: run health checks."""
    sm = _get_sm(context)
    checks: list[str] = []

    # 1. Claude CLI check
    try:
        import claude_agent_sdk
        version = getattr(claude_agent_sdk, "__version__", "unknown")
        checks.append(f"✅ Claude SDK: v{version}")
    except ImportError:
        checks.append("❌ Claude SDK: not installed")

    # 2. CLI reachability
    try:
        import shutil
        cli_path = shutil.which("claude")
        if cli_path:
            checks.append(f"✅ Claude CLI: {cli_path}")
        else:
            checks.append("❌ Claude CLI: not found in PATH")
    except Exception as e:
        checks.append(f"❌ Claude CLI check failed: {e}")

    # 3. Sessions info
    all_sessions = sm.list_all()
    stale = sum(1 for s in all_sessions if s.session_id)
    checks.append(f"📋 Sessions: {len(all_sessions)} total, {stale} with context")

    # 4. Sessions dir disk usage
    sessions_dir = sm._sessions_dir
    if sessions_dir.exists():
        sessions_file = sessions_dir / "sessions.json"
        size_bytes = sessions_file.stat().st_size if sessions_file.exists() else 0
        if size_bytes < 1024:
            size_str = f"{size_bytes}B"
        else:
            size_str = f"{size_bytes / 1024:.1f}KB"
        checks.append(f"💾 Sessions file: {size_str}")
    else:
        checks.append("💾 Sessions dir: not found")

    # 5. Database check
    try:
        async with get_session() as s:
            repo = Repository(s)
            from sqlalchemy import func, select

            from megobari.db.models import ConversationSummary, Memory, Message, User
            await repo.list_memories()  # just to test connectivity
            result = await s.execute(select(func.count()).select_from(User))
            user_count = result.scalar()
            result = await s.execute(select(func.count()).select_from(Memory))
            mem_count = result.scalar()
            result = await s.execute(select(func.count()).select_from(ConversationSummary))
            sum_count = result.scalar()
            result = await s.execute(select(func.count()).select_from(Message))
            msg_count = result.scalar()
        checks.append(
            f"🗄 DB: {user_count} users, {mem_count} memories, "
            f"{sum_count} summaries, {msg_count} messages"
        )
    except Exception as e:
        checks.append(f"❌ DB: {e}")

    # 6. Current session info
    session = sm.current
    if session:
        checks.append(
            f"🔧 Active session: {session.name} "
            f"(thinking={session.thinking}, effort={session.effort or 'default'})"
        )

    await _reply(update, "\n".join(checks))


# -- /model command --


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /model command: switch model for current session."""
    sm = _get_sm(context)
    session = sm.current
    args = context.args or []

    if not args:
        current = session.model or "default (SDK decides)"
        aliases_list = ", ".join(sorted(MODEL_ALIASES.keys()))
        await _reply(
            update,
            f"{fmt.bold('Model:')} {fmt.escape(current)}\n\n"
            f"Available: {aliases_list}\n"
            f"Or use a full model name.",
            formatted=True,
        )
        return

    model = args[0].lower()

    if model == "default" or model == "off":
        session.model = None
        sm._save()
        await _reply(update, "✅ Model cleared (SDK default)")
        return

    # Resolve alias
    resolved = MODEL_ALIASES.get(model, model)
    session.model = resolved
    sm._save()
    display = f"{model} → {resolved}" if model != resolved else resolved
    await _reply(update, f"✅ Model: {display}")


# -- /context command --


async def cmd_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /context command: show token usage for current session."""
    sm = _get_sm(context)
    session = sm.current

    # In-memory (this run)
    usage_map: dict[str, SessionUsage] = context.bot_data.get("usage", {})
    su = usage_map.get(session.name)

    # DB history
    try:
        async with get_session() as s:
            repo = Repository(s)
            db_usage = await repo.get_session_usage(session.name)
    except Exception:
        db_usage = None

    lines = [f"{fmt.bold('Context info for:')} {fmt.escape(session.name)}"]

    if su and su.message_count > 0:
        total_tokens = su.input_tokens + su.output_tokens
        lines.append("")
        lines.append(fmt.bold("This run:"))
        lines.append(f"  Input tokens: {su.input_tokens:,}")
        lines.append(f"  Output tokens: {su.output_tokens:,}")
        lines.append(f"  Total tokens: {total_tokens:,}")
        lines.append(f"  Messages: {su.message_count}")

    if db_usage and db_usage["query_count"] > 0:
        db_total = db_usage["total_input_tokens"] + db_usage["total_output_tokens"]
        lines.append("")
        lines.append(fmt.bold("All-time (this session):"))
        lines.append(f"  Input tokens: {db_usage['total_input_tokens']:,}")
        lines.append(f"  Output tokens: {db_usage['total_output_tokens']:,}")
        lines.append(f"  Total tokens: {db_total:,}")
        lines.append(f"  Queries: {db_usage['query_count']}")

    if (not su or su.message_count == 0) and (not db_usage or db_usage["query_count"] == 0):
        lines.append("\nNo token data recorded yet.")

    # Session config
    lines.append("")
    lines.append(fmt.bold("Session config:"))
    lines.append(f"  Model: {session.model or 'default'}")
    lines.append(f"  Thinking: {session.thinking}")
    lines.append(f"  Effort: {session.effort or 'default'}")
    lines.append(f"  Has context: {'yes' if session.session_id else 'no'}")

    await _reply(update, "\n".join(lines), formatted=True)


# -- /history command --


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /history command: browse past conversations from DB."""
    sm = _get_sm(context)
    session = sm.current
    args = context.args or []

    if not args:
        # Show recent messages for current session
        try:
            async with get_session() as s:
                repo = Repository(s)
                msgs = await repo.get_recent_messages(session.name, limit=10)
        except Exception:
            await _reply(update, "Failed to read history from DB.")
            return

        if not msgs:
            await _reply(update, "No messages recorded for this session yet.")
            return

        lines = [fmt.bold(f"Recent messages ({session.name}):"), ""]
        for m in reversed(msgs):  # oldest first
            ts = m.created_at.strftime("%H:%M") if m.created_at else "?"
            role_icon = "👤" if m.role == "user" else "🤖"
            preview = m.content[:100] + ("..." if len(m.content) > 100 else "")
            lines.append(f"{role_icon} {ts} {fmt.escape(preview)}")
        await _reply(update, "\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub == "all":
        # Show messages across all sessions
        try:
            async with get_session() as s:
                repo = Repository(s)
                from sqlalchemy import select

                from megobari.db.models import Message
                stmt = (
                    select(Message)
                    .order_by(Message.created_at.desc())
                    .limit(15)
                )
                result = await s.execute(stmt)
                msgs = list(result.scalars().all())
        except Exception:
            await _reply(update, "Failed to read history from DB.")
            return

        if not msgs:
            await _reply(update, "No messages recorded yet.")
            return

        lines = [fmt.bold("Recent messages (all sessions):"), ""]
        for m in reversed(msgs):
            ts = m.created_at.strftime("%m-%d %H:%M") if m.created_at else "?"
            role_icon = "👤" if m.role == "user" else "🤖"
            preview = m.content[:80] + ("..." if len(m.content) > 80 else "")
            lines.append(f"{role_icon} {ts} [{m.session_name}] {fmt.escape(preview)}")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "search" and len(args) > 1:
        query_text = " ".join(args[1:])
        try:
            async with get_session() as s:
                repo = Repository(s)
                from sqlalchemy import select

                from megobari.db.models import Message
                stmt = (
                    select(Message)
                    .where(Message.content.ilike(f"%{query_text}%"))
                    .order_by(Message.created_at.desc())
                    .limit(10)
                )
                result = await s.execute(stmt)
                msgs = list(result.scalars().all())
        except Exception:
            await _reply(update, "Failed to search history.")
            return

        if not msgs:
            await _reply(update, f"No messages matching '{query_text}'.")
            return

        lines = [fmt.bold(f"Search results for '{query_text}':"), ""]
        for m in reversed(msgs):
            ts = m.created_at.strftime("%m-%d %H:%M") if m.created_at else "?"
            role_icon = "👤" if m.role == "user" else "🤖"
            preview = m.content[:100] + ("..." if len(m.content) > 100 else "")
            lines.append(f"{role_icon} {ts} [{m.session_name}] {fmt.escape(preview)}")
        await _reply(update, "\n".join(lines), formatted=True)

    elif sub == "stats":
        try:
            async with get_session() as s:
                repo = Repository(s)
                from sqlalchemy import func as sqlfunc
                from sqlalchemy import select

                from megobari.db.models import Message

                # Count by session
                stmt = (
                    select(
                        Message.session_name,
                        sqlfunc.count(Message.id).label("cnt"),
                    )
                    .group_by(Message.session_name)
                    .order_by(sqlfunc.count(Message.id).desc())
                    .limit(10)
                )
                result = await s.execute(stmt)
                rows = result.all()
        except Exception:
            await _reply(update, "Failed to read history stats.")
            return

        if not rows:
            await _reply(update, "No messages recorded yet.")
            return

        lines = [fmt.bold("Message stats by session:"), ""]
        for row in rows:
            marker = " ◂" if row.session_name == session.name else ""
            lines.append(f"  {fmt.escape(row.session_name)}: {row.cnt} messages{marker}")
        await _reply(update, "\n".join(lines), formatted=True)

    else:
        await _reply(
            update,
            "Usage:\n"
            "/history — recent messages for current session\n"
            "/history all — recent across all sessions\n"
            "/history search <query> — search message content\n"
            "/history stats — message counts by session",
        )


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
            rendered = markdown_to_html(display)
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
    global _busy

    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    user_text = update.message.text
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    # React immediately — before anything else
    if _busy:
        await _set_reaction(context.bot, chat_id, message_id, "\u23f3")
    else:
        await _set_reaction(context.bot, chat_id, message_id, "\U0001f440")

    # Fire-and-forget: track user in DB without blocking the handler
    asyncio.create_task(_track_user(update))

    logger.info(
        "[%s] User: %s",
        session.name,
        user_text[:200] + ("..." if len(user_text) > 200 else ""),
    )

    _busy = True
    try:
        await _process_prompt(user_text, update, context)
    finally:
        _busy = False
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

    # Build recall context (summaries + memories)
    recall = await build_recall_context(session.name)

    try:
        if session.streaming:
            accumulator = StreamingAccumulator(update, context)
            await accumulator.initialize()
            response_text, tool_uses, new_session_id, usage = await send_to_claude(
                prompt=user_text,
                session=session,
                on_text_chunk=accumulator.on_chunk,
                on_tool_use=accumulator.on_tool_use,
                recall_context=recall,
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
                recall_context=recall,
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
                rendered = markdown_to_html(response_text)
                combined = f"{summary}\n\n{rendered}"
                for chunk in split_message(combined):
                    await _reply(update, chunk, formatted=True)
            else:
                for chunk in split_message(response_text):
                    await _reply(
                        update, markdown_to_html(chunk), formatted=True,
                    )

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
    app.add_handler(CommandHandler("release", cmd_release, filters=user_filter))
    app.add_handler(CommandHandler("persona", cmd_persona, filters=user_filter))
    app.add_handler(CommandHandler("memory", cmd_memory, filters=user_filter))
    app.add_handler(CommandHandler("summaries", cmd_summaries, filters=user_filter))
    app.add_handler(CommandHandler("think", cmd_think, filters=user_filter))
    app.add_handler(CommandHandler("effort", cmd_effort, filters=user_filter))
    app.add_handler(CommandHandler("usage", cmd_usage, filters=user_filter))
    app.add_handler(CommandHandler("compact", cmd_compact, filters=user_filter))
    app.add_handler(CommandHandler("doctor", cmd_doctor, filters=user_filter))
    app.add_handler(CommandHandler("model", cmd_model, filters=user_filter))
    app.add_handler(CommandHandler("context", cmd_context, filters=user_filter))
    app.add_handler(CommandHandler("history", cmd_history, filters=user_filter))
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
    app.add_handler(
        MessageHandler(
            filters.PHOTO & user_filter,
            handle_photo,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Document.ALL & user_filter,
            handle_document,
        )
    )

    async def _post_init(application: Application) -> None:
        """Initialize DB and send restart notification."""
        await init_db()
        logger.info("Database initialized at ~/.megobari/megobari.db")

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
