# OpenClaw-Inspired Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `/compact`, `/think`, `/effort`, `/usage`, and `/doctor` commands to megobari.

**Architecture:** Extend `Session` dataclass with `thinking`/`thinking_budget`/`effort` fields (persisted). Track usage in-memory via `bot_data["usage"]`. Wire thinking/effort into `ClaudeAgentOptions`. `/compact` does summarize-then-reset. `/doctor` runs stateless health checks.

**Tech Stack:** python-telegram-bot v22, claude-agent-sdk (ClaudeAgentOptions.thinking, .effort, ResultMessage.total_cost_usd/usage/num_turns/duration_api_ms)

---

### Task 1: Add thinking/effort fields to Session

**Files:**
- Modify: `src/megobari/session.py`
- Test: `tests/test_session.py`

**Step 1: Write the failing tests**

Add to `tests/test_session.py`:

```python
class TestSessionThinkingEffort:
    def test_defaults(self):
        s = Session(name="s")
        assert s.thinking == "adaptive"
        assert s.thinking_budget is None
        assert s.effort is None

    def test_custom_values(self):
        s = Session(name="s", thinking="enabled", thinking_budget=5000, effort="high")
        assert s.thinking == "enabled"
        assert s.thinking_budget == 5000
        assert s.effort == "high"

    def test_persistence_round_trip(self, tmp_sessions_dir):
        sm1 = SessionManager(tmp_sessions_dir)
        sm1.create("t")
        session = sm1.get("t")
        session.thinking = "disabled"
        session.effort = "max"
        sm1._save()

        sm2 = SessionManager(tmp_sessions_dir)
        sm2.load_from_disk()
        loaded = sm2.get("t")
        assert loaded.thinking == "disabled"
        assert loaded.effort == "max"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_session.py::TestSessionThinkingEffort -v`
Expected: FAIL — `Session.__init__() got an unexpected keyword argument 'thinking'`

**Step 3: Add fields and type aliases to session.py**

In `src/megobari/session.py`, add after the `PermissionMode` and `VALID_PERMISSION_MODES` lines:

```python
ThinkingMode = Literal["adaptive", "enabled", "disabled"]
VALID_THINKING_MODES: set[str] = {"adaptive", "enabled", "disabled"}

EffortLevel = Literal["low", "medium", "high", "max"]
VALID_EFFORT_LEVELS: set[str] = {"low", "medium", "high", "max"}
```

Add to `Session` dataclass after `dirs`:

```python
thinking: ThinkingMode = "adaptive"
thinking_budget: int | None = None
effort: EffortLevel | None = None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session.py -v`
Expected: ALL PASS

**Step 5: Run linters**

Run: `uv run flake8 src/megobari/session.py && uv run isort --check src/megobari/session.py`
Expected: Clean

**Step 6: Commit**

```bash
git add src/megobari/session.py tests/test_session.py
git commit -m "feat: add thinking/effort fields to Session dataclass"
```

---

### Task 2: Add SessionUsage dataclass and format_usage/format_doctor to message_utils

**Files:**
- Modify: `src/megobari/message_utils.py`
- Test: `tests/test_message_utils.py`

**Step 1: Write the failing tests**

Add to `tests/test_message_utils.py`:

