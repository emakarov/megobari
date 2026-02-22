"""Voice transcription with faster-whisper (optional dependency)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

INSTALL_HINT = (
    "Voice support requires faster-whisper.\n"
    "Install with: pip install megobari[voice]"
)


def _check_dependency() -> None:
    """Raise ImportError with install hint if faster-whisper is missing."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        raise ImportError(INSTALL_HINT)


class Transcriber:
    """Lazy-loading speech-to-text transcriber using faster-whisper.

    The model is downloaded and loaded on first transcription call.
    """

    def __init__(self, model_size: str = "small"):
        self._model = None
        self._model_size = model_size

    def _ensure_model(self) -> None:
        """Load the whisper model on first use."""
        if self._model is not None:
            return
        _check_dependency()
        from faster_whisper import WhisperModel

        logger.info("Loading whisper model: %s", self._model_size)
        self._model = WhisperModel(
            self._model_size,
            device="cpu",
            compute_type="int8",
        )
        logger.info("Whisper model loaded")

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to audio file (.ogg, .mp3, .wav, etc.)

        Returns:
            Transcribed text.
        """
        self._ensure_model()
        segments, info = self._model.transcribe(audio_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments)
        logger.info(
            "Transcribed %.1fs audio (%s): %s",
            info.duration,
            info.language,
            text[:100] + ("..." if len(text) > 100 else ""),
        )
        return text


# Module-level singleton, created lazily on first voice message.
_transcriber: Transcriber | None = None


def get_transcriber(model_size: str = "small") -> Transcriber:
    """Get or create the module-level Transcriber singleton."""
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber(model_size=model_size)
    return _transcriber


def is_available() -> bool:
    """Check if faster-whisper is installed."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False
