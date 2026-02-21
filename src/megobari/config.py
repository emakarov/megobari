"""Environment configuration loaded from .env, env vars, or programmatic input."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

TELEGRAM_MAX_MESSAGE_LEN = 4096


def _parse_allowed_user(raw: str) -> tuple[int | None, str | None]:
    """Parse allowed user string into (user_id, username) tuple."""
    if not raw:
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, raw.lstrip("@")


@dataclass
class Config:
    """Bot configuration. Can be built from env, CLI args, or programmatic input."""

    bot_token: str = ""
    allowed_user_id: int | None = None
    allowed_username: str | None = None
    working_dir: str = field(default_factory=os.getcwd)
    sessions_dir: Path | None = None

    def __post_init__(self):
        """Set default sessions_dir based on working_dir if not provided."""
        if self.sessions_dir is None:
            self.sessions_dir = Path(self.working_dir) / ".megobari" / "sessions"

    @classmethod
    def from_env(cls) -> Config:
        """Load config from environment variables and .env file."""
        load_dotenv()
        user_id, username = _parse_allowed_user(os.getenv("ALLOWED_USER", ""))
        return cls(
            bot_token=os.getenv("BOT_TOKEN", ""),
            allowed_user_id=user_id,
            allowed_username=username,
            working_dir=os.getcwd(),
        )

    @classmethod
    def from_args(
        cls,
        bot_token: str | None = None,
        allowed_user: str | None = None,
        cwd: str | None = None,
    ) -> Config:
        """Build config from explicit arguments, falling back to env."""
        env = cls.from_env()
        user_id, username = env.allowed_user_id, env.allowed_username
        if allowed_user is not None:
            user_id, username = _parse_allowed_user(allowed_user)
        return cls(
            bot_token=bot_token or env.bot_token,
            allowed_user_id=user_id,
            allowed_username=username,
            working_dir=cwd or env.working_dir,
        )

    def validate(self) -> list[str]:
        """Return list of validation errors, empty if config is valid."""
        errors = []
        if not self.bot_token:
            errors.append(
                "BOT_TOKEN is not set. "
                "Pass bot_token= or set BOT_TOKEN in env/.env."
            )
        if self.allowed_user_id is None and self.allowed_username is None:
            errors.append(
                "ALLOWED_USER is not set. "
                "Pass allowed_user= or set ALLOWED_USER in env/.env."
            )
        return errors

    @property
    def is_discovery_mode(self) -> bool:
        """True if no allowed user is configured (ID discovery mode)."""
        return self.allowed_user_id is None and self.allowed_username is None