```python
from megobari.message_utils import format_doctor, format_usage, SessionUsage


class TestSessionUsage:
    def test_defaults(self):
        u = SessionUsage()
        assert u.total_cost_usd == 0.0
        assert u.total_turns == 0
        assert u.total_duration_ms == 0
        assert u.message_count == 0

    def test_accumulate(self):
        u = SessionUsage()
        u.total_cost_usd += 0.05
        u.total_turns += 3
        u.total_duration_ms += 5000
        u.message_count += 1
        assert u.total_cost_usd == 0.05
        assert u.message_count == 1


class TestFormatUsage:
    def test_basic(self):
        u = SessionUsage(
            total_cost_usd=0.0342,
            total_turns=12,
            total_duration_ms=45200,
            message_count=5,
        )
        text = format_usage("megobari", u)
        assert "megobari" in text
        assert "$0.0342" in text
        assert "12" in text
        assert "5" in text
        assert "45.2s" in text

    def test_zero_usage(self):
        u = SessionUsage()
        text = format_usage("empty", u)
        assert "empty" in text
        assert "$0.0000" in text

    def test_html_formatting(self):
        fmt = TelegramFormatter()
        u = SessionUsage(total_cost_usd=0.01, total_turns=1,
                         total_duration_ms=1000, message_count=1)
        text = format_usage("s", u, fmt)
        assert "<b>" in text


class TestFormatDoctor:
    def test_all_healthy(self):
        checks = [
            ("Claude CLI", True, "v0.1.39"),
            ("Sessions", True, "3 sessions, 12.5 KB"),
        ]
        text = format_doctor(checks)
        assert "Claude CLI" in text
        assert "v0.1.39" in text

    def test_unhealthy_check(self):
        checks = [
            ("Claude CLI", False, "not found"),
        ]
        text = format_doctor(checks)
        assert "not found" in text

    def test_html_formatting(self):
        fmt = TelegramFormatter()
        checks = [("CLI", True, "ok")]
        text = format_doctor(checks, fmt)
        assert "<b>" in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_message_utils.py::TestSessionUsage tests/test_message_utils.py::TestFormatUsage tests/test_message_utils.py::TestFormatDoctor -v`
Expected: FAIL — ImportError

**Step 3: Implement SessionUsage, format_usage, format_doctor**

Add `SessionUsage` dataclass at top of `src/megobari/message_utils.py` (after imports):

```python
from dataclasses import dataclass


@dataclass
class SessionUsage:
    """In-memory usage tracking for a session."""

    total_cost_usd: float = 0.0
    total_turns: int = 0
    total_duration_ms: int = 0
    message_count: int = 0
```

Add `format_usage` function:

```python
def format_usage(
    session_name: str, usage: SessionUsage, fmt: Formatter | None = None
) -> str:
    """Format session usage stats for display."""
    if fmt is None:
        fmt = PlainTextFormatter()

    def line(label: str, value: str) -> str:
        return f"{fmt.bold(label + ':')} {fmt.escape(value)}"

    api_seconds = usage.total_duration_ms / 1000
    lines = [
        line("Session", session_name),
        line("Cost", f"${usage.total_cost_usd:.4f}"),
        line("Turns", f"{usage.total_turns} (across {usage.message_count} messages)"),
        line("API time", f"{api_seconds:.1f}s"),
    ]
    return "\n".join(lines)
```

Add `format_doctor` function:

```python
def format_doctor(
    checks: list[tuple[str, bool, str]], fmt: Formatter | None = None
) -> str:
    """Format doctor check results for display."""
    if fmt is None:
        fmt = PlainTextFormatter()

    lines = [fmt.bold("Health Check:"), ""]
    for name, ok, detail in checks:
        icon = "\u2705" if ok else "\u274c"
        lines.append(f"{icon} {fmt.bold(fmt.escape(name))} \u2014 {fmt.escape(detail)}")
    return "\n".join(lines)
```

Also update `format_help` to include the 5 new commands. Add these entries to the `cmds` list:

```python
(f"/think {fmt.code('<mode>')}", "Set thinking: adaptive|on [budget]|off"),
(f"/effort {fmt.code('<level>')}", "Set effort: low|medium|high|max|off"),
("/usage", "Show session usage stats"),
("/compact", "Summarize and reset context"),
("/doctor", "Run health checks"),
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_message_utils.py -v`
Expected: ALL PASS

**Step 5: Run linters**

Run: `uv run flake8 src/megobari/message_utils.py && uv run isort --check src/megobari/message_utils.py`
Expected: Clean

**Step 6: Commit**

```bash
git add src/megobari/message_utils.py tests/test_message_utils.py
git commit -m "feat: add SessionUsage, format_usage, format_doctor utilities"
```

---

### Task 3: Wire thinking/effort into claude_bridge and return usage data

**Files:**
- Modify: `src/megobari/claude_bridge.py`
- Test: `tests/test_claude_bridge.py`

**Step 1: Write the failing tests**

Add to `tests/test_claude_bridge.py`:

