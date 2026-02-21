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
    def bold(self, text: str) -> str: ...

    @abstractmethod
    def italic(self, text: str) -> str: ...

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
        return "HTML"

    def bold(self, text: str) -> str:
        return f"<b>{text}</b>"

    def italic(self, text: str) -> str:
        return f"<i>{text}</i>"

    def code(self, text: str) -> str:
        return f"<code>{html_lib.escape(text)}</code>"

    def pre(self, text: str) -> str:
        return f"<pre>{html_lib.escape(text)}</pre>"

    def escape(self, text: str) -> str:
        return html_lib.escape(text)


class PlainTextFormatter(Formatter):
    """No-op formatter — returns text as-is."""

    @property
    def parse_mode(self) -> str | None:
        return None

    def bold(self, text: str) -> str:
        return text

    def italic(self, text: str) -> str:
        return text

    def code(self, text: str) -> str:
        return text

    def pre(self, text: str) -> str:
        return text

    def escape(self, text: str) -> str:
        return text
