# Megobari — Project Guide

Personal Telegram bot bridging to Claude Code via the Agent SDK. Source in `src/megobari/`, installed as an editable package with `uv`.

## Quick reference

```bash
./run.sh watch                                   # dev mode (auto-restart on save)
uv run pytest                                    # run tests (95%+ coverage required)
uv run flake8 src/ tests/                        # lint
uv run isort --check src/ tests/                 # import order
uv run pydocstyle --config=pyproject.toml src/   # docstrings
```

## Essential rules

- Max line length: 99, isort black profile, Google-style docstrings
- All source files must have module docstrings (D100 enforced)
- Type hints throughout (`from __future__ import annotations`)
- Keep bot responses concise — this runs on mobile via Telegram
- Prefer editing existing files over creating new ones
- Session must be in `acceptEdits` or `bypassPermissions` mode (not `default`)

## Deep dives

For more detail on specific topics, see:

- [Architecture and patterns](claude_instructions/architecture.md) — module overview, streaming, reactions, error handling
- [API conventions](claude_instructions/api-conventions.md) — python-telegram-bot v22, claude-agent-sdk, permission modes
- [Testing and code style](claude_instructions/testing.md) — pytest patterns, linter config, test helpers
- [Project structure](claude_instructions/project-structure.md) — file tree, run modes, directory layout
