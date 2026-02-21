# Project Structure

```
CLAUDE.md                  # Quick-start project guide (this references detail files)
claude_instructions/       # Detailed guides by topic
run.sh                     # Bot launcher (watch / hook / once / stop)
.claude-plugin/
  marketplace.json         # Plugin marketplace index
plugins/                   # Curated Claude Code skills and MCP configs
src/megobari/
  __init__.py
  __main__.py              # Entry point
  config.py                # Environment configuration (.env)
  bot.py                   # Telegram handlers, streaming, reactions
  claude_bridge.py         # Agent SDK integration, tool callbacks
  session.py               # Session dataclass + manager (JSON persistence)
  formatting.py            # Formatter ABC (Telegram HTML, plain text)
  message_utils.py         # Message splitting, tool summaries, status text
tests/                     # pytest tests (mirror source structure)
  conftest.py              # Shared fixtures (session_manager)
  test_bot.py
  test_claude_bridge.py
  test_message_utils.py
  test_session.py
  test_main.py
requirements/              # Requirement documents
  001-telegram-bot.md
  002-skills-and-mcp-library.md
  003-progress-indicators.md
ideas/                     # Future feature ideas
  mcp-servers-support.md
  permission-forwarding.md
```

## Running the bot

```bash
./run.sh once          # single run
./run.sh watch         # auto-restart on .py changes (dev)
./run.sh hook          # auto-restart on git commit
./run.sh install-hook  # set up post-commit hook for hook mode
./run.sh stop          # stop running bot
```

Watch mode uses `watchfiles` to monitor `src/` for Python changes. Hook mode uses a git post-commit hook to SIGTERM the bot, which restarts via a loop. Both write PID to `.megobari/bot.pid`.
