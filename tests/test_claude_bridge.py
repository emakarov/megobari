"""Tests for Claude bridge integration."""

from __future__ import annotations

from unittest.mock import patch

from megobari.claude_bridge import (
    _BASE_SYSTEM_PROMPT,
    _build_system_prompt,
    _run_query,
    send_to_claude,
)
from megobari.session import Session


class TestBuildSystemPrompt:
    def test_no_dirs(self):
        session = Session(name="s")
        assert _build_system_prompt(session) == _BASE_SYSTEM_PROMPT

    def test_with_dirs(self):
        session = Session(name="s", dirs=["/a", "/b"])
        prompt = _build_system_prompt(session)
        assert _BASE_SYSTEM_PROMPT in prompt
        assert "/a" in prompt
        assert "/b" in prompt
        assert "absolute paths" in prompt


class TestRunQuery:
    async def test_text_response(self):
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock

        messages = [
            AssistantMessage(model="test", content=[TextBlock(text="Hello!")]),
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sid-1",
                total_cost_usd=0.01,
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        session = Session(name="s")
        options = ClaudeAgentOptions(
            permission_mode="default", cwd="/tmp"
        )

        with patch("megobari.claude_bridge.query", mock_query):
            text, tool_uses, sid = await _run_query(
                "hi", options, session
            )

        assert text == "Hello!"
        assert tool_uses == []
        assert sid == "sid-1"

    async def test_tool_use(self):
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
        )

        messages = [
            AssistantMessage(
                model="test",
                content=[
                    ToolUseBlock(
                        id="t1", name="Bash", input={"command": "ls"}
                    ),
                    TextBlock(text="Done."),
                ],
            ),
            ResultMessage(
                subtype="result",
                duration_ms=200,
                duration_api_ms=150,
                is_error=False,
                num_turns=1,
                session_id="sid-2",
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        session = Session(name="s")
        options = ClaudeAgentOptions(
            permission_mode="default", cwd="/tmp"
        )

        with patch("megobari.claude_bridge.query", mock_query):
            text, tool_uses, sid = await _run_query(
                "run ls", options, session
            )

        assert text == "Done."
        assert len(tool_uses) == 1
        assert tool_uses[0] == ("Bash", {"command": "ls"})

    async def test_streaming_callback(self):
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock

        messages = [
            AssistantMessage(model="test", content=[TextBlock(text="chunk1")]),
            AssistantMessage(model="test", content=[TextBlock(text="chunk2")]),
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sid-3",
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        chunks = []

        async def on_chunk(text):
            chunks.append(text)

        session = Session(name="s", streaming=True)
        options = ClaudeAgentOptions(
            permission_mode="default", cwd="/tmp"
        )

        with patch("megobari.claude_bridge.query", mock_query):
            text, _, _ = await _run_query(
                "hi", options, session, on_text_chunk=on_chunk
            )

        assert text == "chunk1\nchunk2"
        assert chunks == ["chunk1", "chunk2"]

    async def test_init_message_extracts_session_id(self):
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage

        messages = [
            SystemMessage(
                subtype="init", data={"session_id": "init-sid"}
            ),
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="result-sid",
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        session = Session(name="s")
        options = ClaudeAgentOptions(
            permission_mode="default", cwd="/tmp"
        )

        with patch("megobari.claude_bridge.query", mock_query):
            _, _, sid = await _run_query("hi", options, session)

        # ResultMessage session_id takes precedence
        assert sid == "result-sid"

    async def test_result_fallback_text(self):
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

        messages = [
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sid",
                result="fallback text",
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        session = Session(name="s")
        options = ClaudeAgentOptions(
            permission_mode="default", cwd="/tmp"
        )

        with patch("megobari.claude_bridge.query", mock_query):
            text, _, _ = await _run_query("hi", options, session)

        assert text == "fallback text"


class TestSendToClaude:
    async def test_success(self):
        session = Session(name="s", cwd="/tmp")

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.return_value = ("response", [], "sid-1")
            text, tools, sid = await send_to_claude("hi", session)

        assert text == "response"
        assert sid == "sid-1"

    async def test_empty_response(self):
        session = Session(name="s", cwd="/tmp")

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.return_value = ("", [], "sid-1")
            text, _, _ = await send_to_claude("hi", session)

        assert text == "(no response)"

    async def test_cli_not_found(self):
        from claude_agent_sdk import CLINotFoundError

        session = Session(name="s", cwd="/tmp")

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.side_effect = CLINotFoundError()
            text, tools, sid = await send_to_claude("hi", session)

        assert "not found" in text.lower()
        assert tools == []

    async def test_process_error_with_resume(self):
        from claude_agent_sdk import ProcessError

        session = Session(
            name="s", cwd="/tmp", session_id="old-sid"
        )

        call_count = 0

        async def mock_rq(prompt, options, session, on_text_chunk=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProcessError("fail")
            return ("retried", [], "new-sid")

        with patch("megobari.claude_bridge._run_query", mock_rq):
            text, _, sid = await send_to_claude("hi", session)

        assert text == "retried"
        assert call_count == 2

    async def test_process_error_no_resume(self):
        from claude_agent_sdk import ProcessError

        session = Session(name="s", cwd="/tmp")

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.side_effect = ProcessError("fail")
            text, tools, sid = await send_to_claude("hi", session)

        assert "Error" in text

    async def test_generic_exception(self):
        session = Session(name="s", cwd="/tmp")

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.side_effect = ValueError("boom")
            text, tools, sid = await send_to_claude("hi", session)

        assert "ValueError" in text
        assert "boom" in text

    async def test_retry_also_fails(self):
        from claude_agent_sdk import ProcessError

        session = Session(
            name="s", cwd="/tmp", session_id="old-sid"
        )

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.side_effect = ProcessError("fail")
            text, tools, sid = await send_to_claude("hi", session)

        assert "Error" in text
        assert sid is None

    async def test_sets_resume_option(self):
        session = Session(
            name="s", cwd="/tmp", session_id="existing-sid"
        )

        with patch("megobari.claude_bridge._run_query") as mock_rq:
            mock_rq.return_value = ("ok", [], "sid")
            await send_to_claude("hi", session)
            call_args = mock_rq.call_args
            options = call_args[0][1]
            assert options.resume == "existing-sid"
