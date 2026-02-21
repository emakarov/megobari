# REQ-002: Curated Skills & MCP Library

## Summary

Megobari ships with a curated library of Claude Code skills and MCP server configurations. Users can browse and install them into their Claude Code setup directly from the bot or from the repository.

## Motivation

Claude Code's ecosystem of skills and MCP servers is growing, but discovering quality ones is hard. Megobari should serve not just as a Telegram bridge, but as an opinionated toolkit — a handpicked collection of useful skills and MCP integrations that the author has tested and recommends.

This also solves the problem discovered in REQ-001: the Agent SDK does not inherit MCP servers from the CLI config, so the bot needs its own MCP registry.

## Requirements

### Library Structure

- A well-organized directory in the repository containing:
  - **Skills** — Claude Code skill definitions (`.md` files with frontmatter)
  - **MCP configs** — Tested MCP server configurations ready to install
- Each entry includes:
  - The skill/MCP definition itself
  - A short description of what it does and why it's useful
  - Category/tags for discoverability
  - Source attribution (author, upstream repo if applicable)

### Installation

- User can install a skill or MCP server from the library into their Claude Code setup
- Installation should work via:
  - Bot command (e.g., `/install <skill-name>`)
  - Manual copy from the repository
- Uninstall/removal support

### Bot Integration

- `/library` or `/skills` command to browse available skills and MCPs
- `/install <name>` to install a skill or MCP to the user's Claude Code
- `/uninstall <name>` to remove
- Show which ones are currently installed

### Curation

- Author maintains the library — not a community free-for-all
- Each entry is tested and vetted before inclusion
- Version tracking for upstream changes

## Directory Structure

```
library/
  skills/
    <skill-name>/
      skill.md           # The skill definition
      README.md           # Description, usage, why it's useful
  mcp/
    <server-name>/
      config.json         # MCP server config (ready to pass to SDK or install via CLI)
      README.md           # Description, what tools it provides, auth setup
  catalog.json            # Machine-readable index of all entries
```

## Considerations

- Skills are just `.md` files — installing means copying to `~/.claude/skills/`
- MCP servers need more setup (env vars, auth tokens, npm packages)
- The `catalog.json` enables the bot to list/search without parsing every file
- Should work both as a standalone browsable repo and via the bot
- MCP configs should support both local (stdio) and remote (HTTP/SSE) servers
- Consider whether per-session MCP selection makes sense (different sessions, different tools)

## Phases

### Phase 1
- Create `library/` directory structure
- Add initial skills and MCP configs from author's collection
- Bot commands: `/library`, `/install`, `/uninstall`

### Phase 2
- Categories and search
- Per-session MCP activation
- Auto-update check for upstream skill changes
- Integration with `find-skills` skill for discovery

## Related

- [REQ-001](001-telegram-bot.md) — Core bot functionality
- [ideas/mcp-servers-support.md](../ideas/mcp-servers-support.md) — MCP SDK integration details
