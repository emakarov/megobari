"""Action protocol: parse and execute megobari action blocks."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

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
    bot,
    chat_id: int,
) -> list[str]:
    """Execute a list of parsed actions.

    Returns a list of error messages (empty if all succeeded).
    """
    errors: list[str] = []

    for action in actions:
        action_type = action.get("action")

        if action_type == "send_file":
            err = await _action_send_file(action, bot, chat_id)
            if err:
                errors.append(err)
        else:
            logger.warning("Unknown action type: %s", action_type)

    return errors


async def _action_send_file(action: dict, bot, chat_id: int) -> str | None:
    """Execute a send_file action. Returns error string or None."""
    raw_path = action.get("path")
    if not raw_path:
        return "send_file: missing 'path'"

    resolved = Path(raw_path).expanduser().resolve()
    if not resolved.is_file():
        return f"send_file: file not found: {resolved}"

    caption = action.get("caption")

    try:
        with open(resolved, "rb") as f:
            kwargs: dict = {"document": f, "filename": resolved.name}
            if caption:
                kwargs["caption"] = caption
            await bot.send_document(chat_id=chat_id, **kwargs)
    except Exception as e:
        return f"send_file: failed to send {resolved.name}: {e}"

    return None