```python
class TestBuildOptions:
    def test_default_session(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp")
        opts = build_options(session)
        assert opts.permission_mode == "default"
        assert opts.cwd == "/tmp"
        assert opts.thinking is None  # adaptive = no explicit setting
        assert opts.effort is None

    def test_thinking_enabled(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp", thinking="enabled", thinking_budget=5000)
        opts = build_options(session)
        assert opts.thinking == {"type": "enabled", "budget_tokens": 5000}

    def test_thinking_disabled(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp", thinking="disabled")
        opts = build_options(session)
        assert opts.thinking == {"type": "disabled"}

    def test_thinking_adaptive(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp", thinking="adaptive")
        opts = build_options(session)
        # adaptive is the SDK default, so don't set it explicitly
        assert opts.thinking is None

    def test_effort_set(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp", effort="high")
        opts = build_options(session)
        assert opts.effort == "high"

    def test_effort_none(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp")
        opts = build_options(session)
        assert opts.effort is None

    def test_resume_set(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp", session_id="sid-123")
        opts = build_options(session)
        assert opts.resume == "sid-123"

    def test_resume_not_set(self):
        from megobari.claude_bridge import build_options
        session = Session(name="s", cwd="/tmp")
        opts = build_options(session)
        assert opts.resume is None


class TestRunQueryUsageData:
    async def test_returns_usage_data(self):
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock

        messages = [
            AssistantMessage(model="test", content=[TextBlock(text="Hi")]),
            ResultMessage(
                subtype="result",
                duration_ms=500,
                duration_api_ms=400,
                is_error=False,
                num_turns=3,
                session_id="sid",
                total_cost_usd=0.05,
                usage={"input_tokens": 100},
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        session = Session(name="s")
        options = ClaudeAgentOptions(permission_mode="default", cwd="/tmp")

        with patch("megobari.claude_bridge.query", mock_query):
            text, tool_uses, sid, usage_data = await _run_query("hi", options, session)

        assert usage_data["total_cost_usd"] == 0.05
        assert usage_data["num_turns"] == 3
        assert usage_data["duration_api_ms"] == 400

    async def test_returns_empty_usage_when_no_cost(self):
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

        messages = [
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sid",
            ),
        ]

        async def mock_query(**kwargs):
            for m in messages:
                yield m

        session = Session(name="s")
        options = ClaudeAgentOptions(permission_mode="default", cwd="/tmp")

        with patch("megobari.claude_bridge.query", mock_query):
            text, tool_uses, sid, usage_data = await _run_query("hi", options, session)

        assert usage_data["total_cost_usd"] is None
        assert usage_data["num_turns"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_claude_bridge.py::TestBuildOptions tests/test_claude_bridge.py::TestRunQueryUsageData -v`
Expected: FAIL — ImportError for `build_options`, wrong return tuple length for `_run_query`

**Step 3: Implement changes to claude_bridge.py**

3a. Add `build_options` function:

```python
def build_options(session: Session) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions from a Session's configuration."""
    thinking = None
    if session.thinking == "enabled":
        budget = session.thinking_budget or 10000
        thinking = {"type": "enabled", "budget_tokens": budget}
    elif session.thinking == "disabled":
        thinking = {"type": "disabled"}
    # "adaptive" → leave as None (SDK default)

    options = ClaudeAgentOptions(
        permission_mode=session.permission_mode,
        cwd=session.cwd,
        disallowed_tools=DISALLOWED_TOOLS,
        system_prompt=_build_system_prompt(session),
        thinking=thinking,
        effort=session.effort,
    )
    if session.session_id:
        options.resume = session.session_id
    return options
```

3b. Change `_run_query` return type to include usage data dict. Add a `usage_data` dict built from ResultMessage fields. Return 4-tuple instead of 3-tuple:

```python
async def _run_query(
    prompt, options, session, on_text_chunk=None, on_tool_use=None
) -> tuple[str, list[tuple[str, dict]], str | None, dict]:
    ...
    usage_data: dict = {}
    ...
    # In the ResultMessage handler, add:
    usage_data = {
        "total_cost_usd": message.total_cost_usd,
        "num_turns": message.num_turns,
        "duration_api_ms": message.duration_api_ms,
    }
    ...
    return "\n".join(text_parts) if text_parts else "", tool_uses, session_id, usage_data
```

3c. Update `send_to_claude` to use `build_options` and return 4-tuple. Replace inline `ClaudeAgentOptions(...)` construction with `build_options(session)`. Return `usage_data` as 4th element.

**Step 4: Fix existing tests that expect 3-tuple returns**

