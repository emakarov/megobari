"""Tests for session management."""

from __future__ import annotations

from pathlib import Path

from megobari.session import Session, SessionManager


class TestSession:
    def test_create_session(self):
        s = Session(name="demo")
        assert s.name == "demo"
        assert s.session_id is None
        assert s.streaming is False
        assert s.permission_mode == "default"
        assert s.cwd
        assert s.dirs == []
        assert s.created_at
        assert s.last_used_at

    def test_touch_updates_last_used(self):
        s = Session(name="demo")
        original = s.last_used_at
        s.touch()
        assert s.last_used_at >= original


class TestSessionManager:
    def test_create(self, session_manager: SessionManager):
        s = session_manager.create("alpha")
        assert s is not None
        assert s.name == "alpha"
        assert session_manager.active_name == "alpha"
        assert session_manager.current is s

    def test_create_duplicate(self, session_manager: SessionManager):
        session_manager.create("alpha")
        assert session_manager.create("alpha") is None

    def test_switch(self, session_manager: SessionManager):
        session_manager.create("a")
        session_manager.create("b")
        assert session_manager.active_name == "b"

        s = session_manager.switch("a")
        assert s is not None
        assert session_manager.active_name == "a"

    def test_switch_nonexistent(self, session_manager: SessionManager):
        assert session_manager.switch("nope") is None

    def test_delete(self, session_manager: SessionManager):
        session_manager.create("a")
        session_manager.create("b")
        assert session_manager.delete("a") is True
        assert session_manager.get("a") is None
        assert len(session_manager.list_all()) == 1

    def test_delete_active_switches(self, session_manager: SessionManager):
        session_manager.create("a")
        session_manager.create("b")
        session_manager.switch("a")
        session_manager.delete("a")
        assert session_manager.active_name == "b"

    def test_delete_nonexistent(self, session_manager: SessionManager):
        assert session_manager.delete("nope") is False

    def test_delete_last(self, session_manager: SessionManager):
        session_manager.create("only")
        session_manager.delete("only")
        assert session_manager.active_name is None
        assert session_manager.current is None

    def test_rename(self, session_manager: SessionManager):
        session_manager.create("old")
        err = session_manager.rename("old", "new")
        assert err is None
        assert session_manager.get("old") is None
        assert session_manager.get("new") is not None
        assert session_manager.active_name == "new"

    def test_rename_nonexistent(self, session_manager: SessionManager):
        err = session_manager.rename("nope", "new")
        assert err is not None

    def test_rename_conflict(self, session_manager: SessionManager):
        session_manager.create("a")
        session_manager.create("b")
        err = session_manager.rename("a", "b")
        assert err is not None

    def test_list_all(self, session_manager: SessionManager):
        session_manager.create("a")
        session_manager.create("b")
        names = [s.name for s in session_manager.list_all()]
        assert "a" in names
        assert "b" in names

    def test_update_session_id(self, session_manager: SessionManager):
        session_manager.create("s")
        session_manager.update_session_id("s", "sid-123")
        s = session_manager.get("s")
        assert s.session_id == "sid-123"

    def test_persistence(self, tmp_sessions_dir: Path):
        sm1 = SessionManager(tmp_sessions_dir)
        sm1.create("persisted")
        sm1.update_session_id("persisted", "sid-abc")

        sm2 = SessionManager(tmp_sessions_dir)
        sm2.load_from_disk()
        s = sm2.get("persisted")
        assert s is not None
        assert s.session_id == "sid-abc"
        assert sm2.active_name == "persisted"
