"""Telegram implementation of TransportContext."""

from __future__ import annotations

import logging
import tempfile
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Coroutine

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from megobari.formatting import Formatter, TelegramFormatter
from megobari.transport import MessageHandle, TransportContext

logger = logging.getLogger(__name__)

# Telegram HTML message length limit
_MAX_MSG_LEN = 4096

# Shared formatter singleton
_fmt = TelegramFormatter()


class TelegramTransport(TransportContext):
    """Wraps python-telegram-bot's Update + Context into TransportContext."""

    def __init__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        self._update = update
        self._context = context

    # -- input data --

    @property
    def args(self) -> list[str]:
        """Command arguments."""
        return self._context.args or []

    @property
    def text(self) -> str | None:
        """Message text."""
        msg = self._update.message
        return msg.text if msg else None

    @property
    def chat_id(self) -> int:
        """Telegram chat ID."""
        return self._update.effective_chat.id

    @property
    def message_id(self) -> int:
        """Telegram message ID."""
        return self._update.message.message_id

    @property
    def user_id(self) -> int:
        """Telegram user ID."""
        user = self._update.effective_user
        return user.id if user else 0

    @property
    def username(self) -> str | None:
        """Telegram username."""
        user = self._update.effective_user
        return user.username if user else None

    @property
    def first_name(self) -> str | None:
        """User's first name."""
        user = self._update.effective_user
        return user.first_name if user else None

    @property
    def last_name(self) -> str | None:
        """User's last name."""
        user = self._update.effective_user
        return user.last_name if user else None

    @property
    def caption(self) -> str | None:
        """Media caption."""
        msg = self._update.message
        return msg.caption if msg else None

    # -- shared application state --

    @property
    def session_manager(self) -> Any:
        """Return session manager from bot_data."""
        return self._context.bot_data["session_manager"]

    @property
    def formatter(self) -> Formatter:
        """Telegram HTML formatter."""
        return _fmt

    @property
    def bot_data(self) -> dict:
        """Shared bot_data dict."""
        return self._context.bot_data

    # -- messaging --

    async def reply(
        self, text: str, *, formatted: bool = False
    ) -> MessageHandle:
        """Send a reply via Telegram."""
        kwargs: dict[str, Any] = {}
        if formatted:
            kwargs["parse_mode"] = _fmt.parse_mode
        return await self._update.message.reply_text(text, **kwargs)

    async def reply_document(
        self,
        path: Path | str,
        filename: str,
        *,
        caption: str | None = None,
    ) -> None:
        """Send a document via Telegram."""
        resolved = Path(path)
        with open(resolved, "rb") as f:
            kwargs: dict[str, Any] = {
                "document": f,
                "filename": filename,
            }
            if caption:
                kwargs["caption"] = caption
            await self._update.message.reply_document(**kwargs)

    async def reply_photo(
        self, path: Path | str, *, caption: str | None = None
    ) -> None:
        """Send a photo via Telegram."""
        resolved = Path(path)
        with open(resolved, "rb") as f:
            kwargs: dict[str, Any] = {"photo": f}
            if caption:
                kwargs["caption"] = caption
            await self._update.message.reply_photo(**kwargs)

    async def send_message(self, text: str) -> None:
        """Send a standalone message to the chat."""
        await self._context.bot.send_message(
            chat_id=self.chat_id, text=text
        )

    async def edit_message(
        self,
        handle: MessageHandle,
        text: str,
        *,
        formatted: bool = False,
    ) -> None:
        """Edit a previously sent Telegram message."""
        kwargs: dict[str, Any] = {}
        if formatted:
            kwargs["parse_mode"] = _fmt.parse_mode
        await handle.edit_text(text, **kwargs)

    async def delete_message(self, handle: MessageHandle) -> None:
        """Delete a Telegram message."""
        await handle.delete()

    # -- indicators --

    async def send_typing(self) -> None:
        """Send Telegram typing indicator."""
        await self._context.bot.send_chat_action(
            chat_id=self.chat_id, action=ChatAction.TYPING
        )

    async def set_reaction(self, emoji: str | None) -> None:
        """Set or clear reaction on the incoming message."""
        try:
            reaction = [] if emoji is None else [emoji]
            await self._context.bot.set_message_reaction(
                chat_id=self.chat_id,
                message_id=self.message_id,
                reaction=reaction,
            )
        except Exception:
            logger.debug(
                "Failed to set reaction %r", emoji, exc_info=True
            )

    # -- file downloads --

    async def download_photo(self) -> Path | None:
        """Download incoming photo to session cwd."""
        msg = self._update.message
        if not msg or not msg.photo:
            return None
        photo = msg.photo[-1]  # largest resolution
        photo_file = await photo.get_file()
        ext = (
            Path(photo_file.file_path).suffix
            if photo_file.file_path
            else ".jpg"
        )
        filename = f"photo_{self.message_id}{ext}"
        sm = self.session_manager
        session = sm.current
        save_dir = Path(session.cwd) if session else Path.home()
        save_path = save_dir / filename
        await photo_file.download_to_drive(str(save_path))
        return save_path

    async def download_document(self) -> tuple[Path, str] | None:
        """Download incoming document. Returns (path, filename)."""
        msg = self._update.message
        if not msg or not msg.document:
            return None
        doc = msg.document
        doc_file = await doc.get_file()
        filename = doc.file_name or f"document_{self.message_id}"
        sm = self.session_manager
        session = sm.current
        save_dir = Path(session.cwd) if session else Path.home()
        save_path = save_dir / filename
        await doc_file.download_to_drive(str(save_path))
        return save_path, filename

    async def download_voice(self) -> Path | None:
        """Download incoming voice message to temp file."""
        msg = self._update.message
        if not msg or not msg.voice:
            return None
        voice = msg.voice
        voice_file = await voice.get_file()
        with tempfile.NamedTemporaryFile(
            suffix=".ogg", delete=False
        ) as tmp:
            tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)
        return Path(tmp_path)

    # -- transport metadata --

    @property
    def transport_name(self) -> str:
        """Return transport name."""
        return "telegram"

    @property
    def max_message_length(self) -> int:
        """Telegram message length limit."""
        return _MAX_MSG_LEN


def telegram_handler(
    fn: Callable[[TransportContext], Coroutine],
) -> Callable:
    """Wrap a TransportContext handler for python-telegram-bot dispatch."""
    @wraps(fn)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        ctx = TelegramTransport(update, context)
        await fn(ctx)
    return wrapper
