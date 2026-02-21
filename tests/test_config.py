"""Tests for configuration module."""

from __future__ import annotations

from unittest.mock import patch

from megobari.config import Config, _parse_allowed_user


class TestParseAllowedUser:
    def test_numeric_id(self):
        uid, uname = _parse_allowed_user("12345")
        assert uid == 12345
        assert uname is None

    def test_username_with_at(self):
        uid, uname = _parse_allowed_user("@myuser")
        assert uid is None
        assert uname == "myuser"

    def test_username_without_at(self):
        uid, uname = _parse_allowed_user("myuser")
        assert uid is None
        assert uname == "myuser"

    def test_empty_string(self):
        uid, uname = _parse_allowed_user("")
        assert uid is None
        assert uname is None


class TestConfig:
    def test_defaults(self):
        cfg = Config(bot_token="tok")
        assert cfg.bot_token == "tok"
        assert cfg.allowed_user_id is None
        assert cfg.allowed_username is None
        assert cfg.sessions_dir is not None

    def test_sessions_dir_default(self, tmp_path):
        cfg = Config(bot_token="tok", working_dir=str(tmp_path))
        assert cfg.sessions_dir == tmp_path / ".megobari" / "sessions"

    def test_sessions_dir_explicit(self, tmp_path):
        custom = tmp_path / "custom"
        cfg = Config(bot_token="tok", sessions_dir=custom)
        assert cfg.sessions_dir == custom

    def test_validate_no_token(self):
        cfg = Config()
        errors = cfg.validate()
        assert any("BOT_TOKEN" in e for e in errors)

    def test_validate_no_user(self):
        cfg = Config(bot_token="tok")
        errors = cfg.validate()
        assert any("ALLOWED_USER" in e for e in errors)

    def test_validate_ok_with_id(self):
        cfg = Config(bot_token="tok", allowed_user_id=123)
        assert cfg.validate() == []

    def test_validate_ok_with_username(self):
        cfg = Config(bot_token="tok", allowed_username="user")
        assert cfg.validate() == []

    def test_is_discovery_mode(self):
        cfg = Config(bot_token="tok")
        assert cfg.is_discovery_mode is True

    def test_not_discovery_mode(self):
        cfg = Config(bot_token="tok", allowed_user_id=123)
        assert cfg.is_discovery_mode is False

    @patch.dict("os.environ", {"BOT_TOKEN": "env-tok", "ALLOWED_USER": "999"})
    def test_from_env(self):
        cfg = Config.from_env()
        assert cfg.bot_token == "env-tok"
        assert cfg.allowed_user_id == 999

    @patch.dict("os.environ", {"BOT_TOKEN": "env-tok", "ALLOWED_USER": "@bob"})
    def test_from_env_username(self):
        cfg = Config.from_env()
        assert cfg.allowed_username == "bob"
        assert cfg.allowed_user_id is None

    @patch.dict("os.environ", {"BOT_TOKEN": "env-tok", "ALLOWED_USER": "999"})
    def test_from_args_overrides_env(self):
        cfg = Config.from_args(bot_token="arg-tok", allowed_user="@alice")
        assert cfg.bot_token == "arg-tok"
        assert cfg.allowed_username == "alice"
        assert cfg.allowed_user_id is None

    @patch.dict("os.environ", {"BOT_TOKEN": "env-tok", "ALLOWED_USER": "999"})
    def test_from_args_falls_back_to_env(self):
        cfg = Config.from_args()
        assert cfg.bot_token == "env-tok"
        assert cfg.allowed_user_id == 999

    def test_from_args_with_cwd(self, tmp_path):
        cfg = Config.from_args(
            bot_token="tok", allowed_user="123", cwd=str(tmp_path),
        )
        assert cfg.working_dir == str(tmp_path)
