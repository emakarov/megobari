# REQ-006: Voice Message Support

## Problem

Users may want to send voice messages to the bot instead of typing. The bot
currently only handles text messages.

## Goals

1. Accept Telegram voice messages and transcribe them to text
2. Use `faster-whisper` for local, free, offline transcription
3. Make the voice feature an **optional dependency** — core megobari works
   without it, install via `pip install megobari[voice]`

## Design

### Optional dependency pattern

```toml
# pyproject.toml
[project.optional-dependencies]
voice = ["faster-whisper>=1.0.0"]
```

Install: `pip install megobari[voice]`

### New module: `voice.py`

Lazy-loads `faster-whisper` on first use. If not installed, raises a clear
error telling the user to install with `[voice]` extra.

```python
class Transcriber:
    def __init__(self, model_size="small"):
        self._model = None
        self._model_size = model_size

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._model_size, device="cpu",
                                        compute_type="int8")

    def transcribe(self, audio_path: str) -> str:
        self._ensure_model()
        segments, _ = self._model.transcribe(audio_path, beam_size=5)
        return " ".join(s.text.strip() for s in segments)
```

- Default model: `small` (~150MB, good enough for voice messages)
- Runs on CPU with int8 quantization — no GPU needed
- Model downloaded on first use (cached by ctranslate2)
- Supports `.ogg` natively (Telegram voice format) via PyAV

### Config extension

Add optional `whisper_model` field to `Config`:

```python
whisper_model: str = "small"  # tiny, base, small, medium, large-v3
```

### Bot integration

- Add `filters.VOICE` handler in `bot.py`
- Download `.ogg` file via `Voice.get_file()` → `file.download_to_drive()`
- Transcribe with `Transcriber`
- Show transcription as a quoted reply, then send to Claude
- If `faster-whisper` not installed, reply with install instructions

### Flow

```
User sends voice message
  → Bot downloads .ogg to temp file
  → Transcriber converts to text
  → Bot replies: "🎤 <transcription>"
  → Text sent to Claude as normal prompt
  → Claude responds
```

## Testing

- `test_voice.py`:
  - Transcriber with mocked WhisperModel
  - Import error handling (faster-whisper not installed)
  - Voice handler integration (download + transcribe + send to Claude)
- Voice tests should work without faster-whisper installed (all mocked)
