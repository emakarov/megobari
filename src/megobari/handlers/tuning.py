"""Model and inference parameter command handlers."""

from __future__ import annotations

from megobari.session import (
    DEFAULT_AUTONOMOUS_MAX_TURNS,
    MODEL_ALIASES,
    VALID_EFFORT_LEVELS,
    VALID_THINKING_MODES,
)
from megobari.transport import TransportContext


async def cmd_think(ctx: TransportContext) -> None:
    """Handle /think command: control extended thinking."""
    fmt = ctx.formatter
    sm = ctx.session_manager
    session = sm.current

    args = ctx.args

    if not args:
        budget_info = ""
        if session.thinking == "enabled" and session.thinking_budget:
            budget_info = f" (budget: {session.thinking_budget:,} tokens)"
        msg = f"Thinking: {fmt.bold(session.thinking)}{budget_info}"
        await ctx.reply(msg, formatted=True)
        return

    mode = args[0].lower()

    if mode == "on":
        session.thinking = "enabled"
        budget = 10000
        if len(args) > 1:
            try:
                budget = int(args[1])
            except ValueError:
                await ctx.reply("Invalid budget. Use: /think on [budget_tokens]")
                return
        session.thinking_budget = budget
        sm._save()
        await ctx.reply(f"✅ Thinking enabled (budget: {budget:,} tokens)")
    elif mode == "off":
        session.thinking = "disabled"
        session.thinking_budget = None
        sm._save()
        await ctx.reply("✅ Thinking disabled")
    elif mode in VALID_THINKING_MODES:
        session.thinking = mode
        if mode != "enabled":
            session.thinking_budget = None
        sm._save()
        await ctx.reply(f"✅ Thinking: {mode}")
    else:
        await ctx.reply(
            "Usage:\n"
            "/think — show current setting\n"
            "/think adaptive — let Claude decide (default)\n"
            "/think on [budget] — enable with optional budget (default 10000)\n"
            "/think off — disable thinking",
        )


async def cmd_effort(ctx: TransportContext) -> None:
    """Handle /effort command: control effort level."""
    fmt = ctx.formatter
    sm = ctx.session_manager
    session = sm.current
    args = ctx.args

    if not args:
        level = session.effort or "not set (SDK default)"
        await ctx.reply(f"Effort: {fmt.bold(str(level))}", formatted=True)
        return

    level = args[0].lower()

    if level == "off":
        session.effort = None
        sm._save()
        await ctx.reply("✅ Effort cleared (using SDK default)")
    elif level in VALID_EFFORT_LEVELS:
        session.effort = level
        sm._save()
        await ctx.reply(f"✅ Effort: {level}")
    else:
        await ctx.reply(
            "Usage:\n"
            "/effort — show current setting\n"
            "/effort low|medium|high|max — set level\n"
            "/effort off — clear (use SDK default)",
        )


async def cmd_model(ctx: TransportContext) -> None:
    """Handle /model command: switch model for current session."""
    fmt = ctx.formatter
    sm = ctx.session_manager
    session = sm.current
    args = ctx.args

    if not args:
        current = session.model or "default (SDK decides)"
        aliases_list = ", ".join(sorted(MODEL_ALIASES.keys()))
        await ctx.reply(
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
        await ctx.reply("✅ Model cleared (SDK default)")
        return

    # Resolve alias
    resolved = MODEL_ALIASES.get(model, model)
    session.model = resolved
    sm._save()
    display = f"{model} → {resolved}" if model != resolved else resolved
    await ctx.reply(f"✅ Model: {display}")


async def cmd_autonomous(ctx: TransportContext) -> None:
    """Handle /autonomous command: toggle autonomous mode.

    Autonomous mode sets: bypassPermissions, max effort, high max_turns.
    """
    fmt = ctx.formatter
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return

    args = ctx.args

    if not args:
        # Show current status
        is_auto = (
            session.permission_mode == "bypassPermissions"
            and session.effort == "max"
            and session.max_turns is not None
            and session.max_turns >= DEFAULT_AUTONOMOUS_MAX_TURNS
        )
        status = "ON" if is_auto else "OFF"
        lines = [
            fmt.bold(f"Autonomous mode: {status}"),
            f"  Permissions: {session.permission_mode}",
            f"  Effort: {session.effort or 'default'}",
            f"  Max turns: {session.max_turns or 'default'}",
            f"  Budget: ${session.max_budget_usd:.2f}"
            if session.max_budget_usd else "  Budget: unlimited",
        ]
        await ctx.reply("\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub in ("on", "true", "1"):
        session.permission_mode = "bypassPermissions"
        session.effort = "max"
        session.max_turns = DEFAULT_AUTONOMOUS_MAX_TURNS
        sm._save()
        await ctx.reply(
            f"🚀 Autonomous mode ON\n"
            f"  Permissions: bypassPermissions\n"
            f"  Effort: max\n"
            f"  Max turns: {DEFAULT_AUTONOMOUS_MAX_TURNS}",
        )
    elif sub in ("off", "false", "0"):
        session.permission_mode = "default"
        session.effort = None
        session.max_turns = None
        session.max_budget_usd = None
        sm._save()
        await ctx.reply("✅ Autonomous mode OFF (defaults restored)")
    elif sub == "turns":
        if len(args) < 2:
            await ctx.reply(f"Max turns: {session.max_turns or 'default'}")
            return
        try:
            val = int(args[1])
            if val < 1:
                raise ValueError
            session.max_turns = val
            sm._save()
            await ctx.reply(f"✅ Max turns: {val}")
        except ValueError:
            await ctx.reply("Usage: /autonomous turns <number>")
    elif sub == "budget":
        if len(args) < 2:
            if session.max_budget_usd:
                await ctx.reply(f"Budget: ${session.max_budget_usd:.2f}")
            else:
                await ctx.reply("Budget: unlimited")
            return
        if args[1].lower() == "off":
            session.max_budget_usd = None
            sm._save()
            await ctx.reply("✅ Budget limit removed")
        else:
            try:
                val = float(args[1])
                if val <= 0:
                    raise ValueError
                session.max_budget_usd = val
                sm._save()
                await ctx.reply(f"✅ Budget: ${val:.2f}")
            except ValueError:
                await ctx.reply("Usage: /autonomous budget <amount|off>")
    else:
        await ctx.reply(
            "Usage:\n"
            "/autonomous — show current status\n"
            "/autonomous on — enable (bypass + max effort + 50 turns)\n"
            "/autonomous off — disable (restore defaults)\n"
            "/autonomous turns <n> — set max tool turns\n"
            "/autonomous budget <$|off> — set cost limit per query",
        )
