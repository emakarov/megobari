"""Handler for /dashboard command — manage dashboard API tokens."""

from __future__ import annotations

import logging
import secrets

from megobari.db.engine import get_session
from megobari.db.repository import Repository
from megobari.transport import TransportContext

logger = logging.getLogger(__name__)


async def cmd_dashboard(ctx: TransportContext) -> None:
    """Manage dashboard API tokens.

    Usage:
      /dashboard              — list all tokens
      /dashboard add <name>   — create a new token for <name>
      /dashboard disable <id> — disable token by ID
      /dashboard enable <id>  — enable token by ID
      /dashboard revoke <id>  — permanently delete token by ID
    """
    args = ctx.args
    if not args:
        await _list_tokens(ctx)
        return

    subcommand = args[0].lower()

    if subcommand == "add":
        if len(args) < 2:
            await ctx.reply("Usage: /dashboard add <name>")
            return
        name = " ".join(args[1:])
        await _add_token(ctx, name)

    elif subcommand == "disable":
        if len(args) < 2:
            await ctx.reply("Usage: /dashboard disable <id>")
            return
        await _toggle_token(ctx, args[1], enabled=False)

    elif subcommand == "enable":
        if len(args) < 2:
            await ctx.reply("Usage: /dashboard enable <id>")
            return
        await _toggle_token(ctx, args[1], enabled=True)

    elif subcommand == "revoke":
        if len(args) < 2:
            await ctx.reply("Usage: /dashboard revoke <id>")
            return
        await _revoke_token(ctx, args[1])

    else:
        await ctx.reply(
            "Unknown subcommand. Use: add, disable, enable, revoke"
        )


async def _list_tokens(ctx: TransportContext) -> None:
    async with get_session() as session:
        repo = Repository(session)
        tokens = await repo.list_dashboard_tokens()

    if not tokens:
        await ctx.reply(
            "No dashboard tokens.\n"
            "Create one with: /dashboard add <name>"
        )
        return

    lines = ["<b>Dashboard Tokens</b>\n"]
    for t in tokens:
        status = "enabled" if t.enabled else "disabled"
        used = t.last_used_at.strftime("%Y-%m-%d %H:%M") if t.last_used_at else "never"
        lines.append(
            f"  <b>#{t.id}</b> {t.name}\n"
            f"    Prefix: <code>{t.token_prefix}...</code> | "
            f"Status: {status} | Last used: {used}"
        )

    await ctx.reply("\n".join(lines), formatted=True)


async def _add_token(ctx: TransportContext, name: str) -> None:
    token = secrets.token_urlsafe(32)

    async with get_session() as session:
        repo = Repository(session)
        dt = await repo.create_dashboard_token(name, token)

    await ctx.reply(
        f"<b>New dashboard token created</b>\n\n"
        f"Name: {name}\n"
        f"ID: #{dt.id}\n\n"
        f"<code>{token}</code>\n\n"
        f"Copy this token now — it won't be shown again.",
        formatted=True,
    )


async def _toggle_token(ctx: TransportContext, id_str: str, enabled: bool) -> None:
    try:
        token_id = int(id_str)
    except ValueError:
        await ctx.reply("Token ID must be a number.")
        return

    async with get_session() as session:
        repo = Repository(session)
        dt = await repo.toggle_dashboard_token(token_id, enabled)

    if dt is None:
        await ctx.reply(f"Token #{token_id} not found.")
        return

    action = "enabled" if enabled else "disabled"
    await ctx.reply(f"Token #{dt.id} ({dt.name}) {action}.")


async def _revoke_token(ctx: TransportContext, id_str: str) -> None:
    try:
        token_id = int(id_str)
    except ValueError:
        await ctx.reply("Token ID must be a number.")
        return

    async with get_session() as session:
        repo = Repository(session)
        deleted = await repo.delete_dashboard_token(token_id)

    if not deleted:
        await ctx.reply(f"Token #{token_id} not found.")
        return

    await ctx.reply(f"Token #{token_id} permanently revoked.")
