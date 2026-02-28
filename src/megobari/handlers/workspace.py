"""Working directory and file command handlers."""

from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ._common import _get_sm, _reply, fmt


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
