"""Periodic conversation summarizer — uses Claude to produce summaries."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from megobari.db import Repository, get_session
from megobari.db.models import Message

logger = logging.getLogger(__name__)

# Summarize after this many unsummarized messages accumulate.
SUMMARY_THRESHOLD = 20

# Prompt sent to Claude to generate a summary.
_SUMMARIZE_PROMPT = """\
Below is a recent conversation between a user and an AI assistant (megobari bot).
Produce two outputs separated by the exact delimiter "---FULL---":

1. First, a SHORT one-line summary (max 150 chars) capturing the essence.
2. Then the delimiter "---FULL---" on its own line.
3. Then a FULL summary (3-8 sentences) covering:
   - What was discussed and decided
   - Key technical details, file paths, or commands mentioned
   - Any pending tasks or next steps

Example format:
Implemented dark mode toggle and fixed CSS issues in settings page
---FULL---
The user requested a dark mode feature. We added a toggle component...

Output ONLY the two parts as described, nothing else.

--- CONVERSATION ---
{conversation}
"""


def _parse_summary(raw: str) -> tuple[str, str]:
    """Parse raw Claude output into (short_summary, full_summary).

    If the delimiter is missing, the entire text becomes the full summary
    and the first 150 chars become the short summary.
    """
    delimiter = "---FULL---"
    if delimiter in raw:
        short, full = raw.split(delimiter, 1)
        short = short.strip()
        full = full.strip()
        # Ensure short is actually short
        if len(short) > 200:
            short = short[:197] + "..."
        return short, full
    # Fallback: no delimiter found
    full = raw.strip()
    short = full[:150].rsplit(" ", 1)[0] + "..." if len(full) > 150 else full
    return short, full


def _format_messages(messages: list[Message]) -> str:
    """Format messages into a readable conversation transcript."""
    lines = []
    for msg in messages:
        prefix = "User" if msg.role == "user" else "Assistant"
        # Truncate very long assistant messages (code dumps etc.)
        content = msg.content
        if len(content) > 2000:
            content = content[:2000] + "\n... [truncated]"
        lines.append(f"{prefix}: {content}")
    return "\n\n".join(lines)


async def _generate_summary_text(
    messages: list[Message],
    send_fn: Callable[[str], Awaitable[str]],
) -> tuple[str, str]:
    """Generate a summary using Claude via the provided send function.

    Args:
        messages: Messages to summarize.
        send_fn: Async function that sends a prompt and returns response text.

    Returns:
        Tuple of (short_summary, full_summary).
    """
    conversation = _format_messages(messages)
    prompt = _SUMMARIZE_PROMPT.format(conversation=conversation)
    raw = await send_fn(prompt)
    return _parse_summary(raw)


async def check_and_summarize(
    session_name: str,
    send_fn: Callable[[str], Awaitable[str]],
    user_id: int | None = None,
    threshold: int = SUMMARY_THRESHOLD,
) -> bool:
    """Check if enough messages have accumulated and create a summary.

    Args:
        session_name: Session to check.
        send_fn: Async callable that sends a prompt to Claude and returns text.
        user_id: DB user ID for the summary record.
        threshold: Number of unsummarized messages before triggering.

    Returns:
        True if a summary was generated, False otherwise.
    """
    async with get_session() as s:
        repo = Repository(s)
        count = await repo.count_unsummarized(session_name)
        if count < threshold:
            return False

        messages = await repo.get_unsummarized_messages(session_name)
        if not messages:
            return False

        message_ids = [m.id for m in messages]

    # Generate summary outside the DB session to avoid long transactions
    try:
        short_summary, full_summary = await _generate_summary_text(messages, send_fn)
    except Exception:
        logger.warning("Failed to generate summary for %s", session_name, exc_info=True)
        return False

    # Save summary and mark messages
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(
            session_name=session_name,
            summary=full_summary,
            short_summary=short_summary,
            user_id=user_id,
            message_count=len(message_ids),
        )
        await repo.mark_summarized(message_ids)

    logger.info(
        "Created summary for session %r (%d messages)",
        session_name,
        len(message_ids),
    )
    return True


async def maybe_summarize_background(
    session_name: str,
    send_fn: Callable[[str], Awaitable[str]],
    user_id: int | None = None,
    threshold: int = SUMMARY_THRESHOLD,
) -> None:
    """Fire-and-forget wrapper — runs check_and_summarize in background."""
    try:
        await check_and_summarize(session_name, send_fn, user_id, threshold)
    except Exception:
        logger.debug("Background summarization failed", exc_info=True)


async def log_message(
    session_name: str,
    role: str,
    content: str,
    user_id: int | None = None,
) -> None:
    """Log a message to the database and broadcast to dashboard."""
    try:
        async with get_session() as s:
            repo = Repository(s)
            msg = await repo.add_message(
                session_name=session_name,
                role=role,
                content=content,
                user_id=user_id,
            )
        # Notify dashboard WebSocket subscribers
        try:
            from megobari.api.pubsub import MessageEvent, message_bus

            message_bus.publish(
                MessageEvent(
                    id=msg.id,
                    session_name=msg.session_name,
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at.isoformat() + "Z"
                    if msg.created_at.tzinfo is None
                    else msg.created_at.isoformat(),
                )
            )
        except Exception:
            pass  # Dashboard not loaded or no subscribers
    except Exception:
        logger.debug("Failed to log message", exc_info=True)
