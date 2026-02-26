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
    thinking_val = session.thinking
    if session.thinking == "enabled" and session.thinking_budget:
        thinking_val = f"enabled ({session.thinking_budget:,} tokens)"
    lines += [
        line("Streaming", "on" if session.streaming else "off"),
        line("Permissions", session.permission_mode),
        line("Model", session.model or "default"),
        line("Thinking", thinking_val),
        line("Effort", session.effort or "default"),
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
        (f"/file {fmt.code('<path>')}", "Send a file to Telegram"),
        ("/restart", "Restart the bot process"),
        (f"/release {fmt.code('<version>')}", "Bump version, tag & publish to PyPI"),
        (f"/persona {fmt.code('<sub>')}", "Manage personas (list, create, default, ...)"),
        (f"/memory {fmt.code('<sub>')}", "Manage memories (list, set, get, delete)"),
        (f"/summaries {fmt.code('[sub]')}", "View conversation summaries"),
        (f"/model {fmt.code('[name]')}", "Switch model (sonnet/opus/haiku/off)"),
        (f"/think {fmt.code('[mode]')}", "Control extended thinking (adaptive/on/off)"),
        (f"/effort {fmt.code('[level]')}", "Set effort level (low/medium/high/max/off)"),
        ("/usage", "Show session cost and stats"),
        ("/context", "Show token usage and session config"),
        ("/history", "Browse past conversations"),
        ("/compact", "Summarize and reset context"),
        ("/doctor", "Run health checks"),
        ("/help", "Show this message"),
    ]
    lines = [title, ""]
    for cmd, desc in cmds:
        lines.append(f"{cmd} — {fmt.escape(desc)}")
    return "\n".join(lines)


def tool_status_text(tool_name: str, tool_input: dict) -> str:
    """Return a short status line for a tool use event.

    Used to show live progress in the placeholder message while the agent works.
    """
    if tool_name in ("Read", "Write", "Edit"):
        filename = PurePosixPath(tool_input.get("file_path", "")).name or "file"
        verbs = {"Read": "Reading", "Write": "Writing", "Edit": "Editing"}
        return f"\u270f\ufe0f {verbs[tool_name]} {filename}..."
    if tool_name == "Glob":
        return "\U0001f50d Searching files..."
    if tool_name == "Grep":
        return "\U0001f50d Searching codebase..."
    if tool_name == "Bash":
        desc = tool_input.get("description", "")
        if desc:
            short = desc[:40] + ("..." if len(desc) > 40 else "")
            return f"\u26a1 {short}"
        return "\u26a1 Running command..."
    if tool_name == "WebSearch":
        return "\U0001f310 Searching web..."
    if tool_name == "WebFetch":
        return "\U0001f310 Fetching page..."
    if tool_name == "Task":
        return "\U0001f916 Launching agent..."
    if tool_name == "TodoWrite":
        return "\U0001f4cb Updating tasks..."
    return f"\U0001f527 {tool_name}..."


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
