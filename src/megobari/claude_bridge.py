"""Claude Code Agent SDK integration layer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

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
    "To restart the bot (e.g. after code changes), embed:\n"
    "```megobari\n"
    '{"action": "restart"}\n'
    "```"
)


def _build_system_prompt(session: Session) -> str:
    """Build the system prompt, including extra directories if configured."""
    if not session.dirs:
        return _BASE_SYSTEM_PROMPT
    dirs_list = "\n".join(f"- {d}" for d in session.dirs)
    return (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        f"You also have access to these additional directories "
        f"(use absolute paths to work with files in them):\n{dirs_list}"
    )


def _patch_message_parser() -> None:
    """Patch the SDK message parser to handle unknown message types.

    Handles events like rate_limit_event gracefully instead of crashing.
    """
    import claude_agent_sdk._internal.client as internal_client
    import claude_agent_sdk._internal.message_parser as mp

    _original_parse = mp.parse_message

    def _patched_parse(data):
        try:
            return _original_parse(data)
        except MessageParseError:
            msg_type = data.get("type", "unknown") if isinstance(data, dict) else "unknown"
            logger.debug("Skipping unknown SDK message type: %s", msg_type)
            return SystemMessage(subtype=msg_type, data=data if isinstance(data, dict) else {})

    mp.parse_message = _patched_parse
    internal_client.parse_message = _patched_parse


_patch_message_parser()


async def _run_query(
    prompt: str,
    options: ClaudeAgentOptions,
    session: Session,
    on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str, dict], Awaitable[None]] | None = None,
) -> tuple[str, list[tuple[str, dict]], str | None]:
    """Run a single query. Returns (text_parts joined, tool_uses, session_id)."""
    session_id: str | None = session.session_id
    text_parts: list[str] = []
    tool_uses: list[tuple[str, dict]] = []

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
                    logger.info("Tool use: %s %s", block.name, block.input)
                    if on_tool_use:
                        await on_tool_use(block.name, block.input)

        elif isinstance(message, ResultMessage):
            session_id = message.session_id
            if message.result and not text_parts:
                text_parts.append(message.result)
            if message.total_cost_usd is not None:
                logger.info(
                    "Result: turns=%d cost=$%.4f duration=%.1fs",
                    message.num_turns,
                    message.total_cost_usd,
                    message.duration_api_ms / 1000,
                )
            if message.usage:
                logger.info("Usage: %s", message.usage)

    return "\n".join(text_parts) if text_parts else "", tool_uses, session_id


async def send_to_claude(
    prompt: str,
    session: Session,
    on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str, dict], Awaitable[None]] | None = None,
) -> tuple[str, list[tuple[str, dict]], str | None]:
    """Send a prompt to Claude via the Agent SDK.

    If resuming a session fails, retries as a fresh session.
    Returns (response_text, tool_uses, session_id).
    """
    logger.info(
        "Sending to Claude: prompt=%r, session_id=%s, resume=%s, "
        "permission_mode=%s, cwd=%s",
        prompt[:200] + ("..." if len(prompt) > 200 else ""),
        session.session_id or "(new)",
        bool(session.session_id),
        session.permission_mode,
        session.cwd,
    )

    options = ClaudeAgentOptions(
        permission_mode=session.permission_mode,
        cwd=session.cwd,
        disallowed_tools=DISALLOWED_TOOLS,
        system_prompt=_build_system_prompt(session),
    )
    if session.session_id:
        options.resume = session.session_id

    try:
        response, tool_uses, session_id = await _run_query(
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
                response, tool_uses, session_id = await _run_query(
                    prompt, options, session, on_text_chunk, on_tool_use
                )
            except Exception as retry_err:
                logger.exception("Retry also failed")
                return f"Error: {retry_err}", [], None
        else:
            return f"Error: {e}", [], session.session_id
    except CLINotFoundError:
        return (
            "Error: Claude Code CLI not found. "
            "Ensure claude-agent-sdk is installed correctly.",
            [],
            session.session_id,
        )
    except MessageParseError as e:
        logger.warning("SDK parse error (ignoring): %s", e)
        logger.warning("Raw data: %s", e.data)
        return "(response interrupted by SDK parse error)", [], session.session_id
    except Exception as e:
        logger.exception("Unexpected error in send_to_claude")
        return f"Error: {type(e).__name__}: {e}", [], session.session_id

    if not response:
        response = "(no response)"

    return response, tool_uses, session_id
