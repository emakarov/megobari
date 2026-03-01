"""Transport-agnostic context abstraction for multi-platform support.

Defines the interface that all transport adapters (Telegram, Slack, Web UI)
must implement so that handler logic stays platform-independent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from megobari.formatting import Formatter

# Opaque handle returned by reply/send — used for edit/delete.
# Telegram: telegram.Message, Slack: timestamp str, Web: message ID.
MessageHandle = Any


class TransportContext(ABC):
    """Abstract base for transport-specific context adapters.

    Each platform (Telegram, Slack, Web UI) provides a concrete subclass
    that wraps its native request/response objects behind this interface.
    Handlers receive a TransportContext and never touch platform objects.
    """

    # -- input data --

    @property
    @abstractmethod
    def args(self) -> list[str]:
        """Command arguments (e.g. ["on", "15"] for /heartbeat on 15)."""

    @property
    @abstractmethod
    def text(self) -> str | None:
        """Return raw content (None for media-only messages)."""

    @property
    @abstractmethod
    def chat_id(self) -> int | str:
        """Conversation identifier."""

    @property
    @abstractmethod
    def message_id(self) -> int | str:
        """Incoming message identifier."""

    @property
    @abstractmethod
    def user_id(self) -> int | str:
        """User identifier."""

    @property
    @abstractmethod
    def username(self) -> str | None:
        """Username (e.g. Telegram @handle, Slack display name)."""

    @property
    @abstractmethod
    def first_name(self) -> str | None:
        """User's first name."""

    @property
    @abstractmethod
    def last_name(self) -> str | None:
        """User's last name."""

    @property
    @abstractmethod
    def caption(self) -> str | None:
        """Caption on media messages (photos, documents)."""

    # -- shared application state --

    @property
    @abstractmethod
    def session_manager(self) -> Any:
        """The SessionManager instance."""

    @property
    @abstractmethod
    def formatter(self) -> Formatter:
        """Text formatter for this transport."""

    @property
    @abstractmethod
    def bot_data(self) -> dict:
        """Shared application-level data store."""

    # -- messaging --

    @abstractmethod
    async def reply(
        self, text: str, *, formatted: bool = False
    ) -> MessageHandle:
        """Send a reply to the user. Returns a handle for edit/delete."""

    @abstractmethod
    async def reply_document(
        self,
        path: Path | str,
        filename: str,
        *,
        caption: str | None = None,
    ) -> None:
        """Send a file/document to the user."""

    @abstractmethod
    async def reply_photo(
        self, path: Path | str, *, caption: str | None = None
    ) -> None:
        """Send a photo to the user."""

    @abstractmethod
    async def send_message(self, text: str) -> None:
        """Send a standalone message (not a reply)."""

    @abstractmethod
    async def edit_message(
        self,
        handle: MessageHandle,
        text: str,
        *,
        formatted: bool = False,
    ) -> None:
        """Edit a previously sent message."""

    @abstractmethod
    async def delete_message(self, handle: MessageHandle) -> None:
        """Delete a previously sent message."""

    # -- indicators --

    @abstractmethod
    async def send_typing(self) -> None:
        """Show a typing/processing indicator."""

    @abstractmethod
    async def set_reaction(self, emoji: str | None) -> None:
        """Set a reaction on the incoming message (None to clear)."""

    # -- file downloads (incoming media) --

    @abstractmethod
    async def download_photo(self) -> Path | None:
        """Download an incoming photo to disk. Returns path or None."""

    @abstractmethod
    async def download_document(self) -> tuple[Path, str] | None:
        """Download an incoming document. Returns (path, filename) or None."""

    @abstractmethod
    async def download_voice(self) -> Path | None:
        """Download an incoming voice message. Returns path or None."""

    # -- transport metadata --

    @property
    @abstractmethod
    def transport_name(self) -> str:
        """Short name of this transport (e.g. 'telegram', 'slack', 'web')."""

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """Maximum message length for this transport."""
