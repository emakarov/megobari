"""Session management command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from megobari.message_utils import format_session_list
from megobari.session import VALID_PERMISSION_MODES

from ._common import _get_sm, _reply, fmt


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
