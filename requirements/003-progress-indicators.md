# REQ-003: Progress Indicators

## Problem

When the Claude agent is working (reading files, running commands, writing code),
the user sees only "typing..." in the Telegram chat header. There is no indication
of what the agent is doing or how far along it is. This makes long operations
feel unresponsive.

## Goal

Provide lightweight, non-intrusive visual feedback so the user knows the agent
is actively working and can see what tools it's using -- similar to the Claude Code
CLI progress bar.

## Design

### 1. Reaction on user message

When the bot starts processing a message:
- React with eyes emoji on the user's original message (instant visual feedback).

When processing completes:
- Remove the reaction (set reaction to None).

This gives a clear "working / done" signal without sending extra messages.

### 2. Tool activity in placeholder message

In streaming mode, the bot already sends a "..." placeholder and edits it
with accumulated text. Before any text arrives, show live tool activity instead.

As the agent uses different tools, update the placeholder with the current
tool activity. Once text starts streaming, replace the tool status with the
actual response.

In non-streaming mode, send a single status message that updates with tool
activity, then delete it and send the final response.

### Tool to status mapping

| Tool | Status text |
|------|------------|
| Read | Reading filename... |
| Write | Writing filename... |
| Edit | Editing filename... |
| Glob | Searching files... |
| Grep | Searching codebase... |
| Bash | Running command... |
| WebSearch | Searching web... |
| WebFetch | Fetching page... |
| Task | Launching agent... |
| TodoWrite | Updating tasks... |
| Other | ToolName... |

### 3. Typing indicator (existing)

Keep the existing ChatAction.TYPING sent every 4 seconds -- it complements
the above without any changes needed.

## Implementation notes

- set_message_reaction requires Bot API 7.2+ (python-telegram-bot v20.8+) -- we use v22.
- Only 1 reaction per message for non-premium bots -- fine, we only need one.
- Rate limit: about 1 edit/second per chat. Tool events can fire rapidly, so throttle
  status message updates to at most 1 per second.
- The _run_query loop in claude_bridge.py already yields ToolUseBlock events --
  add an on_tool_use callback alongside the existing on_text_chunk.
- Reaction failures should be silently ignored (chat might not support reactions).

## Scope

- Phase 1 (this req): reactions + tool status in placeholder message
- Future: progress percentage for multi-file operations, time elapsed display
