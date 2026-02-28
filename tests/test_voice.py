"""Tests for voice message transcription (all mocked, no faster-whisper needed)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from megobari.session import SessionManager

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


def _make_context(session_manager: SessionManager, config=None):
    """Create a mock telegram context."""
    ctx = MagicMock()
    ctx.bot_data = {"session_manager": session_manager}
    if config:
        ctx.bot_data["config"] = config
    else:
        ctx.bot_data["config"] = None
    ctx.args = []
    ctx.bot = AsyncMock()
    return ctx


def _make_voice_update():
    """Create a mock update with a voice message."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.voice = MagicMock()
    update.message.voice.get_file = AsyncMock()
    update.message.text = None
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.message.message_id = 99
    return update


class TestHandleVoice:
    @patch("megobari.handlers.claude._process_prompt", new_callable=AsyncMock)
    @patch("megobari.voice.is_available", return_value=True)
    @patch("megobari.voice.get_transcriber")
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_voice_transcribe_and_forward(
        self, mock_to_thread, mock_get_trans, mock_avail,
        mock_process, session_manager
    ):
        from megobari.bot import handle_voice
        from megobari.config import Config

        mock_transcriber = MagicMock()
        mock_get_trans.return_value = mock_transcriber
        mock_to_thread.return_value = "Hello from voice"

        update = _make_voice_update()
        mock_file = AsyncMock()
        update.message.voice.get_file.return_value = mock_file

        config = Config(bot_token="fake", whisper_model="tiny")
        ctx = _make_context(session_manager, config=config)
        session_manager.create("s")

        await handle_voice(update, ctx)

        # Should show transcription
        reply_calls = update.message.reply_text.call_args_list
        any_transcription = any("Hello from voice" in str(c) for c in reply_calls)
        assert any_transcription

        # Should forward to _process_prompt with transcription
        mock_process.assert_called_once_with("Hello from voice", update, ctx)

        # Reaction should be set and cleared
        reaction_calls = ctx.bot.set_message_reaction.call_args_list
        assert reaction_calls[0][1]["reaction"] == ["\U0001f440"]
        assert reaction_calls[-1][1]["reaction"] == []

    @patch("megobari.voice.is_available", return_value=False)
    async def test_voice_not_available(self, mock_avail, session_manager):
        from megobari.bot import handle_voice

        update = _make_voice_update()
        ctx = _make_context(session_manager)

        await handle_voice(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "faster-whisper" in text

    @patch("megobari.voice.is_available", return_value=True)
    async def test_voice_no_session(self, mock_avail, session_manager):
        from megobari.bot import handle_voice

        update = _make_voice_update()
        ctx = _make_context(session_manager)

        await handle_voice(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    @patch("megobari.handlers.claude._process_prompt", new_callable=AsyncMock)
    @patch("megobari.voice.is_available", return_value=True)
    @patch("megobari.voice.get_transcriber")
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_voice_empty_transcription(
        self, mock_to_thread, mock_get_trans, mock_avail,
        mock_process, session_manager
    ):
        from megobari.bot import handle_voice
        from megobari.config import Config

        mock_transcriber = MagicMock()
        mock_get_trans.return_value = mock_transcriber
        mock_to_thread.return_value = "   "

        update = _make_voice_update()
        mock_file = AsyncMock()
        update.message.voice.get_file.return_value = mock_file

        config = Config(bot_token="fake")
        ctx = _make_context(session_manager, config=config)
        session_manager.create("s")

        await handle_voice(update, ctx)

        text = update.message.reply_text.call_args[0][0]
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
        from megobari.bot import handle_voice
        from megobari.config import Config

        mock_transcriber = MagicMock()
        mock_get_trans.return_value = mock_transcriber
        mock_to_thread.return_value = "test"

        update = _make_voice_update()
        mock_file = AsyncMock()
        update.message.voice.get_file.return_value = mock_file

        config = Config(bot_token="fake", whisper_model="large-v3")
        ctx = _make_context(session_manager, config=config)
        session_manager.create("s")

        await handle_voice(update, ctx)

        mock_get_trans.assert_called_with("large-v3")
