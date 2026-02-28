"""Telegram bot application factory.

All handler logic lives in megobari.handlers.*.
This module wires handlers via telegram_handler() adapter and provides
the create_application() factory.

Handler names are re-exported for backward compatibility with tests.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from megobari.config import Config
from megobari.db import init_db

# Re-export everything from handlers for backward compatibility.
# Tests do `from megobari.bot import cmd_start` etc.
from megobari.handlers import (  # noqa: F401
    SessionUsage,
    StreamingAccumulator,
    _accumulate_usage,
    _busy_emoji,
    _busy_sessions,
    _persist_usage,
    _process_prompt,
    _send_typing_periodically,
    _track_user,
    cmd_autonomous,
    cmd_cd,
    cmd_compact,
    cmd_context,
    cmd_cron,
    cmd_current,
    cmd_dashboard,
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
    cmd_migrate,
    cmd_model,
    cmd_monitor,
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
    handle_document,
    handle_message,
    handle_photo,
    handle_voice,
)
from megobari.session import SessionManager
from megobari.telegram_transport import telegram_handler

logger = logging.getLogger(__name__)


# -- Application factory --


async def _cmd_discover_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Used when ALLOWED_USER_ID is not set — tells the user their ID."""
    user = update.effective_user
    logger.info(
        "User ID discovery: id=%s username=%s", user.id, user.username
    )
    await update.message.reply_text(
        f"Your Telegram user ID is: {user.id}\n\n"
        f"Set this in your .env file as:\n"
        f"ALLOWED_USER_ID={user.id}\n\n"
        f"Then restart the bot."
    )


def create_application(
    session_manager: SessionManager, config: Config
) -> Application:
    """Create and configure the Telegram application with handlers."""
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
        logger.warning(
            "ALLOWED_USER not set — running in ID discovery mode."
        )
        app.add_handler(MessageHandler(filters.ALL, _cmd_discover_id))
        return app

    # Wrap each TransportContext handler for python-telegram-bot dispatch.
    _w = telegram_handler

    _cmds = {
        "start": cmd_start,
        "new": cmd_new,
        "sessions": cmd_sessions,
        "switch": cmd_switch,
        "delete": cmd_delete,
        "rename": cmd_rename,
        "cd": cmd_cd,
        "dirs": cmd_dirs,
        "file": cmd_file,
        "help": cmd_help,
        "stream": cmd_stream,
        "permissions": cmd_permissions,
        "current": cmd_current,
        "restart": cmd_restart,
        "release": cmd_release,
        "persona": cmd_persona,
        "mcp": cmd_mcp,
        "skills": cmd_skills,
        "memory": cmd_memory,
        "summaries": cmd_summaries,
        "think": cmd_think,
        "effort": cmd_effort,
        "usage": cmd_usage,
        "compact": cmd_compact,
        "doctor": cmd_doctor,
        "migrate": cmd_migrate,
        "model": cmd_model,
        "context": cmd_context,
        "history": cmd_history,
        "autonomous": cmd_autonomous,
        "cron": cmd_cron,
        "heartbeat": cmd_heartbeat,
        "monitor": cmd_monitor,
        "dashboard": cmd_dashboard,
    }

    for name, handler in _cmds.items():
        app.add_handler(
            CommandHandler(name, _w(handler), filters=user_filter)
        )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & user_filter,
            _w(handle_message),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.VOICE & user_filter,
            _w(handle_voice),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO & user_filter,
            _w(handle_photo),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Document.ALL & user_filter,
            _w(handle_document),
        )
    )

    async def _post_init(application: Application) -> None:
        """Initialize DB, start dashboard, and send restart notification."""
        await init_db()
        logger.info("Database initialized at ~/.megobari/megobari.db")

        # Store bot reference for scheduler access
        application.bot_data["_bot"] = application.bot

        # Start dashboard API server (optional)
        if config.dashboard_port:
            try:
                from megobari.api.app import create_api, start_api_server

                api = create_api(
                    bot_data=application.bot_data,
                    session_manager=session_manager,
                )
                await start_api_server(api, port=config.dashboard_port)
                logger.info(
                    "Dashboard API started on port %d",
                    config.dashboard_port,
                )
            except ImportError:
                logger.warning(
                    "Dashboard dependencies not installed "
                    "(pip install megobari[dashboard])"
                )
            except Exception:
                logger.error("Failed to start dashboard API", exc_info=True)

        from megobari.actions import load_restart_marker

        chat_id = load_restart_marker()
        if chat_id:
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Bot restarted successfully.",
                )
            except Exception:
                logger.warning("Failed to send restart notification")
            try:
                from megobari.summarizer import log_message

                session_name = session_manager.current.name if session_manager.current else "main"
                await log_message(session_name, "assistant", "✅ Bot restarted successfully.")
            except Exception:
                logger.debug("Failed to log restart message")

    app.post_init = _post_init

    return app
