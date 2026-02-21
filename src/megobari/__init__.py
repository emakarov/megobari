"""Megobari — Telegram bot bridging to Claude Code.

Library API::

    from megobari import MegobariBot

    bot = MegobariBot(
        bot_token="123:ABC",
        allowed_user="12345",
    )
    bot.run()
"""

from __future__ import annotations

import logging

from megobari.bot import create_application
from megobari.config import Config
from megobari.session import SessionManager

__all__ = ["MegobariBot", "Config"]


class MegobariBot:
    """High-level API for running Megobari as a library.

    Args:
        bot_token: Telegram bot token from @BotFather.
        allowed_user: Telegram user ID (int or str) or @username.
        working_dir: Working directory for Claude Code sessions.
        sessions_dir: Directory for session persistence. Defaults to
            ``<working_dir>/.megobari/sessions``.
    """

    def __init__(
        self,
        bot_token: str,
        allowed_user: str | int | None = None,
        working_dir: str | None = None,
        sessions_dir: str | None = None,
    ):
        raw_user = str(allowed_user) if allowed_user is not None else None
        self.config = Config.from_args(
            bot_token=bot_token,
            allowed_user=raw_user,
            cwd=working_dir,
        )
        if sessions_dir is not None:
            from pathlib import Path
            self.config.sessions_dir = Path(sessions_dir)

        self._session_manager = SessionManager(self.config.sessions_dir)

    def run(self) -> None:
        """Start the bot (blocking). Polls Telegram for messages."""
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            level=logging.INFO,
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logger = logging.getLogger(__name__)

        errors = self.config.validate()
        if errors and not self.config.is_discovery_mode:
            raise ValueError("; ".join(errors))

        self._session_manager.load_from_disk()
        logger.info("Working directory: %s", self.config.working_dir)
        logger.info("Sessions directory: %s", self.config.sessions_dir)

        app = create_application(self._session_manager, self.config)
        logger.info("Bot started. Polling for messages...")
        app.run_polling()
