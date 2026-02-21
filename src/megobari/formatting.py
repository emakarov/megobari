from __future__ import annotations

import html as html_lib
from abc import ABC, abstractmethod


class Formatter(ABC):
    """Abstract formatter for client-specific text formatting.

    Subclass this for each client (Telegram, Discord, CLI, etc.).
    All text that is NOT passed through a formatting method must be
    passed through ``escape()`` to prevent injection.
    """

    @property
    @abstractmethod
    def parse_mode(self) -> str | None:
        """Client-specific parse mode hint (e.g. 'HTML' for Telegram)."""
        ...

    @abstractmethod
    def bold(self, text: str) -> str:
        """Return text formatted as bold."""
        ...

    @abstractmethod
    def italic(self, text: str) -> str:
        """Return text formatted as italic."""
        ...

    @abstractmethod
    def code(self, text: str) -> str:
        """Inline monospace."""
        ...

    @abstractmethod
    def pre(self, text: str) -> str:
        """Code block."""
        ...

    @abstractmethod
    def escape(self, text: str) -> str:
        """Escape raw text so it is rendered literally."""
        ...


class TelegramFormatter(Formatter):
    """Telegram HTML formatter."""

    @property
    def parse_mode(self) -> str:
        """Return Telegram parse mode."""
        return "HTML"

    def bold(self, text: str) -> str:
        """Return text wrapped in HTML bold tags."""
        return f"<b>{text}</b>"

    def italic(self, text: str) -> str:
        """Return text wrapped in HTML italic tags."""
        return f"<i>{text}</i>"

    def code(self, text: str) -> str:
        """Return text wrapped in HTML code tags."""
        return f"<code>{html_lib.escape(text)}</code>"

    def pre(self, text: str) -> str:
        """Return text wrapped in HTML pre tags."""
        return f"<pre>{html_lib.escape(text)}</pre>"

    def escape(self, text: str) -> str:
        """Return text with HTML entities escaped."""
        return html_lib.escape(text)


class PlainTextFormatter(Formatter):
    """No-op formatter — returns text as-is."""

    @property
    def parse_mode(self) -> str | None:
        """Return None as plain text has no parse mode."""
        return None

    def bold(self, text: str) -> str:
        """Return text unmodified."""
        return text

    def italic(self, text: str) -> str:
        """Return text unmodified."""
        return text

    def code(self, text: str) -> str:
        """Return text unmodified."""
        return text

    def pre(self, text: str) -> str:
        """Return text unmodified."""
        return text

    def escape(self, text: str) -> str:
        """Return text unmodified."""
        return text
