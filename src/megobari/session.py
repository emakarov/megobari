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

_LAUNCH_DIR = os.getcwd()


@dataclass
class Session:
    name: str
    session_id: str | None = None
    streaming: bool = False
    permission_mode: PermissionMode = "default"
    cwd: str = field(default_factory=lambda: _LAUNCH_DIR)
    dirs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now_iso())
    last_used_at: str = field(default_factory=lambda: _now_iso())

    def touch(self) -> None:
        self.last_used_at = _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionManager:
    def __init__(self, sessions_dir: Path) -> None:
        self._sessions: dict[str, Session] = {}
        self._active_name: str | None = None
        self._sessions_dir = sessions_dir

    @property
    def current(self) -> Session | None:
        if self._active_name is None:
            return None
        return self._sessions.get(self._active_name)

    @property
    def active_name(self) -> str | None:
        return self._active_name

    def create(self, name: str) -> Session | None:
        if name in self._sessions:
            return None
        session = Session(name=name)
        self._sessions[name] = session
        self._active_name = name
        self._save()
        return session

    def get(self, name: str) -> Session | None:
        return self._sessions.get(name)

    def delete(self, name: str) -> bool:
        if name not in self._sessions:
            return False
        del self._sessions[name]
        if self._active_name == name:
            remaining = list(self._sessions.keys())
            self._active_name = remaining[0] if remaining else None
        self._save()
        return True

    def list_all(self) -> list[Session]:
        return list(self._sessions.values())

    def switch(self, name: str) -> Session | None:
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
