# Megobari (მეგობარი)

**Megobari** means "friend" in Georgian. The name was chosen by the author while living in Georgia and learning the language — a nod to the idea of having a helpful coding companion always at hand, right from your phone.

A personal Telegram bot that bridges to [Claude Code](https://docs.anthropic.com/en/docs/claude-code), giving you a mobile interface to Claude's coding capabilities.

## Features

- **Session management** — multiple named conversations with independent context
- **Streaming responses** — real-time message updates as Claude thinks
- **Per-session working directory** — `/cd` to switch, `/dirs` to add extra folders
- **Permission modes** — `default`, `acceptEdits`, `bypassPermissions` per session
- **Rich Telegram formatting** — HTML-formatted tool summaries, session info, help
- **Client-agnostic formatting** — `Formatter` abstraction for future non-Telegram frontends
- **Library API** — embed Megobari in your own Python project
- **Voice messages** — send voice messages, transcribed locally via faster-whisper
- **Action protocol** — Claude can send files/photos and restart the bot via embedded action blocks
- **Persistent memory** — Claude can save, recall, and delete long-term facts/preferences
- **Conversation summaries** — automatic periodic summarization + manual `/compact` with short extract for efficient context injection
- **Usage tracking** — per-query cost, tokens, duration tracked in SQLite with `/usage` and `/context` commands
- **Model & reasoning controls** — `/model`, `/think`, `/effort` to tune Claude's behavior per session
- **Plugin marketplace** — curated collection of Claude Code skills and MCP integrations

## Installation

```bash
pip install megobari
```

With voice message support:

```bash
pip install megobari[voice]
```

Or from source:

```bash
git clone https://github.com/emakarov/megobari
cd megobari
uv sync
# For voice support:
uv pip install faster-whisper
```

### Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude auth login`)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Quick start

### Option 1: Environment variables

```bash
export BOT_TOKEN="your-bot-token"
export ALLOWED_USER="your-telegram-id"   # or @username
megobari
```

Or use a `.env` file:

```bash
cp .env.example .env   # edit with your values
megobari
```

### Option 2: CLI arguments

```bash
megobari --bot-token="your-bot-token" --allowed-user="12345"
megobari --bot-token="your-bot-token" --allowed-user="@username" --cwd /path/to/project
```

### Option 3: Library API

```python
from megobari import MegobariBot

bot = MegobariBot(
    bot_token="your-bot-token",
    allowed_user="12345",           # user ID or @username
    working_dir="/path/to/project", # optional
)
bot.run()
```

### Configuration priority

Arguments override environment variables, which override `.env` file values.

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

**Session management**

| Command | Description |
|---|---|
| `/new <name>` | Create a new session |
| `/sessions` | List all sessions |
| `/switch <name>` | Switch to a session |
| `/rename <old> <new>` | Rename a session |
| `/delete <name>` | Delete a session |
| `/current` | Show active session info |

**Configuration**

| Command | Description |
|---|---|
| `/cd <path>` | Change working directory |
| `/dirs [add\|rm] <path>` | Manage extra directories |
| `/stream on\|off` | Toggle streaming responses |
| `/permissions <mode>` | Set permission mode (`default`, `acceptEdits`, `bypassPermissions`) |
| `/model [name]` | Switch model (`sonnet`, `opus`, `haiku`, or full name; `off` to reset) |
| `/think [mode] [budget]` | Set thinking mode (`on`, `off`, `adaptive`) and optional token budget |
| `/effort [level]` | Set reasoning effort (`low`, `medium`, `high`) |

**Context & usage**

| Command | Description |
|---|---|
| `/compact` | Summarize conversation and reset context window |
| `/context` | Show token usage for current run and all-time |
| `/usage` | Show cost and usage statistics |
| `/history [all\|search\|stats]` | Browse conversation history |

**Utilities**

| Command | Description |
|---|---|
| `/file <path>` | Send a file to Telegram |
| `/restart` | Restart the bot process |
| `/doctor` | Run diagnostics (check deps, config, connectivity) |
| `/help` | Show all commands |

### Permission modes

The `/permissions` command controls how Claude handles tool approvals:

| Mode | Behavior |
|---|---|
| `default` | Requires interactive approval for file writes and commands. **Not usable via Telegram** — prompts have nowhere to go and the agent will hang. |
| `acceptEdits` | Auto-approves file reads, writes, and edits. Still prompts for bash commands. **Recommended for normal use.** |
| `bypassPermissions` | Approves everything automatically. Use when you need the agent to run commands freely. |

Set it per session:

```
/permissions acceptEdits
```

### Sessions

Each session maintains its own:
- Claude conversation context (resumable)
- Working directory (`cwd`)
- Extra accessible directories
- Streaming toggle
- Permission mode

Session data is persisted to `.megobari/sessions/sessions.json`.

## Voice Messages

Send a voice message in Telegram and the bot will transcribe it locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper), then forward the text to Claude.

