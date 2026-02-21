# Architecture

```
Telegram  <-->  bot.py  <-->  claude_bridge.py  <-->  Claude Code CLI (Agent SDK)
                  |
        formatting.py + message_utils.py
                  |
             session.py  <-->  .megobari/sessions/sessions.json
```

## Modules

- **bot.py** — Telegram handlers, streaming accumulator, reactions, command routing
- **claude_bridge.py** — Agent SDK integration, `send_to_claude()` async generator, tool callbacks
- **session.py** — Session dataclass + SessionManager with JSON persistence
- **message_utils.py** — Message splitting, tool summaries, tool status text, help formatting
- **formatting.py** — `Formatter` ABC with `TelegramFormatter` (HTML) and `PlainTextFormatter`
- **config.py** — Loads `.env` via python-dotenv

## Key patterns

- `StreamingAccumulator` in bot.py handles real-time message editing with edit throttling (200 char threshold)
- Tool activity is shown via `on_tool_use` callbacks — placeholder message shows status before text arrives
- Reactions (eyes emoji) are set on user message during processing, removed in `finally` block
- Session persistence: JSON file at `.megobari/sessions/sessions.json`, saved on every mutation
- Error handling: resume failures auto-retry as fresh sessions, all reaction/edit failures silently caught
- The `Formatter` abstraction decouples presentation from logic — swap `TelegramFormatter` for another implementation to support Discord, Slack, CLI, etc.
