"""Entry point for the Megobari Telegram bot."""

import argparse
import logging
import sys

from megobari.bot import create_application
from megobari.config import Config
from megobari.session import SessionManager


def main():
    """Initialize and start the Telegram bot."""
    parser = argparse.ArgumentParser(
        description="Megobari — Telegram bot bridging to Claude Code",
    )
    parser.add_argument("--bot-token", help="Telegram bot token")
    parser.add_argument(
        "--allowed-user",
        help="Telegram user ID or @username",
    )
    parser.add_argument("--cwd", help="Working directory")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)

    config = Config.from_args(
        bot_token=args.bot_token,
        allowed_user=args.allowed_user,
        cwd=args.cwd,
    )

    errors = config.validate()
    if errors and not config.is_discovery_mode:
        for err in errors:
            logger.error(err)
        sys.exit(1)

    logger.info("Working directory: %s", config.working_dir)
    logger.info("Sessions directory: %s", config.sessions_dir)

    session_manager = SessionManager(config.sessions_dir)
    session_manager.load_from_disk()

    app = create_application(session_manager, config)
    logger.info("Bot started. Polling for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
