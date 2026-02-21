# Megobari

Personal Telegram bot that bridges to [Claude Code](https://docs.anthropic.com/en/docs/claude-code), giving you a mobile interface to Claude's coding capabilities.

## Features

- **Session management** — multiple named conversations with independent context
- **Streaming responses** — real-time message updates as Claude thinks
- **Per-session working directory** — `/cd` to switch, `/dirs` to add extra folders
- **Permission modes** — `default`, `acceptEdits`, `bypassPermissions` per session
- **Rich Telegram formatting** — HTML-formatted tool summaries, session info, help
- **Client-agnostic formatting** — `Formatter` abstraction for future non-Telegram frontends

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude auth login`)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Setup

```bash
# Clone and install
git clone <repo-url>
cd megobari
uv sync

# Configure
cp .env.example .env
# Edit .env with your bot token and Telegram user ID/username
```

### Environment variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `ALLOWED_USER` | Your Telegram numeric user ID or `@username` |

To find your Telegram user ID, start the bot without `ALLOWED_USER` set — it will reply with your ID.

## Usage

```bash
# Run once
./run.sh once

# Auto-restart on .py file changes (dev mode)
./run.sh watch

# Auto-restart on git commit (set up hook first)
./run.sh install-hook
./run.sh hook

# Stop the running bot
./run.sh stop
```

### Run modes

| Mode | Command | Restarts on | Best for |
|---|---|---|---|
| **watch** | `./run.sh watch` | Any `.py` file change | Active development |
| **hook** | `./run.sh hook` | `git commit` | Stable dev / staging |
| **once** | `./run.sh once` | — | Production / manual runs |

**Watch mode** uses [watchfiles](https://watchfiles.helpmanual.io/) to monitor `src/` for Python file changes and restarts the bot instantly on save.

**Hook mode** runs the bot in a restart loop. A git `post-commit` hook (installed via `./run.sh install-hook`) sends SIGTERM to the running bot after each commit, and the loop automatically restarts it with the new code.

Both modes write a PID file to `.megobari/bot.pid` for lifecycle management. Use `./run.sh stop` to stop the bot from either mode.

### Commands

| Command | Description |
|---|---|
| `/new <name>` | Create a new session |
| `/sessions` | List all sessions |
| `/switch <name>` | Switch to a session |
| `/rename <old> <new>` | Rename a session |
| `/delete <name>` | Delete a session |
| `/current` | Show active session info |
| `/cd <path>` | Change working directory |
| `/dirs [add\|rm] <path>` | Manage extra directories |
| `/stream on\|off` | Toggle streaming responses |
| `/permissions <mode>` | Set permission mode |
| `/help` | Show all commands |

### Sessions

Each session maintains its own:
- Claude conversation context (resumable)
- Working directory (`cwd`)
- Extra accessible directories
- Streaming toggle
- Permission mode

Session data is persisted to `.megobari/sessions/sessions.json`.

## Development

```bash
# Install with dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run linting
uv run flake8 src/ tests/
uv run isort --check src/ tests/
uv run pydocstyle --config=pyproject.toml src/

# Install pre-commit hooks
uv run pre-commit install
```

### Project structure

```
run.sh                 # Bot launcher (watch / hook / once / stop)
src/megobari/
  __main__.py          # Entry point
  config.py            # Environment configuration
  bot.py               # Telegram handlers
  claude_bridge.py     # Agent SDK integration
  session.py           # Session dataclass + manager
  formatting.py        # Formatter ABC (Telegram HTML, plain text)
  message_utils.py     # Message splitting, formatting helpers
tests/
  test_bot.py
  test_claude_bridge.py
  test_formatting.py
  test_main.py
  test_message_utils.py
  test_session.py
```

## Architecture

```
Telegram  <-->  bot.py  <-->  claude_bridge.py  <-->  Claude Code CLI
                  |                                        |
             formatting.py                           Agent SDK
                  |
           message_utils.py
                  |
             session.py  <-->  .megobari/sessions/sessions.json
```

The `Formatter` abstraction decouples presentation from logic. Swap `TelegramFormatter` for another implementation to support Discord, Slack, CLI, etc.

## Name

**Megobari** (მეგობარი) is the Georgian word for "friend". The name reflects the idea of having a helpful companion always at hand — a coding friend you can reach from your phone through Telegram.
