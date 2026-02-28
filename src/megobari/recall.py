"""Memory recall — build context from summaries and memories for Claude."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from megobari.db import Repository, get_session

logger = logging.getLogger(__name__)


@dataclass
class RecallResult:
    """Result of recall context building, including persona metadata."""

    context: str | None = None
    # MCP server names the active persona wants (empty = no persona filtering)
    persona_mcp_servers: list[str] = field(default_factory=list)
    # Skill names the active persona prioritizes (empty = no filtering)
    persona_skills: list[str] = field(default_factory=list)


async def build_recall_context(
    session_name: str,
    user_id: int | None = None,
) -> RecallResult:
    """Build recall context from recent summaries, persona, and memories.

    Returns a RecallResult with context string and persona metadata.
    """
    parts: list[str] = []
    result = RecallResult()

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

            # Persona (if default persona set)
            persona = await repo.get_default_persona()
            if persona:
                persona_parts = []
                if persona.system_prompt:
                    persona_parts.append(persona.system_prompt)

                # Skills priority
                p_skills = Repository.persona_skills(persona)
                if p_skills:
                    result.persona_skills = p_skills
                    persona_parts.append(
                        "Prioritize these skills: "
                        + ", ".join(p_skills)
                    )

                # MCP server names (used by _build_options, also noted here)
                p_mcp = Repository.persona_mcp_servers(persona)
                if p_mcp:
                    result.persona_mcp_servers = p_mcp
                    persona_parts.append(
                        "Active MCP integrations: "
                        + ", ".join(p_mcp)
                    )

                if persona_parts:
                    header = f"Active persona ({persona.name}):"
                    parts.append(
                        header + " " + " | ".join(persona_parts)
                    )

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
        return result

    result.context = "\n\n".join(parts) if parts else None
    return result
