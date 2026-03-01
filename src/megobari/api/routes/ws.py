"""WebSocket endpoint for live message streaming."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from megobari.api.pubsub import message_bus
from megobari.db.engine import get_session
from megobari.db.repository import Repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _ws_authenticate(token: str) -> bool:
    """Verify a bearer token against the DB (same as HTTP auth)."""
    if not token:
        return False
    try:
        async with get_session() as session:
            repo = Repository(session)
            dt = await repo.verify_dashboard_token(token)
            return dt is not None
    except Exception:
        return False


@router.websocket("/ws/messages")
async def ws_messages(
    ws: WebSocket,
    token: str = Query(""),
) -> None:
    """Stream new messages in real-time.

    Connect: ws://host:port/api/ws/messages?token=<bearer_token>
    Sends JSON: {"id", "session_name", "role", "content", "created_at"}
    """
    if not await _ws_authenticate(token):
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    queue = message_bus.subscribe()

    try:
        while True:
            event = await queue.get()
            await ws.send_text(
                json.dumps(
                    {
                        "id": event.id,
                        "session_name": event.session_name,
                        "role": event.role,
                        "content": event.content,
                        "created_at": event.created_at,
                    }
                )
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket error", exc_info=True)
    finally:
        message_bus.unsubscribe(queue)