All existing tests that call `_run_query` or `send_to_claude` and unpack 3 values need updating to unpack 4. This affects:
- `TestRunQuery` — all methods: `text, tool_uses, sid` → `text, tool_uses, sid, _`
- `TestSendToClaude` — all methods: `text, tools, sid` → `text, tools, sid, _`
- `TestRunQueryEdgeCases` — all methods similarly

**Step 5: Run all tests**

Run: `uv run pytest tests/test_claude_bridge.py -v`
Expected: ALL PASS

**Step 6: Run full test suite to check nothing else broke**

Run: `uv run pytest -v`
Expected: ALL PASS (bot.py tests also unpack send_to_claude results but via mock — check if they need updating)

**Step 7: Run linters**

Run: `uv run flake8 src/megobari/claude_bridge.py && uv run isort --check src/megobari/claude_bridge.py`
Expected: Clean

**Step 8: Commit**

```bash
git add src/megobari/claude_bridge.py tests/test_claude_bridge.py
git commit -m "feat: wire thinking/effort into ClaudeAgentOptions, return usage data"
```

---

### Task 4: Add /think and /effort command handlers

**Files:**
- Modify: `src/megobari/bot.py`
- Test: `tests/test_bot.py`

**Step 1: Write the failing tests**

Add to `tests/test_bot.py`:

```python
class TestCmdThink:
    async def test_show_current(self, session_manager):
        from megobari.bot import cmd_think
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "adaptive" in text

    async def test_set_off(self, session_manager):
        from megobari.bot import cmd_think
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["off"])
        await cmd_think(update, ctx)
        assert session_manager.current.thinking == "disabled"

    async def test_set_adaptive(self, session_manager):
        from megobari.bot import cmd_think
        session_manager.create("s")
        session_manager.current.thinking = "disabled"
        update = _make_update()
        ctx = _make_context(session_manager, args=["adaptive"])
        await cmd_think(update, ctx)
        assert session_manager.current.thinking == "adaptive"

    async def test_set_on_default_budget(self, session_manager):
        from megobari.bot import cmd_think
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["on"])
        await cmd_think(update, ctx)
        assert session_manager.current.thinking == "enabled"
        assert session_manager.current.thinking_budget == 10000

    async def test_set_on_custom_budget(self, session_manager):
        from megobari.bot import cmd_think
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["on", "5000"])
        await cmd_think(update, ctx)
        assert session_manager.current.thinking == "enabled"
        assert session_manager.current.thinking_budget == 5000

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_think
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_invalid_budget(self, session_manager):
        from megobari.bot import cmd_think
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["on", "abc"])
        await cmd_think(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "number" in text.lower() or "invalid" in text.lower()


class TestCmdEffort:
    async def test_show_current(self, session_manager):
        from megobari.bot import cmd_effort
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_effort(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "off" in text.lower() or "not set" in text.lower()

    async def test_set_high(self, session_manager):
        from megobari.bot import cmd_effort
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["high"])
        await cmd_effort(update, ctx)
        assert session_manager.current.effort == "high"

    async def test_set_off(self, session_manager):
        from megobari.bot import cmd_effort
        session_manager.create("s")
        session_manager.current.effort = "high"
        update = _make_update()
        ctx = _make_context(session_manager, args=["off"])
        await cmd_effort(update, ctx)
        assert session_manager.current.effort is None

    async def test_invalid_level(self, session_manager):
        from megobari.bot import cmd_effort
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager, args=["turbo"])
        await cmd_effort(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "low" in text

    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_effort
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_effort(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot.py::TestCmdThink tests/test_bot.py::TestCmdEffort -v`
Expected: FAIL — ImportError

**Step 3: Implement cmd_think and cmd_effort in bot.py**

Add import at top of `bot.py`:

```python
from megobari.session import VALID_EFFORT_LEVELS, VALID_PERMISSION_MODES, VALID_THINKING_MODES, SessionManager
```

Add `cmd_think`:

