# REQ-001: Telegram Bot Interface to Claude Code

## Summary

Create a Telegram bot that runs on my local machine and allows me to communicate with Claude Code from Telegram.

## Motivation

I want to be able to interact with Claude Code from anywhere via Telegram — send messages, get responses, and manage tasks on my computer without needing to be at the terminal.

## Requirements

### Core

- Telegram bot that runs as a service on my local machine
- Receives messages from my Telegram account
- Forwards them to Claude Code CLI for processing
- Sends Claude Code's responses back to me via Telegram
- Only responds to my Telegram user (authenticated, single-user)

### Functional

- Send text messages to the bot and get Claude Code responses
- Support for long responses (Telegram has a 4096 char limit per message — split if needed)
- Indication that the bot is processing (typing indicator)

#### Session Management

- Named sessions — each session has a user-given name
- Ability to create, switch between, and list sessions
- Each session maintains its own conversation context (via Agent SDK session resumption)
- Streaming mode is togglable per session (on/off)
- Permission mode is selectable per session (`default`, `acceptEdits`, `bypassPermissions`)
- Working directory is the directory where the bot is launched

#### Bot Commands

- `/new <name>` — create a new session with the given name
- `/sessions` — list all active sessions
- `/switch <name>` — switch to an existing session
- `/delete <name>` — delete a session
- `/stream on|off` — toggle streaming for the current session
- `/permissions <mode>` — set permission mode for the current session
- `/current` — show current session info (name, streaming, permissions, cwd)

### Non-Functional

- Runs locally on my macOS machine
- Starts automatically (or easily startable)
- Secure — only I can interact with the bot
- Resilient — handles errors gracefully without crashing

## Technology Decisions

- **Telegram framework:** `python-telegram-bot` (Python)
- **Claude integration:** Claude Agent SDK (`claude-agent-sdk` Python package)
  - Provides built-in tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
  - Async streaming via `query()` — yields messages as they arrive
  - Permission modes: `default`, `acceptEdits`, `bypassPermissions`
  - Session resumption support (can continue conversations across requests)
  - Custom system prompts and tool configuration
  - Working directory (`cwd`) control for file operations on local machine

## Architecture

```
Telegram App (phone/desktop)
    ↕ (Telegram API)
python-telegram-bot (runs locally on Mac)
    ↕ (claude-agent-sdk)
Claude Agent SDK → Claude API
    ↕ (built-in tools)
Local filesystem, shell, web
```

## Phases

### Phase 1 (current)
- Core bot with session management
- Text-only communication
- Streaming toggle per session
- Permission mode per session
- Bot commands for session control

### Phase 2 (future)
- File sending/receiving (screenshots, code files)
- Additional features TBD
