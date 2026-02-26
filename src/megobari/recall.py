"""Memory recall — build context from summaries and memories for Claude."""

from __future__ import annotations

import logging

from megobari.db import Repository, get_session

logger = logging.getLogger(__name__)


async def build_recall_context(
    session_name: str,
    user_id: int | None = None,
) -> str | None:
    """Build a recall context string from recent summaries and memories.

    Returns None if there's nothing to recall.
    """
    parts: list[str] = []

    try:
        async with get_session() as s:
            repo = Repository(s)

            # Recent summaries for this session (up to 3)
            # Use short_summary for token efficiency; fall back to full summary
            summaries = await repo.get_summaries(
                session_name=session_name, limit=3
            )
            if summaries:
                lines = ["Previous conversation summaries for this session:"]
                for cs in reversed(summaries):  # oldest first
                    ts = cs.created_at.strftime("%Y-%m-%d %H:%M") if cs.created_at else "?"
                    text = cs.short_summary or cs.summary
                    lines.append(f"[{ts}] {text}")
                parts.append("\n".join(lines))

            # Persona system prompt (if default persona set)
            persona = await repo.get_default_persona()
            if persona and persona.system_prompt:
                parts.append(f"Active persona ({persona.name}): {persona.system_prompt}")

            # User memories (up to 20)
            if user_id is not None:
                memories = await repo.list_memories(user_id=user_id, limit=20)
            else:
                memories = await repo.list_memories(limit=20)

            if memories:
                lines = ["Known facts and preferences:"]
                for m in memories:
                    lines.append(f"- [{m.category}] {m.key}: {m.content}")
                parts.append("\n".join(lines))

    except Exception:
        logger.debug("Failed to build recall context", exc_info=True)
        return None

    if not parts:
        return None

    return "\n\n".join(parts)
