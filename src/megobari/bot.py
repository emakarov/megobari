"""Telegram bot application factory.

All handler logic has been moved to megobari.handlers.*.
This module re-exports handler names for backward compatibility
and provides the create_application() factory.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from megobari.config import Config
from megobari.db import init_db

# Re-export everything from handlers for backward compatibility.
# This ensures `from megobari.bot import cmd_start` etc. keep working.
from megobari.handlers import (  # noqa: F401
    SessionUsage,
    StreamingAccumulator,
    _accumulate_usage,
    _busy_emoji,
    _busy_sessions,
    _get_sm,
    _persist_usage,
    _process_prompt,
    _reply,
    _send_typing_periodically,
    _set_reaction,
    _track_user,
    cmd_autonomous,
    cmd_cd,
    cmd_compact,
    cmd_context,
    cmd_cron,
    cmd_current,
    cmd_delete,
    cmd_dirs,
    cmd_doctor,
    cmd_effort,
    cmd_file,
    cmd_heartbeat,
    cmd_help,
    cmd_history,
    cmd_mcp,
    cmd_memory,
    cmd_model,
    cmd_new,
    cmd_permissions,
    cmd_persona,
    cmd_release,
    cmd_rename,
    cmd_restart,
    cmd_sessions,
    cmd_skills,
    cmd_start,
    cmd_stream,
    cmd_summaries,
    cmd_switch,
    cmd_think,
    cmd_usage,
    fmt,
    handle_document,
    handle_message,
    handle_photo,
    handle_voice,
)
from megobari.session import SessionManager

logger = logging.getLogger(__name__)


# -- Application factory --


async def _cmd_discover_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Used when ALLOWED_USER_ID is not set — tells the user their numeric ID."""
    user = update.effective_user
    logger.info("User ID discovery: id=%s username=%s", user.id, user.username)
    await update.message.reply_text(
        f"Your Telegram user ID is: {user.id}\n\n"
        f"Set this in your .env file as:\n"
        f"ALLOWED_USER_ID={user.id}\n\n"
        f"Then restart the bot."
    )


def create_application(session_manager: SessionManager, config: Config) -> Application:
    """Create and configure the Telegram application with command handlers."""
    app = (
        Application.builder()
        .token(config.bot_token)
        .concurrent_updates(True)
        .build()
    )
    app.bot_data["session_manager"] = session_manager
    app.bot_data["config"] = config

    if config.allowed_user_id is not None:
        user_filter = filters.User(user_id=config.allowed_user_id)
    elif config.allowed_username is not None:
        user_filter = filters.User(username=config.allowed_username)
    else:
        logger.warning("ALLOWED_USER not set — running in ID discovery mode.")
        app.add_handler(MessageHandler(filters.ALL, _cmd_discover_id))
        return app

    app.add_handler(CommandHandler("start", cmd_start, filters=user_filter))
    app.add_handler(CommandHandler("new", cmd_new, filters=user_filter))
    app.add_handler(CommandHandler("sessions", cmd_sessions, filters=user_filter))
    app.add_handler(CommandHandler("switch", cmd_switch, filters=user_filter))
    app.add_handler(CommandHandler("delete", cmd_delete, filters=user_filter))
    app.add_handler(CommandHandler("rename", cmd_rename, filters=user_filter))
    app.add_handler(CommandHandler("cd", cmd_cd, filters=user_filter))
    app.add_handler(CommandHandler("dirs", cmd_dirs, filters=user_filter))
    app.add_handler(CommandHandler("file", cmd_file, filters=user_filter))
    app.add_handler(CommandHandler("help", cmd_help, filters=user_filter))
    app.add_handler(CommandHandler("stream", cmd_stream, filters=user_filter))
    app.add_handler(CommandHandler("permissions", cmd_permissions, filters=user_filter))
    app.add_handler(CommandHandler("current", cmd_current, filters=user_filter))
    app.add_handler(CommandHandler("restart", cmd_restart, filters=user_filter))
    app.add_handler(CommandHandler("release", cmd_release, filters=user_filter))
    app.add_handler(CommandHandler("persona", cmd_persona, filters=user_filter))
    app.add_handler(CommandHandler("mcp", cmd_mcp, filters=user_filter))
    app.add_handler(CommandHandler("skills", cmd_skills, filters=user_filter))
    app.add_handler(CommandHandler("memory", cmd_memory, filters=user_filter))
    app.add_handler(CommandHandler("summaries", cmd_summaries, filters=user_filter))
    app.add_handler(CommandHandler("think", cmd_think, filters=user_filter))
    app.add_handler(CommandHandler("effort", cmd_effort, filters=user_filter))
    app.add_handler(CommandHandler("usage", cmd_usage, filters=user_filter))
    app.add_handler(CommandHandler("compact", cmd_compact, filters=user_filter))
    app.add_handler(CommandHandler("doctor", cmd_doctor, filters=user_filter))
    app.add_handler(CommandHandler("model", cmd_model, filters=user_filter))
    app.add_handler(CommandHandler("context", cmd_context, filters=user_filter))
    app.add_handler(CommandHandler("history", cmd_history, filters=user_filter))
    app.add_handler(CommandHandler("autonomous", cmd_autonomous, filters=user_filter))
    app.add_handler(CommandHandler("cron", cmd_cron, filters=user_filter))
    app.add_handler(CommandHandler("heartbeat", cmd_heartbeat, filters=user_filter))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & user_filter,
            handle_message,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.VOICE & user_filter,
            handle_voice,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO & user_filter,
            handle_photo,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Document.ALL & user_filter,
            handle_document,
        )
    )

    async def _post_init(application: Application) -> None:
        """Initialize DB and send restart notification."""
        await init_db()
        logger.info("Database initialized at ~/.megobari/megobari.db")

        from megobari.actions import load_restart_marker

        chat_id = load_restart_marker()
        if chat_id:
            try:
                await application.bot.send_message(
                    chat_id=chat_id, text="✅ Bot restarted successfully."
                )
            except Exception:
                logger.warning("Failed to send restart notification")

    app.post_init = _post_init

    return app