```python
async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /think command to set extended thinking mode."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    if not context.args:
        budget_info = f" (budget: {session.thinking_budget})" if session.thinking == "enabled" else ""
        await _reply(
            update,
            f"Thinking: {session.thinking}{budget_info}\n\n"
            f"Usage: /think adaptive|on [budget]|off",
        )
        return
    mode = context.args[0].lower()
    if mode == "off":
        session.thinking = "disabled"
        session.thinking_budget = None
        sm._save()
        await _reply(update, "Thinking disabled.")
    elif mode == "adaptive":
        session.thinking = "adaptive"
        session.thinking_budget = None
        sm._save()
        await _reply(update, "Thinking set to adaptive.")
    elif mode == "on":
        budget = 10000
        if len(context.args) > 1:
            try:
                budget = int(context.args[1])
            except ValueError:
                await _reply(update, "Invalid number for budget.")
                return
        session.thinking = "enabled"
        session.thinking_budget = budget
        sm._save()
        await _reply(update, f"Thinking enabled (budget: {budget} tokens).")
    else:
        await _reply(update, "Usage: /think adaptive|on [budget]|off")
```

Add `cmd_effort`:

```python
async def cmd_effort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /effort command to set effort level."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    if not context.args:
        current = session.effort or "not set"
        levels = ", ".join(sorted(VALID_EFFORT_LEVELS))
        await _reply(update, f"Effort: {current}\n\nUsage: /effort {levels}|off")
        return
    level = context.args[0].lower()
    if level == "off":
        session.effort = None
        sm._save()
        await _reply(update, "Effort level cleared (using default).")
    elif level in VALID_EFFORT_LEVELS:
        session.effort = level
        sm._save()
        await _reply(update, f"Effort set to '{level}'.")
    else:
        levels = ", ".join(sorted(VALID_EFFORT_LEVELS))
        await _reply(update, f"Usage: /effort {levels}|off")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot.py::TestCmdThink tests/test_bot.py::TestCmdEffort -v`
Expected: ALL PASS

**Step 5: Run linters**

Run: `uv run flake8 src/megobari/bot.py && uv run isort --check src/megobari/bot.py`

**Step 6: Commit**

```bash
git add src/megobari/bot.py tests/test_bot.py
git commit -m "feat: add /think and /effort commands"
```

---

### Task 5: Add /usage command handler with accumulation

**Files:**
- Modify: `src/megobari/bot.py`
- Test: `tests/test_bot.py`

**Step 1: Write the failing tests**

Add to `tests/test_bot.py`:

```python
class TestCmdUsage:
    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_usage
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_no_usage_data(self, session_manager):
        from megobari.bot import cmd_usage
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)
        ctx.bot_data["usage"] = {}
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "$0.0000" in text

    async def test_with_usage_data(self, session_manager):
        from megobari.bot import cmd_usage
        from megobari.message_utils import SessionUsage
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)
        ctx.bot_data["usage"] = {
            "s": SessionUsage(
                total_cost_usd=0.05, total_turns=10,
                total_duration_ms=30000, message_count=3,
            )
        }
        await cmd_usage(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "$0.0500" in text
        assert "10" in text
        assert "3" in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot.py::TestCmdUsage -v`
Expected: FAIL — ImportError

**Step 3: Implement cmd_usage in bot.py**

Add import:

```python
from megobari.message_utils import (
    SessionUsage,
    format_help,
    format_session_info,
    format_session_list,
    format_tool_summary,
    format_usage,
    split_message,
    tool_status_text,
)
```

Add handler:

```python
async def cmd_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /usage command to show session usage stats."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    usage_store: dict = context.bot_data.setdefault("usage", {})
    usage = usage_store.get(session.name, SessionUsage())
    await _reply(update, format_usage(session.name, usage, fmt), formatted=True)
```

Also, update `_process_prompt` to accumulate usage after each `send_to_claude` call. After the line `if new_session_id:`, add usage accumulation:

```python
# Accumulate usage stats
if usage_data:
    usage_store: dict = context.bot_data.setdefault("usage", {})
    u = usage_store.setdefault(session.name, SessionUsage())
    if usage_data.get("total_cost_usd") is not None:
        u.total_cost_usd += usage_data["total_cost_usd"]
    u.total_turns += usage_data.get("num_turns", 0)
    u.total_duration_ms += usage_data.get("duration_api_ms", 0)
    u.message_count += 1
```

Note: `_process_prompt` calls `send_to_claude` which now returns 4-tuple. Update both the streaming and non-streaming branches to unpack `usage_data`:

