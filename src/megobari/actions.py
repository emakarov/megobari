"""Action protocol: parse and execute megobari action blocks."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from megobari.transport import TransportContext

logger = logging.getLogger(__name__)

# Matches ```megobari\n{...}\n``` blocks (with optional whitespace)
_ACTION_BLOCK_RE = re.compile(
    r"```megobari\s*\n(.*?)\n\s*```",
    re.DOTALL,
)


def parse_actions(text: str) -> tuple[str, list[dict]]:
    """Extract megobari action blocks from response text.

    Returns:
        A tuple of (cleaned_text, actions) where cleaned_text has the
        action blocks removed and actions is a list of parsed JSON dicts.
        Invalid JSON blocks are left in the text as-is.
    """
    actions: list[dict] = []
    blocks_to_remove: list[tuple[int, int]] = []

    for match in _ACTION_BLOCK_RE.finditer(text):
        raw_json = match.group(1).strip()
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Invalid JSON in megobari block: %s", raw_json[:200])
            continue  # leave invalid block in text

        if not isinstance(data, dict) or "action" not in data:
            logger.warning("Megobari block missing 'action' key: %s", raw_json[:200])
            continue

        actions.append(data)
        blocks_to_remove.append((match.start(), match.end()))

    # Remove matched blocks from text (reverse order to preserve indices)
    cleaned = text
    for start, end in reversed(blocks_to_remove):
        cleaned = cleaned[:start] + cleaned[end:]

    # Clean up extra blank lines left behind
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned, actions


async def execute_actions(
    actions: list[dict],
    ctx: TransportContext,
    *,
    user_id: int | None = None,
) -> list[str]:
    """Execute a list of parsed actions.

    Returns a list of error messages (empty if all succeeded).
    """
    errors: list[str] = []

    for action in actions:
        action_type = action.get("action")

        if action_type == "send_file":
            err = await _action_send_file(action, ctx)
            if err:
                errors.append(err)
        elif action_type == "send_photo":
            err = await _action_send_photo(action, ctx)
            if err:
                errors.append(err)
        elif action_type == "restart":
            await _action_restart(ctx)
        elif action_type == "memory_set":
            err = await _action_memory_set(action, user_id)
            if err:
                errors.append(err)
        elif action_type == "memory_delete":
            err = await _action_memory_delete(action, user_id)
            if err:
                errors.append(err)
        elif action_type == "memory_list":
            result = await _action_memory_list(action, ctx, user_id)
            if result:
                errors.append(result)
        else:
            logger.warning("Unknown action type: %s", action_type)

    return errors


async def _action_send_file(
    action: dict, ctx: TransportContext
) -> str | None:
    """Execute a send_file action. Returns error string or None."""
    raw_path = action.get("path")
    if not raw_path:
        return "send_file: missing 'path'"

    resolved = Path(raw_path).expanduser().resolve()
    if not resolved.is_file():
        return f"send_file: file not found: {resolved}"

    caption = action.get("caption")

    try:
        await ctx.reply_document(
            resolved, resolved.name, caption=caption
        )
    except Exception as e:
        return f"send_file: failed to send {resolved.name}: {e}"

    return None


async def _action_send_photo(
    action: dict, ctx: TransportContext
) -> str | None:
    """Execute a send_photo action. Returns error string or None."""
    raw_path = action.get("path")
    if not raw_path:
        return "send_photo: missing 'path'"

    resolved = Path(raw_path).expanduser().resolve()
    if not resolved.is_file():
        return f"send_photo: file not found: {resolved}"

    caption = action.get("caption")

    try:
        await ctx.reply_photo(resolved, caption=caption)
    except Exception as e:
        return f"send_photo: failed to send {resolved.name}: {e}"

    return None


# ---------------------------------------------------------------------------
# Memory actions
# ---------------------------------------------------------------------------


async def _action_memory_set(action: dict, user_id: int | None) -> str | None:
    """Save a memory. Returns error string or None."""
    category = action.get("category")
    key = action.get("key")
    value = action.get("value")
    if not category or not key or not value:
        return "memory_set: requires 'category', 'key', and 'value'"

    try:
        from megobari.db import Repository, get_session

        async with get_session() as session:
            repo = Repository(session)
            await repo.set_memory(
                category=category,
                key=key,
                content=value,
                user_id=user_id,
            )
        logger.info("Memory saved: %s/%s", category, key)
    except Exception as e:
        logger.warning("memory_set failed: %s", e)
        return f"memory_set: {e}"
    return None


async def _action_memory_delete(action: dict, user_id: int | None) -> str | None:
    """Delete a memory. Returns error string or None."""
    category = action.get("category")
    key = action.get("key")
    if not category or not key:
        return "memory_delete: requires 'category' and 'key'"

    try:
        from megobari.db import Repository, get_session

        async with get_session() as session:
            repo = Repository(session)
            ok = await repo.delete_memory(
                category=category, key=key, user_id=user_id
            )
        if ok:
            logger.info("Memory deleted: %s/%s", category, key)
        else:
            return f"memory_delete: not found {category}/{key}"
    except Exception as e:
        logger.warning("memory_delete failed: %s", e)
        return f"memory_delete: {e}"
    return None


async def _action_memory_list(
    action: dict, ctx: TransportContext, user_id: int | None
) -> str | None:
    """List memories and send to chat. Returns error string or None."""
    category = action.get("category")
    try:
        from megobari.db import Repository, get_session

        async with get_session() as session:
            repo = Repository(session)
            memories = await repo.list_memories(
                user_id=user_id, category=category
            )
        if not memories:
            await ctx.send_message("📭 No memories found.")
        else:
            lines = []
            for m in memories:
                lines.append(f"• **{m.category}/{m.key}**: {m.content}")
            await ctx.send_message("\n".join(lines))
    except Exception as e:
        logger.warning("memory_list failed: %s", e)
        return f"memory_list: {e}"
    return None


_RESTART_MARKER = Path(".megobari") / "restart_notify.json"


def save_restart_marker(chat_id: int | str) -> None:
    """Save chat_id so the bot can notify after restart."""
    _RESTART_MARKER.parent.mkdir(parents=True, exist_ok=True)
    _RESTART_MARKER.write_text(json.dumps({"chat_id": chat_id}))
    logger.info("Restart marker saved for chat_id=%s", chat_id)


def load_restart_marker() -> int | None:
    """Load and delete restart marker. Returns chat_id or None."""
    if not _RESTART_MARKER.is_file():
        return None
    try:
        data = json.loads(_RESTART_MARKER.read_text())
        chat_id = data.get("chat_id")
        _RESTART_MARKER.unlink()
        logger.info("Restart marker loaded: chat_id=%s", chat_id)
        return chat_id
    except Exception:
        logger.warning("Failed to read restart marker")
        try:
            _RESTART_MARKER.unlink()
        except Exception:
            pass
        return None


async def _action_restart(ctx: TransportContext) -> None:
    """Restart the bot process via os.execv."""
    logger.info("Restart action triggered — restarting bot process")
    save_restart_marker(ctx.chat_id)
    try:
        await ctx.send_message("🔄 Restarting...")
    except Exception:
        pass
    try:
        from megobari.summarizer import log_message

        await log_message(
            ctx.session_manager.current.name, "assistant", "🔄 Restarting..."
        )
    except Exception:
        pass
    _do_restart()


def _do_restart() -> None:
    """Re-exec the current process. Extracted for testability."""
    os.execv(sys.executable, [sys.executable] + sys.argv)
