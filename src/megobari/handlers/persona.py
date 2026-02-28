"""Persona, MCP, skills, memory, and summaries command handlers."""

from __future__ import annotations

import json as _json

from telegram import Update
from telegram.ext import ContextTypes

from megobari.db import Repository, get_session
from megobari.mcp_config import discover_skills, list_available_servers

from ._common import _get_sm, _reply, fmt


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
            "/persona mcp <name> <server1,server2,...>\n"
            "/persona skills <name> <skill1,skill2,...>",
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
            f"Skills: {p.skills or '—'}",
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

    elif sub == "skills":
        if len(args) < 3:
            await _reply(
                update,
                "Usage: /persona skills <name> <skill1,skill2,...>"
            )
            return
        name = args[1]
        skill_list = [sk.strip() for sk in args[2].split(",")]
        async with get_session() as s:
            repo = Repository(s)
            p = await repo.update_persona(name, skills=skill_list)
        if not p:
            await _reply(update, f"Persona '{name}' not found.")
            return
        await _reply(
            update,
            f"Skills for '{name}' (priority order): {skill_list}"
        )

    else:
        await _reply(update, f"Unknown subcommand: {sub}. Use /persona for help.")


async def cmd_mcp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mcp command: list available MCP servers."""
    servers = list_available_servers()
    if not servers:
        await _reply(
            update,
            "No MCP servers found.\n"
            "Configure them in ~/.claude/mcp.json"
        )
        return
    lines = [fmt.bold("Available MCP servers:"), ""]
    for name in servers:
        lines.append(f"  {fmt.code(name)}")
    lines.append("")
    lines.append(
        "Assign to persona: /persona mcp <name> server1,server2"
    )
    await _reply(update, "\n".join(lines), formatted=True)


async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /skills command: list available Claude Code skills."""
    found = discover_skills()
    if not found:
        await _reply(
            update,
            "No skills found.\n"
            "Install skills in ~/.claude/skills/"
        )
        return
    lines = [fmt.bold("Available skills:"), ""]
    for name in found:
        lines.append(f"  {fmt.code(name)}")
    lines.append("")
    lines.append(
        "Assign to persona: /persona skills <name> skill1,skill2"
    )
    await _reply(update, "\n".join(lines), formatted=True)


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
