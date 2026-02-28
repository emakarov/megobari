"""Model and inference parameter command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from megobari.session import (
    DEFAULT_AUTONOMOUS_MAX_TURNS,
    MODEL_ALIASES,
    VALID_EFFORT_LEVELS,
    VALID_THINKING_MODES,
)

from ._common import _get_sm, _reply, fmt


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


async def cmd_autonomous(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /autonomous command: toggle autonomous mode.

    Autonomous mode sets: bypassPermissions, max effort, high max_turns.
    """
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return

    args = context.args or []

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
        await _reply(update, "\n".join(lines), formatted=True)
        return

    sub = args[0].lower()

    if sub in ("on", "true", "1"):
        session.permission_mode = "bypassPermissions"
        session.effort = "max"
        session.max_turns = DEFAULT_AUTONOMOUS_MAX_TURNS
        sm._save()
        await _reply(
            update,
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
        await _reply(update, "✅ Autonomous mode OFF (defaults restored)")
    elif sub == "turns":
        if len(args) < 2:
            await _reply(update, f"Max turns: {session.max_turns or 'default'}")
            return
        try:
            val = int(args[1])
            if val < 1:
                raise ValueError
            session.max_turns = val
            sm._save()
            await _reply(update, f"✅ Max turns: {val}")
        except ValueError:
            await _reply(update, "Usage: /autonomous turns <number>")
    elif sub == "budget":
        if len(args) < 2:
            if session.max_budget_usd:
                await _reply(update, f"Budget: ${session.max_budget_usd:.2f}")
            else:
                await _reply(update, "Budget: unlimited")
            return
        if args[1].lower() == "off":
            session.max_budget_usd = None
            sm._save()
            await _reply(update, "✅ Budget limit removed")
        else:
            try:
                val = float(args[1])
                if val <= 0:
                    raise ValueError
                session.max_budget_usd = val
                sm._save()
                await _reply(update, f"✅ Budget: ${val:.2f}")
            except ValueError:
                await _reply(update, "Usage: /autonomous budget <amount|off>")
    else:
        await _reply(
            update,
            "Usage:\n"
            "/autonomous — show current status\n"
            "/autonomous on — enable (bypass + max effort + 50 turns)\n"
            "/autonomous off — disable (restore defaults)\n"
            "/autonomous turns <n> — set max tool turns\n"
            "/autonomous budget <$|off> — set cost limit per query",
        )
