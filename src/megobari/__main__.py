import logging

from megobari.bot import create_application
from megobari.config import SESSIONS_DIR, WORKING_DIR
from megobari.session import SessionManager


def main():
    """Initialize and start the Telegram bot."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)

    logger.info("Working directory: %s", WORKING_DIR)
    logger.info("Sessions directory: %s", SESSIONS_DIR)

    session_manager = SessionManager(SESSIONS_DIR)
    session_manager.load_from_disk()

    app = create_application(session_manager)
    logger.info("Bot started. Polling for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
