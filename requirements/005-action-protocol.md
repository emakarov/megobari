# REQ-005: Action Protocol

## Problem

When Claude wants to send a file (or perform other Telegram actions), it has no
way to trigger them. The user must manually use `/file <path>`. We need a
convention so Claude can embed actions in its text responses and the bot
executes them automatically.

## Design

### Fenced code block protocol

Claude embeds actions as fenced code blocks with the `megobari` language tag:

    ```megobari
    {"action": "send_file", "path": "/absolute/path/to/file.pdf"}
    ```

The bot:
1. Parses the response text for ```` ```megobari ... ``` ```` blocks
2. Extracts and validates each JSON action
3. Executes the actions (e.g., sends files)
4. Strips the action blocks from the displayed text

### Supported actions (Phase 1)

| Action      | Fields                  | Description          |
|-------------|-------------------------|----------------------|
| `send_file` | `path` (str, required), `caption` (str, optional) | Send a file to user |

### Future actions (not implemented yet)

- `send_photo` — send image with optional caption
- `send_location` — send a location pin
- `react` — set a reaction emoji
- `pin` — pin a message

### Graceful degradation

- If JSON is invalid, the block is left in the text as-is (user sees it as code)
- If action fails (e.g., file not found), bot sends an error message but
  continues displaying the rest of the response
- Unknown action types are ignored (logged as warning)

### System prompt update

The system prompt is updated to inform Claude about the protocol:

```
When you need to send a file to the user, embed an action block:
\```megobari
{"action": "send_file", "path": "/absolute/path/to/file.pdf"}
\```
The bot will send the file and strip the block from your message.
```

## Implementation

### New module: `actions.py`

- `parse_actions(text) -> tuple[str, list[dict]]` — extract action blocks,
  return cleaned text and list of parsed actions
- `execute_actions(actions, bot, chat_id) -> list[str]` — execute actions,
  return list of error messages (empty on success)

### Changes to existing modules

- `bot.py` — after receiving response text, call `parse_actions()`, execute
  actions, then display cleaned text
- `claude_bridge.py` — append action protocol instructions to system prompt
- `message_utils.py` — no changes needed

## Testing

- Parser: valid blocks, multiple blocks, invalid JSON, no blocks, mixed content
- Executor: send_file success, file not found, unknown action
- Integration: end-to-end in handle_message
