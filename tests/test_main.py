"""Tests for the application entry point."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMain:
    @patch("megobari.__main__.SessionManager")
    @patch("megobari.__main__.create_application")
    @patch("megobari.__main__.Config")
    @patch("sys.argv", ["megobari", "--bot-token=fake", "--allowed-user=123"])
    def test_main_runs(self, mock_config_cls, mock_create_app, mock_sm_cls):
        from megobari.__main__ import main

        mock_config = MagicMock()
        mock_config.validate.return_value = []
        mock_config.is_discovery_mode = False
        mock_config.working_dir = "/tmp"
        mock_config.sessions_dir = "/tmp/sessions"
        mock_config_cls.from_args.return_value = mock_config

        mock_sm = MagicMock()
        mock_sm_cls.return_value = mock_sm

        mock_app = MagicMock()
        mock_create_app.return_value = mock_app

        main()

        mock_sm.load_from_disk.assert_called_once()
        mock_create_app.assert_called_once_with(mock_sm, mock_config)
        mock_app.run_polling.assert_called_once()
