"""Tests for voice message transcription (all mocked, no faster-whisper needed)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.formatting import TelegramFormatter

# -- Transcriber tests --


class TestTranscriber:
    def test_transcribe_joins_segments(self):
        from megobari.voice import Transcriber

        mock_model = MagicMock()
        seg1 = MagicMock()
        seg1.text = " Hello "
        seg2 = MagicMock()
        seg2.text = " world "
        mock_info = MagicMock()
        mock_info.duration = 2.5
        mock_info.language = "en"
        mock_model.transcribe.return_value = ([seg1, seg2], mock_info)

        t = Transcriber(model_size="small")
        t._model = mock_model  # skip actual model loading
        result = t.transcribe("/tmp/audio.ogg")

        assert result == "Hello world"
        mock_model.transcribe.assert_called_once_with("/tmp/audio.ogg", beam_size=5)

    def test_transcribe_empty_segments(self):
        from megobari.voice import Transcriber

        mock_model = MagicMock()
        mock_info = MagicMock()
        mock_info.duration = 0.5
        mock_info.language = "en"
        mock_model.transcribe.return_value = ([], mock_info)

        t = Transcriber()
        t._model = mock_model
        result = t.transcribe("/tmp/silence.ogg")

        assert result == ""

    def test_ensure_model_noop_when_loaded(self):
        from megobari.voice import Transcriber

        t = Transcriber(model_size="tiny")
        mock_model = MagicMock()
        t._model = mock_model

        t._ensure_model()
        t._ensure_model()
        assert t._model is mock_model

    def test_ensure_model_loads_via_import(self):
        from megobari.voice import Transcriber

        mock_whisper_cls = MagicMock()
        mock_fw = MagicMock()
        mock_fw.WhisperModel = mock_whisper_cls

        t = Transcriber(model_size="tiny")

        with patch("megobari.voice._check_dependency"), \
             patch.dict("sys.modules", {"faster_whisper": mock_fw}):
            t._ensure_model()

        mock_whisper_cls.assert_called_once_with(
            "tiny", device="cpu", compute_type="int8"
        )


class TestIsAvailable:
    def test_returns_bool(self):
        from megobari.voice import is_available

        result = is_available()
        assert isinstance(result, bool)


class TestGetTranscriber:
    def test_singleton(self):
        import megobari.voice as voice_mod

        voice_mod._transcriber = None
        t1 = voice_mod.get_transcriber("small")
        t2 = voice_mod.get_transcriber("small")
        assert t1 is t2
        voice_mod._transcriber = None

    def test_creates_with_model_size(self):
        import megobari.voice as voice_mod

        voice_mod._transcriber = None
        t = voice_mod.get_transcriber("tiny")
        assert t._model_size == "tiny"
        voice_mod._transcriber = None


class TestCheckDependency:
    def test_raises_with_hint_when_missing(self):
        from megobari.voice import _check_dependency

        with patch.dict("sys.modules", {"faster_whisper": None}):
            with pytest.raises(ImportError, match="faster-whisper"):
                _check_dependency()

    def test_passes_when_available(self):
        from megobari.voice import _check_dependency

        with patch.dict("sys.modules", {"faster_whisper": MagicMock()}):
            _check_dependency()  # should not raise


# -- Voice handler tests --


class MockTransport:
    """Lightweight mock implementing TransportContext interface for voice tests."""

    def __init__(self, session_manager=None, bot_data=None):
        self._session_manager = session_manager
        self._formatter = TelegramFormatter()
        self._bot_data = bot_data if bot_data is not None else {}
        if session_manager and "session_manager" not in self._bot_data:
            self._bot_data["session_manager"] = session_manager

        self.reply = AsyncMock(return_value=MagicMock())
        self.reply_document = AsyncMock()
        self.reply_photo = AsyncMock()
        self.send_message = AsyncMock()
        self.edit_message = AsyncMock()
        self.delete_message = AsyncMock()
        self.send_typing = AsyncMock()
        self.set_reaction = AsyncMock()
        self.download_photo = AsyncMock(return_value=None)
        self.download_document = AsyncMock(return_value=None)
        self.download_voice = AsyncMock(return_value=None)

    @property
    def args(self):
        return []

    @property
    def text(self):
        return None

    @property
    def chat_id(self):
        return 12345

    @property
    def message_id(self):
        return 99

    @property
    def user_id(self):
        return 12345

    @property
    def username(self):
        return "testuser"

    @property
    def first_name(self):
        return "Test"

    @property
    def last_name(self):
        return "User"

    @property
    def caption(self):
        return None

    @property
    def session_manager(self):
        return self._session_manager

    @property
    def formatter(self):
        return self._formatter

    @property
    def bot_data(self):
        return self._bot_data

    @property
    def transport_name(self):
        return "test"

    @property
    def max_message_length(self):
        return 4096


class TestHandleVoice:
    @patch("megobari.handlers.claude._process_prompt", new_callable=AsyncMock)
    @patch("megobari.voice.is_available", return_value=True)
    @patch("megobari.voice.get_transcriber")
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_voice_transcribe_and_forward(
        self, mock_to_thread, mock_get_trans, mock_avail,
        mock_process, session_manager
    ):
        from megobari.config import Config
        from megobari.handlers.claude import handle_voice

        mock_transcriber = MagicMock()
        mock_get_trans.return_value = mock_transcriber
        mock_to_thread.return_value = "Hello from voice"

        config = Config(bot_token="fake", whisper_model="tiny")
        ctx = MockTransport(
            session_manager=session_manager,
            bot_data={"session_manager": session_manager, "config": config},
        )
        ctx.download_voice.return_value = Path("/tmp/voice.ogg")
        session_manager.create("s")

        await handle_voice(ctx)

        # Should show transcription
        reply_calls = ctx.reply.call_args_list
        any_transcription = any("Hello from voice" in str(c) for c in reply_calls)
        assert any_transcription

        # Should forward to _process_prompt with transcription
        mock_process.assert_called_once_with("Hello from voice", ctx)

        # Reaction should be set and cleared
        reaction_calls = ctx.set_reaction.call_args_list
        assert reaction_calls[0][0][0] == "\U0001f440"
        assert reaction_calls[-1][0][0] is None

    @patch("megobari.voice.is_available", return_value=False)
    async def test_voice_not_available(self, mock_avail, session_manager):
        from megobari.handlers.claude import handle_voice

        ctx = MockTransport(session_manager=session_manager)

        await handle_voice(ctx)

        text = ctx.reply.call_args[0][0]
        assert "faster-whisper" in text

    @patch("megobari.voice.is_available", return_value=True)
    async def test_voice_no_session(self, mock_avail, session_manager):
        from megobari.handlers.claude import handle_voice

        ctx = MockTransport(session_manager=session_manager)

        await handle_voice(ctx)

        text = ctx.reply.call_args[0][0]
        assert "No active session" in text

    @patch("megobari.handlers.claude._process_prompt", new_callable=AsyncMock)
    @patch("megobari.voice.is_available", return_value=True)
    @patch("megobari.voice.get_transcriber")
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_voice_empty_transcription(
        self, mock_to_thread, mock_get_trans, mock_avail,
        mock_process, session_manager
    ):
        from megobari.config import Config
        from megobari.handlers.claude import handle_voice

        mock_transcriber = MagicMock()
        mock_get_trans.return_value = mock_transcriber
        mock_to_thread.return_value = "   "

        config = Config(bot_token="fake")
        ctx = MockTransport(
            session_manager=session_manager,
            bot_data={"session_manager": session_manager, "config": config},
        )
        ctx.download_voice.return_value = Path("/tmp/voice.ogg")
        session_manager.create("s")

        await handle_voice(ctx)

        text = ctx.reply.call_args[0][0]
        assert "Could not transcribe" in text
        mock_process.assert_not_called()

    @patch("megobari.handlers.claude._process_prompt", new_callable=AsyncMock)
    @patch("megobari.voice.is_available", return_value=True)
    @patch("megobari.voice.get_transcriber")
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_voice_uses_config_model(
        self, mock_to_thread, mock_get_trans, mock_avail,
        mock_process, session_manager
    ):
        from megobari.config import Config
        from megobari.handlers.claude import handle_voice

        mock_transcriber = MagicMock()
        mock_get_trans.return_value = mock_transcriber
        mock_to_thread.return_value = "test"

        config = Config(bot_token="fake", whisper_model="large-v3")
        ctx = MockTransport(
            session_manager=session_manager,
            bot_data={"session_manager": session_manager, "config": config},
        )
        ctx.download_voice.return_value = Path("/tmp/voice.ogg")
        session_manager.create("s")

        await handle_voice(ctx)

        mock_get_trans.assert_called_with("large-v3")
