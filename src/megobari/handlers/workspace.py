"""Working directory and file command handlers."""

from __future__ import annotations

from pathlib import Path

from megobari.transport import TransportContext


async def cmd_cd(ctx: TransportContext) -> None:
    """Handle /cd command to change the working directory."""
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return
    if not ctx.args:
        await ctx.reply(f"Current directory: {session.cwd}\n\nUsage: /cd <path>")
        return
    path = " ".join(ctx.args)  # support paths with spaces
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        await ctx.reply(f"Directory not found: {resolved}")
        return
    session.cwd = str(resolved)
    sm._save()
    await ctx.reply(f"Working directory: {session.cwd}")


async def cmd_dirs(ctx: TransportContext) -> None:
    """Handle /dirs command to manage session directories."""
    fmt = ctx.formatter
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return

    if not ctx.args:
        # List directories
        lines = [fmt.bold("Directories:"), ""]
        lines.append(f"\u25b8 {fmt.code(fmt.escape(session.cwd))} (cwd)")
        for d in session.dirs:
            lines.append(f"  {fmt.code(fmt.escape(d))}")
        if not session.dirs:
            lines.append(fmt.italic("No extra directories. Use /dirs add <path>"))
        await ctx.reply("\n".join(lines), formatted=True)
        return

    action = ctx.args[0]

    if action == "add":
        if len(ctx.args) < 2:
            await ctx.reply("Usage: /dirs add <path>")
            return
        path = " ".join(ctx.args[1:])
        resolved = str(Path(path).expanduser().resolve())
        if not Path(resolved).is_dir():
            await ctx.reply(f"Directory not found: {resolved}")
            return
        if resolved in session.dirs or resolved == session.cwd:
            await ctx.reply(f"Already added: {resolved}")
            return
        session.dirs.append(resolved)
        sm._save()
        await ctx.reply(f"Added: {resolved}")

    elif action == "rm":
        if len(ctx.args) < 2:
            await ctx.reply("Usage: /dirs rm <path>")
            return
        path = " ".join(ctx.args[1:])
        resolved = str(Path(path).expanduser().resolve())
        if resolved not in session.dirs:
            await ctx.reply(f"Not in directory list: {resolved}")
            return
        session.dirs.remove(resolved)
        sm._save()
        await ctx.reply(f"Removed: {resolved}")

    else:
        await ctx.reply("Usage: /dirs [add|rm] <path>")


async def cmd_file(ctx: TransportContext) -> None:
    """Handle /file command to send a file to the user."""
    sm = ctx.session_manager
    session = sm.current
    if not ctx.args:
        await ctx.reply("Usage: /file <path>")
        return
    raw_path = " ".join(ctx.args)
    resolved = Path(raw_path).expanduser()
    if not resolved.is_absolute() and session:
        resolved = Path(session.cwd) / resolved
    resolved = resolved.resolve()
    if not resolved.is_file():
        await ctx.reply(f"File not found: {resolved}")
        return
    try:
        await ctx.reply_document(resolved, resolved.name)
    except Exception as e:
        await ctx.reply(f"Failed to send file: {e}")