```python
response_text, tool_uses, new_session_id, usage_data = await send_to_claude(...)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot.py::TestCmdUsage -v`
Expected: ALL PASS

**Step 5: Run full suite**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/megobari/bot.py tests/test_bot.py
git commit -m "feat: add /usage command with per-session accumulation"
```

---

### Task 6: Add /compact command handler

**Files:**
- Modify: `src/megobari/bot.py`
- Test: `tests/test_bot.py`

**Step 1: Write the failing tests**

Add to `tests/test_bot.py`:

```python
class TestCmdCompact:
    async def test_no_session(self, session_manager):
        from megobari.bot import cmd_compact
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_compact(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "No active session" in text

    async def test_no_context_to_compact(self, session_manager):
        from megobari.bot import cmd_compact
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_compact(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "no context" in text.lower() or "nothing" in text.lower()

    @patch("megobari.bot.send_to_claude")
    async def test_compact_success(self, mock_send, session_manager):
        from megobari.bot import cmd_compact
        session_manager.create("s")
        session_manager.update_session_id("s", "old-sid")
        update = _make_update()
        ctx = _make_context(session_manager)
        ctx.bot_data["usage"] = {}

        # First call: summarize. Second call: seed new session.
        mock_send.side_effect = [
            ("Summary: we discussed X and Y.", [], "sid-1", {}),
            ("Got it, context loaded.", [], "sid-2", {}),
        ]

        await cmd_compact(update, ctx)

        # Session ID should be updated to the new one
        assert session_manager.current.session_id == "sid-2"
        # Should have called send_to_claude twice
        assert mock_send.call_count == 2
        # User should see the summary
        calls = update.message.reply_text.call_args_list
        found_summary = any("Summary" in str(c) for c in calls)
        assert found_summary

    @patch("megobari.bot.send_to_claude")
    async def test_compact_summary_fails(self, mock_send, session_manager):
        from megobari.bot import cmd_compact
        session_manager.create("s")
        session_manager.update_session_id("s", "old-sid")
        update = _make_update()
        ctx = _make_context(session_manager)
        ctx.bot_data["usage"] = {}

        mock_send.return_value = ("Error: something broke", [], None, {})

        await cmd_compact(update, ctx)

        # Should report the error, not crash
        calls = update.message.reply_text.call_args_list
        found_error = any("failed" in str(c).lower() or "error" in str(c).lower() for c in calls)
        assert found_error
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot.py::TestCmdCompact -v`
Expected: FAIL — ImportError

**Step 3: Implement cmd_compact in bot.py**

```python
_COMPACT_PROMPT = (
    "Summarize our conversation so far into key context points that would help "
    "you continue this work in a fresh session. Be concise — bullet points preferred."
)


async def cmd_compact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /compact command to summarize and reset context."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    if not session.session_id:
        await _reply(update, "Nothing to compact — no context in this session yet.")
        return

    await _reply(update, "Compacting context...")

    # Step 1: Ask Claude to summarize the conversation
    summary, _, _, _ = await send_to_claude(_COMPACT_PROMPT, session)

    if summary.startswith("Error"):
        await _reply(update, f"Compact failed: {summary}")
        return

    # Step 2: Reset session context
    session.session_id = None

    # Step 3: Seed new session with the summary
    seed_prompt = (
        "This is a compacted context summary from our previous conversation. "
        "Use it as background context:\n\n" + summary
    )
    _, _, new_session_id, _ = await send_to_claude(seed_prompt, session)

    if new_session_id:
        sm.update_session_id(session.name, new_session_id)

    await _reply(update, f"Context compacted.\n\n{summary}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot.py::TestCmdCompact -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/megobari/bot.py tests/test_bot.py
git commit -m "feat: add /compact command for context summarization and reset"
```

---

### Task 7: Add /doctor command handler

**Files:**
- Modify: `src/megobari/bot.py`
- Test: `tests/test_bot.py`

**Step 1: Write the failing tests**

Add to `tests/test_bot.py`:

```python
class TestCmdDoctor:
    async def test_runs_checks(self, session_manager):
        from megobari.bot import cmd_doctor
        session_manager.create("s")
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_doctor(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Health Check" in text or "CLI" in text

    async def test_reports_session_count(self, session_manager):
        from megobari.bot import cmd_doctor
        session_manager.create("a")
        session_manager.create("b")
        update = _make_update()
        ctx = _make_context(session_manager)
        await cmd_doctor(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "2" in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bot.py::TestCmdDoctor -v`
Expected: FAIL — ImportError

**Step 3: Implement cmd_doctor in bot.py**

Add import at top:

```python
from megobari.message_utils import format_doctor
```

Add handler:

```python
async def cmd_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /doctor command to run health checks."""
    sm = _get_sm(context)
    checks: list[tuple[str, bool, str]] = []

    # Check 1: Claude CLI reachable
    try:
        import claude_agent_sdk
        version = getattr(claude_agent_sdk, "__version__", "unknown")
        checks.append(("Claude CLI", True, f"SDK v{version}"))
    except ImportError:
        checks.append(("Claude CLI", False, "claude-agent-sdk not installed"))

    # Check 2: Session health
    sessions = sm.list_all()
    sessions_path = sm._sessions_dir / "sessions.json"
    try:
        size_bytes = sessions_path.stat().st_size if sessions_path.exists() else 0
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        else:
            size_str = f"{size_bytes / 1024:.1f} KB"
        stale = sum(1 for s in sessions if s.session_id and not s.last_used_at)
        detail = f"{len(sessions)} sessions, {size_str}"
        if stale:
            detail += f", {stale} stale"
        checks.append(("Sessions", True, detail))
    except Exception as e:
        checks.append(("Sessions", False, str(e)))

    await _reply(update, format_doctor(checks, fmt), formatted=True)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot.py::TestCmdDoctor -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/megobari/bot.py tests/test_bot.py
git commit -m "feat: add /doctor command for health checks"
```

---

### Task 8: Register new command handlers in create_application

**Files:**
- Modify: `src/megobari/bot.py`
- Test: `tests/test_bot.py`

**Step 1: Write the failing test**

Add to `tests/test_bot.py` in the existing `TestCreateApplication` class (or create if missing):

```python
class TestNewCommandsRegistered:
    def test_new_commands_registered(self, session_manager):
        from megobari.bot import create_application
        from megobari.config import Config
        config = Config(bot_token="fake:token", allowed_user_id=12345)
        app = create_application(session_manager, config)
        handler_commands = set()
        for handler in app.handlers.get(0, []):
            if hasattr(handler, "commands"):
                handler_commands.update(handler.commands)
        for cmd in ("think", "effort", "usage", "compact", "doctor"):
            assert cmd in handler_commands, f"/{cmd} not registered"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot.py::TestNewCommandsRegistered -v`
Expected: FAIL — commands not found

**Step 3: Add handler registrations to create_application**

In `create_application`, add after the existing `CommandHandler` registrations (before the `MessageHandler` for text):

```python
app.add_handler(CommandHandler("think", cmd_think, filters=user_filter))
app.add_handler(CommandHandler("effort", cmd_effort, filters=user_filter))
app.add_handler(CommandHandler("usage", cmd_usage, filters=user_filter))
app.add_handler(CommandHandler("compact", cmd_compact, filters=user_filter))
app.add_handler(CommandHandler("doctor", cmd_doctor, filters=user_filter))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bot.py::TestNewCommandsRegistered -v`
Expected: PASS

**Step 5: Run full test suite and linters**

Run: `uv run pytest -v && uv run flake8 src/ tests/ && uv run isort --check src/ tests/`
Expected: ALL PASS, clean lint

**Step 6: Commit**

```bash
git add src/megobari/bot.py tests/test_bot.py
git commit -m "feat: register /think, /effort, /usage, /compact, /doctor handlers"
```

---

### Task 9: Final integration test and cleanup

**Step 1: Run full test suite with coverage**

Run: `uv run pytest --cov=megobari --cov-report=term-missing -v`
Expected: ALL PASS, coverage >= 95%

**Step 2: Run all linters**

Run: `uv run flake8 src/ tests/ && uv run isort --check src/ tests/ && uv run pydocstyle --config=pyproject.toml src/`
Expected: Clean

**Step 3: Verify help text includes new commands**

Run: `uv run pytest tests/test_message_utils.py::TestFormatHelp -v`
Expected: PASS — verify `/think`, `/effort`, `/usage`, `/compact`, `/doctor` appear in help

**Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup for openclaw-inspired features"
```
