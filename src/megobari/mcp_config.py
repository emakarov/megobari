"""MCP server config reader — loads from ~/.claude/mcp.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Standard locations for MCP configs (checked in order)
_MCP_CONFIG_PATHS = [
    Path.home() / ".claude" / "mcp.json",
]


def load_mcp_registry(
    extra_paths: list[Path] | None = None,
) -> dict[str, dict]:
    """Load all available MCP server configs from known locations.

    Returns a dict mapping server name to its config dict
    (command, args, env, type, url, etc.).
    """
    registry: dict[str, dict] = {}
    paths = list(_MCP_CONFIG_PATHS)
    if extra_paths:
        paths.extend(extra_paths)

    for path in paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
            servers = data.get("mcpServers", {})
            for name, config in servers.items():
                if name not in registry:
                    registry[name] = config
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read MCP config from %s: %s", path, exc)

    return registry


def filter_mcp_servers(
    registry: dict[str, dict],
    names: list[str],
) -> dict[str, dict]:
    """Filter MCP registry to only include the named servers.

    Returns a dict ready for ClaudeAgentOptions.mcp_servers.
    Unknown names are silently skipped.
    """
    return {
        name: registry[name]
        for name in names
        if name in registry
    }


def list_available_servers(
    extra_paths: list[Path] | None = None,
) -> list[str]:
    """Return sorted list of all available MCP server names."""
    return sorted(load_mcp_registry(extra_paths).keys())


def discover_skills(
    extra_dirs: list[Path] | None = None,
) -> list[str]:
    """Discover available Claude Code skills from known locations.

    Scans ~/.claude/skills/ and optional extra directories.
    Returns sorted list of skill names.
    """
    skills: set[str] = set()
    dirs = [Path.home() / ".claude" / "skills"]
    if extra_dirs:
        dirs.extend(extra_dirs)

    for d in dirs:
        if not d.is_dir():
            continue
        for child in d.iterdir():
            # Skills are directories (or symlinks to dirs) containing SKILL.md
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.exists() or (child / "skill.md").exists():
                    skills.add(child.name)
                else:
                    # Some skills are just dirs without SKILL.md
                    skills.add(child.name)

    return sorted(skills)
