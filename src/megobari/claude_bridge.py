"""Claude Code Agent SDK integration layer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from claude_agent_sdk._errors import MessageParseError

from megobari.session import Session

logger = logging.getLogger(__name__)

# Block interactive tools that require user input.
# Everything else (built-in + MCP) is inherited from the CLI automatically.
DISALLOWED_TOOLS = [
    "AskUserQuestion", "EnterPlanMode", "EnterWorktree",
]

_BASE_SYSTEM_PROMPT = (
    "You are being accessed through a non-interactive Telegram bot. "
    "Do NOT use AskUserQuestion, EnterPlanMode, or any interactive tools. "
    "Just proceed with your best judgment. Keep responses concise.\n\n"
    "When you need to send a file to the user, embed an action block in your "
    "response:\n"
    "```megobari\n"
    '{"action": "send_file", "path": "/absolute/path/to/file.pdf"}\n'
    "```\n"
    "You can add an optional \"caption\" field. "
    "The bot will send the file and strip the block from your message. "
    "Use absolute paths only.\n\n"
    "To send a photo/image (displayed inline in Telegram), use:\n"
    "```megobari\n"
    '{"action": "send_photo", "path": "/absolute/path/to/image.png"}\n'
    "```\n"
    "You can add an optional \"caption\" field.\n\n"
    "To restart the bot (e.g. after code changes), embed:\n"
    "```megobari\n"
    '{"action": "restart"}\n'
    "```\n\n"
    "When the user sends a photo or document via Telegram, it is automatically "
    "saved to the session working directory and you receive the file path. "
    "Use the Read tool to examine the file.\n\n"
    "You can save, delete, and list persistent memories using action blocks. "
    "Use these proactively to remember important facts, preferences, or context "
    "for future conversations:\n"
    "```megobari\n"
    '{"action": "memory_set", "category": "preferences", "key": "language", '
    '"value": "User prefers Georgian examples"}\n'
    "```\n"
    "```megobari\n"
    '{"action": "memory_delete", "category": "preferences", "key": "language"}\n'
    "```\n"
    "```megobari\n"
    '{"action": "memory_list", "category": "preferences"}\n'
    "```\n"
    "Category and key organize memories (e.g. preferences/language, "
    "projects/megobari, people/contacts). "
    "Saved memories are automatically included in your context for future messages."
)


def _build_system_prompt(
    session: Session, recall_context: str | None = None
) -> str:
    """Build the system prompt, including extra directories and memory recall."""
    parts = [_BASE_SYSTEM_PROMPT]

    if session.dirs:
        dirs_list = "\n".join(f"- {d}" for d in session.dirs)
        parts.append(
            f"You also have access to these additional directories "
            f"(use absolute paths to work with files in them):\n{dirs_list}"
        )

    if recall_context:
        parts.append(recall_context)

    return "\n\n".join(parts)


def _patch_message_parser() -> None:
    """Patch the SDK message parser to handle unknown message types.

    Handles events like rate_limit_event gracefully instead of crashing.
    """
    import claude_agent_sdk._internal.client as internal_client
    import claude_agent_sdk._internal.message_parser as mp

    _original_parse = mp.parse_message

    def _patched_parse(data):
        try:
            result = _original_parse(data)
        except MessageParseError:
            msg_type = data.get("type", "unknown") if isinstance(data, dict) else "unknown"
            logger.debug("Skipping unknown SDK message type: %s", msg_type)
            return SystemMessage(subtype=msg_type, data=data if isinstance(data, dict) else {})
        # Some SDK versions return None for unknown types instead of raising
        if result is None:
            msg_type = data.get("type", "unknown") if isinstance(data, dict) else "unknown"
            logger.debug("SDK returned None for message type: %s", msg_type)
        return result

    mp.parse_message = _patched_parse
    internal_client.parse_message = _patched_parse


_patch_message_parser()

# Keys whose values should be truncated in tool-use logs
_LARGE_KEYS = {"old_string", "new_string", "content", "command", "new_source"}
_MAX_VALUE_LEN = 120


def _summarize_tool_input(tool_name: str, inp: dict) -> dict:
    """Return a copy of tool input with large string values truncated for logging."""
    if not isinstance(inp, dict):
        return inp
    result = {}
    for k, v in inp.items():
        if k in _LARGE_KEYS and isinstance(v, str) and len(v) > _MAX_VALUE_LEN:
            result[k] = v[:_MAX_VALUE_LEN] + f"…({len(v)} chars)"
        else:
            result[k] = v
    return result


@dataclass
class QueryUsage:
    """Usage data from a single query, accumulated from ResultMessage."""

    cost_usd: float = 0.0
    num_turns: int = 0
    duration_api_ms: int = 0
    # Token counts from usage dict (if available)
    input_tokens: int = 0
    output_tokens: int = 0


async def _run_query(
    prompt: str,
    options: ClaudeAgentOptions,
    session: Session,
    on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str, dict], Awaitable[None]] | None = None,
) -> tuple[str, list[tuple[str, dict]], str | None, QueryUsage]:
    """Run a single query. Returns (text, tool_uses, session_id, usage)."""
    session_id: str | None = session.session_id
    text_parts: list[str] = []
    tool_uses: list[tuple[str, dict]] = []
    usage = QueryUsage()

    async for message in query(prompt=prompt, options=options):
        logger.debug("SDK message: %s", type(message).__name__)

        if isinstance(message, SystemMessage):
            if message.subtype == "init":
                sid = message.data.get("session_id")
                if sid:
                    session_id = sid
                    logger.info("Session ID: %s", sid)

        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                    if on_text_chunk and session.streaming:
                        await on_text_chunk(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_uses.append((block.name, block.input))
                    logger.info(
                        "Tool use: %s %s", block.name,
                        _summarize_tool_input(block.name, block.input),
                    )
                    if on_tool_use:
                        await on_tool_use(block.name, block.input)

        elif isinstance(message, ResultMessage):
            session_id = message.session_id
            if message.result and not text_parts:
                text_parts.append(message.result)
            if message.total_cost_usd is not None:
                usage.cost_usd += message.total_cost_usd
                usage.num_turns += message.num_turns
                usage.duration_api_ms += message.duration_api_ms
                logger.info(
                    "Result: turns=%d cost=$%.4f duration=%.1fs",
                    message.num_turns,
                    message.total_cost_usd,
                    message.duration_api_ms / 1000,
                )
            if message.usage:
                logger.info("Usage: %s", message.usage)
                usage.input_tokens += message.usage.get("input_tokens", 0)
                usage.output_tokens += message.usage.get("output_tokens", 0)

    return "\n".join(text_parts) if text_parts else "", tool_uses, session_id, usage


def _build_thinking_config(session: Session) -> dict | None:
    """Build SDK ThinkingConfig dict from session settings."""
    if session.thinking == "adaptive":
        return {"type": "adaptive"}
    if session.thinking == "enabled":
        budget = session.thinking_budget or 10000
        return {"type": "enabled", "budget_tokens": budget}
    if session.thinking == "disabled":
        return {"type": "disabled"}
    return None


def _build_options(
    session: Session, recall_context: str | None = None
) -> ClaudeAgentOptions:
    """Consolidate all ClaudeAgentOptions construction."""
    options = ClaudeAgentOptions(
        permission_mode=session.permission_mode,
        cwd=session.cwd,
        disallowed_tools=DISALLOWED_TOOLS,
        system_prompt=_build_system_prompt(session, recall_context),
    )
    thinking = _build_thinking_config(session)
    if thinking:
        options.thinking = thinking
    if session.effort:
        options.effort = session.effort
    if session.model:
        options.model = session.model
    if session.max_turns is not None:
        options.max_turns = session.max_turns
    if session.max_budget_usd is not None:
        options.max_budget_usd = session.max_budget_usd
    if session.session_id:
        options.resume = session.session_id
    return options


async def send_to_claude(
    prompt: str,
    session: Session,
    on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str, dict], Awaitable[None]] | None = None,
    recall_context: str | None = None,
) -> tuple[str, list[tuple[str, dict]], str | None, QueryUsage]:
    """Send a prompt to Claude via the Agent SDK.

    If resuming a session fails, retries as a fresh session.
    Returns (response_text, tool_uses, session_id, usage).

    Args:
        prompt: The user message to send.
        session: Active session holding model, cwd, and resume state.
        on_text_chunk: Async callback invoked with each streamed text chunk.
        on_tool_use: Async callback invoked with tool name and input dict.
        recall_context: Optional memory/summary context injected into system prompt.
    """
    logger.info(
        "Sending to Claude: prompt=%r, session_id=%s, resume=%s, "
        "permission_mode=%s, cwd=%s, thinking=%s, effort=%s",
        prompt[:200] + ("..." if len(prompt) > 200 else ""),
        session.session_id or "(new)",
        bool(session.session_id),
        session.permission_mode,
        session.cwd,
        session.thinking,
        session.effort,
    )

    options = _build_options(session, recall_context)
    empty_usage = QueryUsage()

    try:
        response, tool_uses, session_id, usage = await _run_query(
            prompt, options, session, on_text_chunk, on_tool_use
        )
    except (ProcessError, CLIConnectionError) as e:
        # If resume failed, retry without resume
        if session.session_id:
            logger.warning(
                "Resume failed (%s), retrying as fresh session...", e
            )
            options.resume = None
            try:
                response, tool_uses, session_id, usage = await _run_query(
                    prompt, options, session, on_text_chunk, on_tool_use
                )
            except Exception as retry_err:
                logger.exception("Retry also failed")
                return f"Error: {retry_err}", [], None, empty_usage
        else:
            return f"Error: {e}", [], session.session_id, empty_usage
    except CLINotFoundError:
        return (
            "Error: Claude Code CLI not found. "
            "Ensure claude-agent-sdk is installed correctly.",
            [],
            session.session_id,
            empty_usage,
        )
    except MessageParseError as e:
        logger.warning("SDK parse error (ignoring): %s", e)
        logger.warning("Raw data: %s", e.data)
        return "(response interrupted by SDK parse error)", [], session.session_id, empty_usage
    except Exception as e:
        logger.exception("Unexpected error in send_to_claude")
        return f"Error: {type(e).__name__}: {e}", [], session.session_id, empty_usage

    if not response:
        response = "(no response)"

    return response, tool_uses, session_id, usage
