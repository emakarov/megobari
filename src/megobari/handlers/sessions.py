"""Session management command handlers."""

from __future__ import annotations

from megobari.message_utils import format_session_list
from megobari.session import VALID_PERMISSION_MODES
from megobari.transport import TransportContext


async def cmd_start(ctx: TransportContext) -> None:
    """Handle /start command."""
    sm = ctx.session_manager
    if not sm.list_all():
        sm.create("default")
    await ctx.reply(
        "Megobari is ready.\n\n"
        "Send a message to talk to Claude.\n"
        "Use /help to see all commands.",
    )


async def cmd_new(ctx: TransportContext) -> None:
    """Handle /new command to create a new session."""
    if not ctx.args:
        await ctx.reply("Usage: /new <name>")
        return
    name = ctx.args[0]
    sm = ctx.session_manager
    session = sm.create(name)
    if session is None:
        await ctx.reply(f"Session '{name}' already exists.")
        return
    await ctx.reply(f"Created and switched to session '{name}'.")


async def cmd_sessions(ctx: TransportContext) -> None:
    """Handle /sessions command to list all sessions."""
    fmt = ctx.formatter
    sm = ctx.session_manager
    text = format_session_list(sm.list_all(), sm.active_name, fmt)
    await ctx.reply(text, formatted=True)


async def cmd_switch(ctx: TransportContext) -> None:
    """Handle /switch command to switch to a session."""
    if not ctx.args:
        await ctx.reply("Usage: /switch <name>")
        return
    name = ctx.args[0]
    sm = ctx.session_manager
    session = sm.switch(name)
    if session is None:
        await ctx.reply(f"Session '{name}' not found.")
        return
    await ctx.reply(f"Switched to session '{name}'.")


async def cmd_delete(ctx: TransportContext) -> None:
    """Handle /delete command to delete a session."""
    if not ctx.args:
        await ctx.reply("Usage: /delete <name>")
        return
    name = ctx.args[0]
    sm = ctx.session_manager
    if not sm.delete(name):
        await ctx.reply(f"Session '{name}' not found.")
        return
    active = sm.active_name
    if active:
        await ctx.reply(f"Deleted '{name}'. Active session is now '{active}'.")
    else:
        await ctx.reply(
            f"Deleted '{name}'. No sessions left. Use /new <name> to create one.",
        )


async def cmd_stream(ctx: TransportContext) -> None:
    """Handle /stream command to enable/disable streaming responses."""
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return
    if not ctx.args or ctx.args[0] not in ("on", "off"):
        await ctx.reply(
            f"Usage: /stream on|off\nCurrently: {'on' if session.streaming else 'off'}",
        )
        return
    session.streaming = ctx.args[0] == "on"
    sm._save()
    await ctx.reply(
        f"Streaming {'enabled' if session.streaming else 'disabled'} for '{session.name}'.",
    )


async def cmd_permissions(ctx: TransportContext) -> None:
    """Handle /permissions command to set session permission mode."""
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return
    if not ctx.args or ctx.args[0] not in VALID_PERMISSION_MODES:
        modes = ", ".join(sorted(VALID_PERMISSION_MODES))
        await ctx.reply(
            f"Usage: /permissions <mode>\nModes: {modes}\n"
            f"Currently: {session.permission_mode}",
        )
        return
    session.permission_mode = ctx.args[0]  # type: ignore[assignment]
    sm._save()
    await ctx.reply(
        f"Permission mode set to '{session.permission_mode}' for '{session.name}'.",
    )


async def cmd_rename(ctx: TransportContext) -> None:
    """Handle /rename command to rename a session."""
    if not ctx.args or len(ctx.args) < 2:
        await ctx.reply("Usage: /rename <old_name> <new_name>")
        return
    old_name, new_name = ctx.args[0], ctx.args[1]
    sm = ctx.session_manager
    error = sm.rename(old_name, new_name)
    if error:
        await ctx.reply(error)
        return
    await ctx.reply(f"Renamed '{old_name}' \u2192 '{new_name}'.")