Requires the `voice` extra:

```bash
pip install megobari[voice]
```

The default model is `small` (~150MB, downloaded on first use). Configure via `Config(whisper_model="tiny")` or set in code. Available models: `tiny`, `base`, `small`, `medium`, `large-v3`.

Transcription runs on CPU (int8 quantization) — no GPU needed.

## Action Protocol

Claude can trigger bot actions by embedding fenced code blocks in responses:

````
```megobari
{"action": "send_file", "path": "/absolute/path/to/file.pdf", "caption": "optional"}
```
````

The bot parses these blocks, executes the actions, and strips them from the displayed text.

| Action | Fields | Description |
|--------|--------|-------------|
| `send_file` | `path` (required), `caption` (optional) | Send a file to the user |
| `send_photo` | `path` (required), `caption` (optional) | Send an image inline |
| `restart` | — | Restart the bot process |
| `memory_set` | `category`, `key`, `value` | Save a persistent memory |
| `memory_delete` | `category`, `key` | Delete a memory |
| `memory_list` | `category` (optional) | List saved memories |

## Persistence & Memory

Megobari uses SQLite (at `~/.megobari/megobari.db`) to persist:

- **Conversation summaries** — auto-generated every 20 messages + manual via `/compact`. Each summary has a short extract (one-line) used for token-efficient context injection, and a full detailed version stored for reference.
- **Messages** — logged for summarization pipeline
- **Memories** — long-term facts and preferences that Claude can save/recall across sessions via action blocks
- **Usage records** — per-query cost, token counts, duration

The recall system injects recent summaries (short extracts) and memories into the system prompt, giving Claude persistent context across conversation resets.

## Plugin Marketplace

Megobari doubles as a Claude Code plugin marketplace with a curated collection of skills and MCP integrations.

### Install the marketplace

```bash
/plugin marketplace add https://github.com/<user>/megobari
```

### Available plugins

No plugins yet — the collection is being curated.

### Install a plugin

```bash
/plugin install <plugin-name>
```

### Structure

```
.claude-plugin/
  marketplace.json         # Marketplace index
plugins/                   # Curated skills and MCP configs
```

See [REQ-002](requirements/002-skills-and-mcp-library.md) for the full design.

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
run.sh                     # Bot launcher (watch / hook / once / stop)
.claude-plugin/
  marketplace.json         # Plugin marketplace index
plugins/                   # Curated skills and MCP configs
src/megobari/
  __main__.py              # Entry point
  config.py                # Environment configuration
  bot.py                   # Telegram handlers & commands
  claude_bridge.py         # Agent SDK integration
  session.py               # Session dataclass + manager
  formatting.py            # Formatter ABC (Telegram HTML, plain text)
  message_utils.py         # Message splitting, formatting helpers
  markdown_html.py         # Markdown to Telegram HTML converter
  actions.py               # Action protocol (send_file, send_photo, restart, memory)
  recall.py                # Context recall (summaries + memories → system prompt)
  summarizer.py            # Auto-summarization pipeline
  voice.py                 # Voice transcription (optional dep)
  db/
    models.py              # SQLAlchemy models (User, Message, Summary, Memory, Usage)
    repository.py          # Async CRUD operations
    engine.py              # DB engine factory
tests/
```

## Architecture

```
Telegram  <-->  bot.py  <-->  claude_bridge.py  <-->  Claude Code CLI
                  |                |                        |
             formatting.py    recall.py                Agent SDK
                  |                |
           message_utils.py   summarizer.py
                  |                |
             session.py        db/ (SQLite)
                  |
          sessions.json
```

The `Formatter` abstraction decouples presentation from logic. Swap `TelegramFormatter` for another implementation to support Discord, Slack, CLI, etc.

The recall system builds context from recent summaries (using short extracts for efficiency) and persistent memories, injecting them into the system prompt each turn.
