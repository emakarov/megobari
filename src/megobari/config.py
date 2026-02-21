"""Environment configuration loaded from .env."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_is_testing = "pytest" in sys.modules

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN and not _is_testing:
    print("ERROR: BOT_TOKEN environment variable is not set.")
    print("Copy .env.example to .env and fill in your bot token from @BotFather.")
    sys.exit(1)

_raw_allowed_user = os.getenv("ALLOWED_USER", "")
if not _raw_allowed_user and not _is_testing:
    print("ERROR: ALLOWED_USER environment variable is not set.")
    print("Set it to your Telegram username or numeric user ID in .env.")
    sys.exit(1)

ALLOWED_USER_ID: int | None = None
ALLOWED_USERNAME: str | None = None
if _raw_allowed_user:
    try:
        ALLOWED_USER_ID = int(_raw_allowed_user)
    except ValueError:
        ALLOWED_USERNAME = _raw_allowed_user.lstrip("@")
WORKING_DIR = os.getcwd()
SESSIONS_DIR = Path(WORKING_DIR) / ".megobari" / "sessions"
TELEGRAM_MAX_MESSAGE_LEN = 4096
