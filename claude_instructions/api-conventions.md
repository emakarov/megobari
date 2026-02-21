# API Conventions

## python-telegram-bot v22+

- Use `filters.User(user_id=ID)` — not `user_ids` (renamed in v22)
- `reply_text` is async, returns the sent `Message` object
- `Message.edit_text()` for in-place edits (rate limit ~1/sec per chat)
- `bot.set_message_reaction()` for emoji reactions (Bot API 7.2+, 1 reaction per message for non-premium)
- `ChatAction.TYPING` expires after 5 seconds — must be re-sent periodically

## claude-agent-sdk

- `query()` is an async generator yielding message objects:
  - `SystemMessage` (subtype="init" has session_id)
  - `AssistantMessage` (contains `TextBlock` and `ToolUseBlock` in `.content`)
  - `ResultMessage` (final, has session_id, cost, usage)
- `ClaudeAgentOptions` configures: `permission_mode`, `cwd`, `disallowed_tools`, `system_prompt`, `resume`
- Agent SDK does NOT inherit MCP servers from CLI config — needs explicit `mcp_servers` in `ClaudeAgentOptions`
- Interactive tools are blocked via `DISALLOWED_TOOLS` list (blocklist, not allowlist)
- The SDK message parser is monkey-patched (`_patch_message_parser`) to handle unknown message types gracefully instead of crashing

## Permission modes

- `default` — requires interactive approval, NOT usable via Telegram (agent hangs)
- `acceptEdits` — auto-approves file operations, prompts for bash
- `bypassPermissions` — approves everything automatically
