# MCP Servers Support

## Problem

The Agent SDK does **not** automatically inherit MCP servers from the Claude Code CLI config. Remote MCP servers (like `claude.ai th`) configured at the account level are available in interactive CLI sessions but are not passed to the SDK's `query()` call.

This means the bot currently cannot use any MCP tools.

## Solution

Add `mcp_servers` config support to the bot:

1. Create an `mcp_servers.json` config file in the megobari project root (or `.megobari/`)
2. Load it at startup in `claude_bridge.py`
3. Pass it to `ClaudeAgentOptions(mcp_servers=...)` on every query

This way all sessions get the same MCP servers regardless of their `cwd`.

## Example config

```json
{
  "claude.ai th": {
    "type": "http",
    "url": "https://transithouse.app/api/mcp/server"
  }
}
```

## SDK API

From the [docs](https://platform.claude.com/docs/en/agent-sdk/mcp):

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "server-name": {
            "type": "http",
            "url": "https://example.com/mcp",
        }
    },
    # Use wildcards to allow all tools from a server
    # or rely on disallowed_tools blocklist
)
```

## Considerations

- MCP tools follow the naming pattern `mcp__<server-name>__<tool-name>`
- Tool search activates automatically when MCP tools exceed 10% of context window
- The `disallowed_tools` blocklist approach (current) works well with MCP — no need to enumerate every MCP tool in an allowlist
- Skills and plugins from `~/.claude/skills/` should be inherited by the SDK automatically, but this needs verification
