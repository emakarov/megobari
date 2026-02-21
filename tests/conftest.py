"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from megobari.session import Session, SessionManager


@pytest.fixture
def tmp_sessions_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for session storage."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def session_manager(tmp_sessions_dir: Path) -> SessionManager:
    """Provide a fresh SessionManager with temp storage."""
    return SessionManager(tmp_sessions_dir)


@pytest.fixture
def sample_session() -> Session:
    """Provide a sample session for testing."""
    return Session(name="test-session")
