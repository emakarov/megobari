"""Tests for MCP config reader."""

import json
from pathlib import Path

import pytest

from megobari.mcp_config import (
    discover_skills,
    filter_mcp_servers,
    list_available_servers,
    load_mcp_registry,
)


@pytest.fixture
def mcp_json(tmp_path: Path) -> Path:
    """Create a test mcp.json file."""
    config = {
        "mcpServers": {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "ghp_test"},
            },
            "sgerp": {
                "command": "uv",
                "args": ["--directory", "/dev/sgerp-mcp", "run", "sgerp-mcp"],
            },
            "figma": {
                "command": "npx",
                "args": ["-y", "@anthropic-ai/figma-mcp-server"],
                "env": {"FIGMA_ACCESS_TOKEN": "test"},
            },
        }
    }
    f = tmp_path / "mcp.json"
    f.write_text(json.dumps(config))
    return f


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a test skills directory."""
    d = tmp_path / "skills"
    d.mkdir()
    # Skill with SKILL.md
    (d / "jira").mkdir()
    (d / "jira" / "SKILL.md").write_text("# Jira skill")
    # Skill with lowercase skill.md
    (d / "clickhouse").mkdir()
    (d / "clickhouse" / "skill.md").write_text("# Clickhouse")
    # Skill directory without SKILL.md (still discovered)
    (d / "find-skills").mkdir()
    return d


def test_load_mcp_registry(mcp_json: Path):
    registry = load_mcp_registry(extra_paths=[mcp_json])
    assert "github" in registry
    assert "sgerp" in registry
    assert "figma" in registry
    assert registry["github"]["command"] == "npx"
    assert registry["sgerp"]["command"] == "uv"


def test_load_mcp_registry_no_file():
    registry = load_mcp_registry(
        extra_paths=[Path("/nonexistent/mcp.json")]
    )
    # Should return empty (or whatever is in ~/.claude/mcp.json)
    # We only test that it doesn't crash
    assert isinstance(registry, dict)


def test_load_mcp_registry_bad_json(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{{")
    registry = load_mcp_registry(extra_paths=[bad])
    assert isinstance(registry, dict)


def test_filter_mcp_servers(mcp_json: Path):
    registry = load_mcp_registry(extra_paths=[mcp_json])
    filtered = filter_mcp_servers(registry, ["github", "sgerp"])
    assert "github" in filtered
    assert "sgerp" in filtered
    assert "figma" not in filtered


def test_filter_mcp_servers_unknown_name(mcp_json: Path):
    registry = load_mcp_registry(extra_paths=[mcp_json])
    filtered = filter_mcp_servers(registry, ["nonexistent"])
    assert filtered == {}


def test_filter_mcp_servers_empty():
    filtered = filter_mcp_servers({}, ["github"])
    assert filtered == {}


def test_list_available_servers(mcp_json: Path):
    servers = list_available_servers(extra_paths=[mcp_json])
    assert "figma" in servers
    assert "github" in servers
    assert "sgerp" in servers
    assert servers == sorted(servers)


def test_discover_skills(skills_dir: Path):
    found = discover_skills(extra_dirs=[skills_dir])
    assert "jira" in found
    assert "clickhouse" in found
    assert "find-skills" in found
    assert found == sorted(found)


def test_discover_skills_empty(tmp_path: Path):
    empty = tmp_path / "empty_skills"
    empty.mkdir()
    found = discover_skills(extra_dirs=[empty])
    # Only from this dir (no real skills in test)
    assert isinstance(found, list)


def test_discover_skills_nonexistent():
    found = discover_skills(
        extra_dirs=[Path("/nonexistent/skills")]
    )
    assert isinstance(found, list)
