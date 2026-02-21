# Megobari — Project Guide

## What is this

A personal Telegram bot that bridges to Claude Code via the Agent SDK. Source lives in `src/megobari/`, installed as an editable package with `uv`.

## Architecture

```
Telegram  <-->  bot.py  <-->  claude_bridge.py  <-->  Claude Code CLI (Agent SDK)
                  |
        formatting.py + message_utils.py
                  |
             session.py  <-->  .megobari/sessions/sessions.json
```

- **bot.py** — Telegram handlers, streaming accumulator, reactions, command routing
- **claude_bridge.py** — Agent SDK integration, `send_to_claude()` async generator, tool callbacks
- **session.py** — Session dataclass + SessionManager with JSON persistence
- **message_utils.py** — Message splitting, tool summaries, tool status text, help formatting
- **formatting.py** — `Formatter` ABC with `TelegramFormatter` (HTML) and `PlainTextFormatter`
- **config.py** — Loads `.env` via python-dotenv

## Key conventions

- **python-telegram-bot v22+**: use `filters.User(user_id=ID)` (not `user_ids`)
- **claude-agent-sdk**: `query()` is an async generator yielding `SystemMessage`, `AssistantMessage`, `ResultMessage`
- Agent SDK does NOT inherit MCP servers from CLI config — needs explicit `mcp_servers` in `ClaudeAgentOptions`
- Interactive tools are blocked via `DISALLOWED_TOOLS` list (not an allowlist)
- All file writes go through the Telegram bot non-interactively — session must be in `acceptEdits` or `bypassPermissions` mode

## Running

```bash
./run.sh once          # single run
./run.sh watch         # auto-restart on .py changes (dev)
./run.sh hook          # auto-restart on git commit
./run.sh stop          # stop running bot
```

## Testing and linting

```bash
uv run pytest                                    # 168 tests, 95%+ coverage required
uv run flake8 src/ tests/                        # max-line-length=99
uv run isort --check src/ tests/                 # profile=black
uv run pydocstyle --config=pyproject.toml src/   # google convention
```

- All source files must have module docstrings (D100 is enforced)
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Coverage threshold is 95% (`--cov-fail-under=95`)

## Code style

- Max line length: 99
- Imports sorted with isort (black profile)
- Google-style docstrings (pydocstyle)
- Type hints used throughout (`from __future__ import annotations`)
- Prefer editing existing files over creating new ones
- Keep responses and messages concise — this runs on mobile

## Project structure

```
src/megobari/          # Main package (7 modules)
tests/                 # pytest tests (mirror source structure)
requirements/          # Requirement docs (001-telegram-bot, 002-skills, 003-progress)
ideas/                 # Future feature ideas
plugins/               # Claude Code plugin marketplace
.claude-plugin/        # Marketplace index (marketplace.json)
run.sh                 # Bot launcher
```

## Important patterns

- `StreamingAccumulator` in bot.py handles real-time message editing with edit throttling (200 char threshold)
- Tool activity is shown via `on_tool_use` callbacks — placeholder message shows status before text arrives
- Reactions (eyes emoji) are set on user message during processing, removed in `finally` block
- Session persistence: JSON file at `.megobari/sessions/sessions.json`, saved on every mutation
- Error handling: resume failures auto-retry as fresh sessions, all reaction/edit failures silently caught
