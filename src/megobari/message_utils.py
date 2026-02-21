"""Message formatting and splitting utilities."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath

from megobari.config import TELEGRAM_MAX_MESSAGE_LEN
from megobari.formatting import Formatter, PlainTextFormatter
from megobari.session import Session


def split_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LEN) -> list[str]:
    """Split a message into chunks that fit within max_length."""
    if not text:
        return ["(empty response)"]
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        chunk = remaining[:max_length]

        # Try splitting at paragraph boundary
        split_pos = chunk.rfind("\n\n")
        if split_pos == -1:
            # Try newline
            split_pos = chunk.rfind("\n")
        if split_pos == -1:
            # Try space
            split_pos = chunk.rfind(" ")
        if split_pos == -1:
            # Hard cut
            split_pos = max_length

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip("\n")

    return chunks


def format_session_info(
    session: Session, fmt: Formatter | None = None
) -> str:
    """Format session details as a multi-line string."""
    if fmt is None:
        fmt = PlainTextFormatter()

    def line(label: str, value: str) -> str:
        return f"{fmt.bold(label + ':')} {fmt.escape(value)}"

    lines = [
        line("Session", session.name),
        line("Working dir", session.cwd),
    ]
    if session.dirs:
        lines.append(line("Extra dirs", f"{len(session.dirs)} (/dirs to list)"))
    lines += [
        line("Streaming", "on" if session.streaming else "off"),
        line("Permissions", session.permission_mode),
        line("Has context", "yes" if session.session_id else "no"),
        line("Created", session.created_at),
        line("Last used", session.last_used_at),
    ]
    return "\n".join(lines)


def format_session_list(
    sessions: list[Session],
    active_name: str | None,
    fmt: Formatter | None = None,
) -> str:
    """Format a list of sessions with the active session marked."""
    if fmt is None:
        fmt = PlainTextFormatter()

    if not sessions:
        return "No sessions. Use /new <name> to create one."

    lines: list[str] = []
    for s in sessions:
        if s.name == active_name:
            name_part = f"▸ {fmt.bold(fmt.escape(s.name))}"
        else:
            name_part = f"  {fmt.escape(s.name)}"
        flags = []
        if s.streaming:
            flags.append("stream")
        flags.append(s.permission_mode)
        lines.append(f"{name_part} ({', '.join(flags)})")

    return "\n".join(lines)


def format_help(fmt: Formatter | None = None) -> str:
    """Format the help text listing all available commands."""
    if fmt is None:
        fmt = PlainTextFormatter()

    title = fmt.bold("Available commands:")
    cmds = [
        (f"/new {fmt.code('<name>')}", "Create a new session"),
        ("/sessions", "List all sessions"),
        (f"/switch {fmt.code('<name>')}", "Switch to a session"),
        (f"/rename {fmt.code('<old>')} {fmt.code('<new>')}", "Rename a session"),
        (f"/delete {fmt.code('<name>')}", "Delete a session"),
        ("/current", "Show active session info"),
        (f"/cd {fmt.code('<path>')}", "Change working directory"),
        (f"/dirs {fmt.code('[add|rm] <path>')}", "Manage extra directories"),
        (f"/stream {fmt.code('on|off')}", "Toggle streaming"),
        (f"/permissions {fmt.code('<mode>')}", "Set permission mode"),
        ("/help", "Show this message"),
    ]
    lines = [title, ""]
    for cmd, desc in cmds:
        lines.append(f"{cmd} — {fmt.escape(desc)}")
    return "\n".join(lines)


def format_tool_summary(
    tool_uses: list[tuple[str, dict]], fmt: Formatter | None = None
) -> str:
    """Format tool uses into a compact grouped summary."""
    if fmt is None:
        fmt = PlainTextFormatter()

    # Preserve insertion order
    groups: dict[str, list[dict]] = {}
    for name, tool_input in tool_uses:
        groups.setdefault(name, []).append(tool_input)

    lines: list[str] = []
    for name, inputs in groups.items():
        if name == "Bash":
            cmds = []
            for inp in inputs:
                cmd = inp.get("command", "")
                if len(cmd) > 60:
                    cmd = cmd[:57] + "..."
                cmds.append(fmt.code(cmd))
            lines.append("⚡ " + " · ".join(cmds))
        elif name in ("Read", "Write", "Edit"):
            filenames = [PurePosixPath(inp.get("file_path", "")).name for inp in inputs]
            counts = Counter(filenames)
            parts = []
            for f, c in counts.items():
                entry = fmt.code(f)
                if c > 1:
                    entry += f" ×{c}"
                parts.append(entry)
            lines.append(f"✏️ {fmt.bold(name + ':')} {', '.join(parts)}")
        elif name in ("Glob", "Grep"):
            patterns = [fmt.code(inp.get("pattern", "")) for inp in inputs]
            lines.append(f"🔍 {fmt.bold(name + ':')} {', '.join(patterns)}")
        elif name == "WebSearch":
            queries = [fmt.code(inp.get("query", "")) for inp in inputs]
            lines.append(f"🌐 {fmt.bold('Search:')} {', '.join(queries)}")
        elif name == "WebFetch":
            count = len(inputs)
            label = f"🌐 {fmt.bold('Fetch')}"
            lines.append(f"{label} ×{count}" if count > 1 else label)
        else:
            count = len(inputs)
            label = f"🔧 {fmt.bold(name)}"
            lines.append(f"{label} ×{count}" if count > 1 else label)

    return "\n".join(lines)
