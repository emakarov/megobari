"""In-process pub/sub for real-time dashboard events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MessageEvent:
    """A new message was logged to the database."""

    id: int
    session_name: str
    role: str
    content: str
    created_at: str  # ISO format


class MessageBus:
    """Simple asyncio broadcast hub for message events.

    WebSocket handlers subscribe; log_message publishes.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[MessageEvent]] = set()

    def subscribe(self) -> asyncio.Queue[MessageEvent]:
        """Create a new subscription queue."""
        q: asyncio.Queue[MessageEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[MessageEvent]) -> None:
        """Remove a subscription queue."""
        self._subscribers.discard(q)

    def publish(self, event: MessageEvent) -> None:
        """Broadcast event to all subscribers (non-blocking)."""
        dead: list[asyncio.Queue[MessageEvent]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        # Drop slow consumers
        for q in dead:
            self._subscribers.discard(q)
            logger.debug("Dropped slow WebSocket subscriber")


# Global singleton — imported by summarizer.py and ws route
message_bus = MessageBus()
