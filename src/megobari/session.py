"""Session management with JSON persistence."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

PermissionMode = Literal["default", "acceptEdits", "bypassPermissions"]
VALID_PERMISSION_MODES: set[str] = {"default", "acceptEdits", "bypassPermissions"}

ThinkingMode = Literal["adaptive", "enabled", "disabled"]
VALID_THINKING_MODES: set[str] = {"adaptive", "enabled", "disabled"}

EffortLevel = Literal["low", "medium", "high", "max"]
VALID_EFFORT_LEVELS: set[str] = {"low", "medium", "high", "max"}

# Default max_turns when autonomous mode is active.
DEFAULT_AUTONOMOUS_MAX_TURNS = 50

# Short aliases → full model names
MODEL_ALIASES: dict[str, str] = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-6",
    "haiku": "claude-haiku-4-20250414",
}
VALID_MODELS: set[str] = set(MODEL_ALIASES.keys()) | set(MODEL_ALIASES.values())

_LAUNCH_DIR = os.getcwd()


@dataclass
class Session:
    """Represents a single Claude Code session with configuration and metadata."""
    name: str
    session_id: str | None = None
    streaming: bool = False
    permission_mode: PermissionMode = "default"
    cwd: str = field(default_factory=lambda: _LAUNCH_DIR)
    dirs: list[str] = field(default_factory=list)
    thinking: ThinkingMode = "adaptive"
    thinking_budget: int | None = None
    effort: EffortLevel | None = None
    model: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    created_at: str = field(default_factory=lambda: _now_iso())
    last_used_at: str = field(default_factory=lambda: _now_iso())

    def touch(self) -> None:
        """Update the last_used_at timestamp to the current time."""
        self.last_used_at = _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionManager:
    """Manages Claude Code sessions with persistence and switching capabilities."""
    def __init__(self, sessions_dir: Path) -> None:
        self._sessions: dict[str, Session] = {}
        self._active_name: str | None = None
        self._sessions_dir = sessions_dir

    @property
    def current(self) -> Session | None:
        """Return the currently active session, or None if no session is active."""
        if self._active_name is None:
            return None
        return self._sessions.get(self._active_name)

    @property
    def active_name(self) -> str | None:
        """Return the name of the currently active session, or None if no session is active."""
        return self._active_name

    def create(self, name: str) -> Session | None:
        """Create a new session with the given name. Returns None if the name already exists."""
        if name in self._sessions:
            return None
        session = Session(name=name)
        self._sessions[name] = session
        self._active_name = name
        self._save()
        return session

    def get(self, name: str) -> Session | None:
        """Retrieve a session by name, or None if it does not exist."""
        return self._sessions.get(name)

    def delete(self, name: str) -> bool:
        """Delete a session by name.

        Returns True on success, False if not found.
        """
        if name not in self._sessions:
            return False
        del self._sessions[name]
        if self._active_name == name:
            remaining = list(self._sessions.keys())
            self._active_name = remaining[0] if remaining else None
        self._save()
        return True

    def list_all(self) -> list[Session]:
        """Return a list of all sessions."""
        return list(self._sessions.values())

    def switch(self, name: str) -> Session | None:
        """Switch the active session to the given name.

        Returns the session or None if not found.
        """
        session = self._sessions.get(name)
        if session is None:
            return None
        self._active_name = name
        self._save()
        return session

    def rename(self, old_name: str, new_name: str) -> str | None:
        """Rename a session. Returns error message or None on success."""
        if old_name not in self._sessions:
            return f"Session '{old_name}' not found."
        if new_name in self._sessions:
            return f"Session '{new_name}' already exists."
        session = self._sessions.pop(old_name)
        session.name = new_name
        self._sessions[new_name] = session
        if self._active_name == old_name:
            self._active_name = new_name
        self._save()
        return None

    def update_session_id(self, name: str, session_id: str) -> None:
        """Update the session_id for a session and touch its last_used_at timestamp."""
        session = self._sessions.get(name)
        if session:
            session.session_id = session_id
            session.touch()
            self._save()

    def _save(self) -> None:
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._sessions_dir / "sessions.json"
        data = {
            "active_session": self._active_name,
            "sessions": {
                name: asdict(session) for name, session in self._sessions.items()
            },
        }
        path.write_text(json.dumps(data, indent=2))

    def load_from_disk(self) -> None:
        """Load sessions from the sessions.json file on disk."""
        path = self._sessions_dir / "sessions.json"
        if not path.exists():
            logger.info("No sessions file found, starting fresh.")
            return
        try:
            data = json.loads(path.read_text())
            self._active_name = data.get("active_session")
            self._sessions = {}
            for name, sdata in data.get("sessions", {}).items():
                self._sessions[name] = Session(**sdata)
            logger.info(
                "Loaded %d session(s), active: %s",
                len(self._sessions),
                self._active_name,
            )
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error("Failed to load sessions: %s", e)
