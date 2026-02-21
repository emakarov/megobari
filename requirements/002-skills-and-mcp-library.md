# REQ-002: Curated Skills & MCP Library

## Summary

Megobari ships with a curated library of Claude Code skills, MCP server configurations, and plugins. The library is distributed as a **Claude Code plugin marketplace**, allowing users to install items via the native `/plugin` system, the bot's Telegram commands, or manually.

## Motivation

Claude Code's ecosystem of skills, MCP servers, and plugins is growing, but discovering quality ones is hard. Megobari should serve not just as a Telegram bridge, but as an opinionated toolkit — a handpicked collection of useful extensions that the author has tested and recommends.

This also solves the problem discovered in REQ-001: the Agent SDK does not inherit MCP servers from the CLI config, so the bot needs its own MCP registry.

## Requirements

### Plugin Marketplace

Megobari acts as a Claude Code plugin marketplace. Users can add it with:

```bash
/plugin marketplace add https://github.com/<user>/megobari
/plugin install <plugin-name>
```

This follows the same pattern as the official marketplace and third-party ones like `claude-scientific-writer`.

### Marketplace Format

The marketplace is defined by a `.claude-plugin/marketplace.json` at the repo root:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "megobari",
  "description": "Curated collection of Claude Code skills, MCP integrations, and tools",
  "owner": {
    "name": "Author Name",
    "email": "author@example.com"
  },
  "plugins": [
    {
      "name": "plugin-name",
      "description": "What it does",
      "source": "./plugins/plugin-name",
      "category": "development"
    }
  ]
}
```

Each plugin lives in its own directory under `plugins/` and can contain:
- **Skills** — `.md` files with frontmatter (`SKILL.md`)
- **MCP servers** — server configs (stdio, HTTP/SSE)
- **LSP servers** — language server configs
- **Hooks** — pre/post action hooks
- **Agents** — custom agent definitions

### Library Structure

```
.claude-plugin/
  marketplace.json          # Marketplace index (required by Claude Code)
plugins/
  <plugin-name>/
    .claude-plugin/
      plugin.json           # Plugin metadata
    skills/
      <skill-name>/
        SKILL.md            # Skill definition
    README.md               # Description, usage, why it's useful
```

### Types of Items

1. **Original skills** — Skills authored by the megobari maintainer
2. **Curated third-party** — Handpicked skills/MCPs from the ecosystem, forked or referenced
3. **MCP bundles** — Pre-configured MCP server setups with auth instructions

### Installation Methods

| Method | How | Best for |
|---|---|---|
| Plugin marketplace | `/plugin marketplace add <url>` + `/plugin install <name>` | Claude Code users |
| Bot command | `/install <name>` (via Telegram) | Bot users |
| Manual | Copy files to `~/.claude/skills/` | Quick one-off |

### Bot Integration

- `/library` — browse available plugins, skills, and MCPs
- `/install <name>` — install a plugin to the user's Claude Code
- `/uninstall <name>` — remove a plugin
- Show which ones are currently installed

### Curation

- Author maintains the library — not a community free-for-all
- Each entry is tested and vetted before inclusion
- Version tracking for upstream changes
- Source attribution (author, upstream repo if applicable)

## Reference: Existing Marketplace Format

Based on analysis of installed marketplaces:

### marketplace.json (repo root)

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "marketplace-name",
  "owner": { "name": "...", "email": "..." },
  "plugins": [
    {
      "name": "plugin-name",
      "description": "...",
      "source": "./plugins/plugin-name",
      "category": "development|productivity|security|...",
      "skills": ["./skills/skill-one", "./skills/skill-two"],
      "lspServers": { ... },
      "strict": false
    },
    {
      "name": "external-plugin",
      "description": "...",
      "source": { "source": "url", "url": "https://github.com/org/repo.git" },
      "category": "...",
      "homepage": "https://..."
    }
  ]
}
```

### plugin.json (per plugin)

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "...",
  "author": { "name": "...", "email": "..." }
}
```

### Key observations

- Plugins can be local (`"source": "./plugins/..."`) or external (`"source": {"source": "url", "url": "..."}`)
- External plugins reference upstream repos — good for curating third-party tools
- Categories: `development`, `productivity`, `security`, `monitoring`, `database`, `deployment`, `design`, `learning`, `testing`
- Skills live inside plugins under `skills/<skill-name>/SKILL.md`
- MCP servers are configured in plugin.json or marketplace.json
- LSP servers are defined inline in marketplace.json

## Phases

### Phase 1
- Set up `.claude-plugin/marketplace.json` structure
- Create initial plugins from author's collection
- Publish as installable marketplace

### Phase 2
- Bot commands: `/library`, `/install`, `/uninstall`
- Categories and search
- Per-session MCP activation
- Auto-update check for upstream changes
- External plugin references for curated third-party tools

## Related

- [REQ-001](001-telegram-bot.md) — Core bot functionality
- [ideas/mcp-servers-support.md](../ideas/mcp-servers-support.md) — MCP SDK integration details
