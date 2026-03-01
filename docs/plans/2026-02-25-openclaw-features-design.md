# Design: /compact, /think, /effort, /usage, /doctor

Inspired by OpenClaw and ZeroClaw feature sets, adapted to megobari's architecture.

## Data Model

### Session fields (persisted)

```python
thinking: ThinkingMode = "adaptive"    # "adaptive" | "enabled" | "disabled"
thinking_budget: int | None = None     # budget_tokens when thinking="enabled"
effort: EffortLevel | None = None      # "low" | "medium" | "high" | "max" | None
```

Type aliases `ThinkingMode` and `EffortLevel` follow the `PermissionMode` pattern with validation sets.

### Usage tracking (in-memory only)

```python
@dataclass
class SessionUsage:
    total_cost_usd: float = 0.0
    total_turns: int = 0
    total_duration_ms: int = 0
    message_count: int = 0
```

Stored in `bot_data["usage"][session_name]`. Resets on bot restart. Accumulated from `ResultMessage` after each query.

## Commands

### /think <mode>

Controls extended thinking via SDK `ThinkingConfig`.

- `/think` — show current setting
- `/think adaptive` — let Claude decide (default)
- `/think on [budget]` — enable with optional budget_tokens (default 10000)
- `/think off` — disable thinking

### /effort <level>

Controls effort level via SDK `effort` field.

- `/effort` — show current setting
- `/effort low|medium|high|max` — set level
- `/effort off` — clear (use SDK default)

### /usage

Show accumulated stats for current session (on-demand only).

Output format:
```
Session: <name>
Cost: $0.0342
Turns: 12 (across 5 messages)
API time: 45.2s
```

### /compact

Summarize conversation and reset context.

1. Send prompt: "Summarize our conversation into key context points. Be concise."
2. Capture summary response
3. Clear `session_id` (breaks context)
4. Send summary as first message of fresh session to seed context
5. Reply to user: "Context compacted. Summary:\n{summary}"

### /doctor

Run health checks (stateless, no Claude involvement).

1. **Claude CLI**: import SDK, report version, verify CLI is reachable
2. **Sessions**: count sessions, check JSON integrity, flag stale session_ids, report sessions dir disk usage

## Wiring

### claude_bridge.py

- `_run_query` returns usage data (cost, turns, duration) alongside text and tool_uses
- `send_to_claude` passes `thinking` and `effort` from session into `ClaudeAgentOptions`
- New helper `build_options(session)` consolidates option construction

### bot.py

- 5 new handlers: `cmd_think`, `cmd_effort`, `cmd_usage`, `cmd_compact`, `cmd_doctor`
- After each `send_to_claude` in `_process_prompt`, accumulate usage stats into `bot_data["usage"]`
- Register handlers in `create_application`

### message_utils.py

- `format_help` — add the 5 new commands
- `format_usage` — new function for /usage display
- `format_doctor` — new function for /doctor display

### session.py

- Add `thinking`, `thinking_budget`, `effort` fields to `Session`
- Add `ThinkingMode`, `EffortLevel` type aliases and validation sets

## Files touched

4 existing files, 0 new files.
