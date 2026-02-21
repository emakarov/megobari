"""Tests for message formatting utilities."""

from __future__ import annotations

from megobari.formatting import PlainTextFormatter, TelegramFormatter
from megobari.message_utils import (
    format_help,
    format_session_info,
    format_session_list,
    format_tool_summary,
    split_message,
    tool_status_text,
)
from megobari.session import Session


class TestSplitMessage:
    def test_empty(self):
        assert split_message("") == ["(empty response)"]

    def test_short(self):
        assert split_message("hello") == ["hello"]

    def test_exact_limit(self):
        text = "a" * 4096
        assert split_message(text) == [text]

    def test_splits_at_paragraph(self):
        text = "a" * 2000 + "\n\n" + "b" * 2000
        chunks = split_message(text, max_length=4096)
        assert len(chunks) >= 1
        assert "".join(chunks).replace("\n", "") == "a" * 2000 + "b" * 2000

    def test_splits_long_text(self):
        text = " ".join(["word"] * 2000)
        chunks = split_message(text, max_length=100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_hard_cut_no_separators(self):
        # Single long word with no spaces or newlines — forces hard cut
        text = "x" * 200
        chunks = split_message(text, max_length=50)
        assert len(chunks) > 1
        assert chunks[0] == "x" * 50

    def test_splits_at_newline(self):
        # Text with single newlines but no double newlines
        text = "a" * 40 + "\n" + "b" * 40
        chunks = split_message(text, max_length=50)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 40


class TestFormatSessionInfo:
    def test_plain(self):
        s = Session(name="test", cwd="/tmp")
        text = format_session_info(s)
        assert "test" in text
        assert "/tmp" in text
        assert "Streaming:" in text

    def test_html(self):
        s = Session(name="test", cwd="/tmp")
        fmt = TelegramFormatter()
        text = format_session_info(s, fmt)
        assert "<b>" in text

    def test_shows_extra_dirs(self):
        s = Session(name="test", cwd="/tmp", dirs=["/a", "/b"])
        text = format_session_info(s)
        assert "2" in text
        assert "/dirs" in text


class TestFormatSessionList:
    def test_empty(self):
        text = format_session_list([], None)
        assert "No sessions" in text

    def test_marks_active(self):
        sessions = [Session(name="a"), Session(name="b")]
        fmt = PlainTextFormatter()
        text = format_session_list(sessions, "a", fmt)
        lines = text.split("\n")
        assert any("▸" in line and "a" in line for line in lines)

    def test_shows_stream_flag(self):
        sessions = [Session(name="s", streaming=True)]
        text = format_session_list(sessions, "s")
        assert "stream" in text


class TestFormatToolSummary:
    def test_bash_grouped(self):
        tools = [
            ("Bash", {"command": "git status"}),
            ("Bash", {"command": "git diff"}),
        ]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "⚡" in text
        assert "git status" in text
        assert "git diff" in text
        # Should be single line for Bash
        assert text.count("⚡") == 1

    def test_edit_deduplication(self):
        tools = [
            ("Edit", {"file_path": "/a/b/foo.py"}),
            ("Edit", {"file_path": "/a/b/foo.py"}),
            ("Edit", {"file_path": "/a/b/bar.py"}),
        ]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "foo.py" in text
        assert "×2" in text
        assert "bar.py" in text

    def test_unknown_tool(self):
        tools = [("TodoWrite", {}), ("TodoWrite", {})]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "TodoWrite" in text
        assert "×2" in text

    def test_unknown_tool_single(self):
        tools = [("TodoWrite", {})]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "TodoWrite" in text
        assert "×" not in text

    def test_html_formatting(self):
        tools = [("Bash", {"command": "ls"})]
        fmt = TelegramFormatter()
        text = format_tool_summary(tools, fmt)
        assert "<code>" in text

    def test_glob_tool(self):
        tools = [("Glob", {"pattern": "**/*.py"})]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "🔍" in text
        assert "Glob" in text
        assert "**/*.py" in text

    def test_grep_tool(self):
        tools = [
            ("Grep", {"pattern": "TODO"}),
            ("Grep", {"pattern": "FIXME"}),
        ]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "🔍" in text
        assert "TODO" in text
        assert "FIXME" in text

    def test_websearch_tool(self):
        tools = [("WebSearch", {"query": "python docs"})]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "🌐" in text
        assert "Search" in text
        assert "python docs" in text

    def test_webfetch_single(self):
        tools = [("WebFetch", {"url": "https://example.com"})]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "🌐" in text
        assert "Fetch" in text
        assert "×" not in text

    def test_webfetch_multiple(self):
        tools = [
            ("WebFetch", {"url": "https://a.com"}),
            ("WebFetch", {"url": "https://b.com"}),
        ]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "Fetch" in text
        assert "×2" in text

    def test_read_write_tools(self):
        tools = [
            ("Read", {"file_path": "/a/b/file.py"}),
            ("Write", {"file_path": "/c/d/out.txt"}),
        ]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "✏️" in text
        assert "file.py" in text
        assert "out.txt" in text

    def test_bash_long_command_truncated(self):
        long_cmd = "x" * 100
        tools = [("Bash", {"command": long_cmd})]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "..." in text
        assert len(text) < len(long_cmd) + 20

    def test_mixed_tools(self):
        tools = [
            ("Bash", {"command": "ls"}),
            ("Read", {"file_path": "/a/foo.py"}),
            ("Glob", {"pattern": "*.md"}),
            ("WebSearch", {"query": "test"}),
        ]
        fmt = PlainTextFormatter()
        text = format_tool_summary(tools, fmt)
        assert "⚡" in text
        assert "✏️" in text
        assert "🔍" in text
        assert "🌐" in text

    def test_default_formatter(self):
        tools = [("Bash", {"command": "echo hi"})]
        text = format_tool_summary(tools)
        assert "echo hi" in text


class TestToolStatusText:
    def test_read(self):
        text = tool_status_text("Read", {"file_path": "/a/b/foo.py"})
        assert "Reading" in text
        assert "foo.py" in text

    def test_write(self):
        text = tool_status_text("Write", {"file_path": "/a/b/out.txt"})
        assert "Writing" in text
        assert "out.txt" in text

    def test_edit(self):
        text = tool_status_text("Edit", {"file_path": "/a/b/bar.py"})
        assert "Editing" in text
        assert "bar.py" in text

    def test_read_no_path(self):
        text = tool_status_text("Read", {})
        assert "Reading" in text
        assert "file" in text

    def test_glob(self):
        text = tool_status_text("Glob", {"pattern": "**/*.py"})
        assert "Searching files" in text

    def test_grep(self):
        text = tool_status_text("Grep", {"pattern": "TODO"})
        assert "Searching codebase" in text

    def test_bash_with_description(self):
        text = tool_status_text("Bash", {"description": "Run unit tests"})
        assert "Run unit tests" in text

    def test_bash_long_description_truncated(self):
        long_desc = "x" * 60
        text = tool_status_text("Bash", {"description": long_desc})
        assert "..." in text
        assert len(text) < 60

    def test_bash_no_description(self):
        text = tool_status_text("Bash", {"command": "ls"})
        assert "Running command" in text

    def test_websearch(self):
        text = tool_status_text("WebSearch", {"query": "python docs"})
        assert "Searching web" in text

    def test_webfetch(self):
        text = tool_status_text("WebFetch", {"url": "https://example.com"})
        assert "Fetching page" in text

    def test_task(self):
        text = tool_status_text("Task", {})
        assert "Launching agent" in text

    def test_todowrite(self):
        text = tool_status_text("TodoWrite", {})
        assert "Updating tasks" in text

    def test_unknown_tool(self):
        text = tool_status_text("SomeNewTool", {})
        assert "SomeNewTool" in text


class TestFormatHelp:
    def test_plain(self):
        text = format_help()
        assert "/new" in text
        assert "/help" in text
        assert "/dirs" in text
        assert "/cd" in text

    def test_html(self):
        fmt = TelegramFormatter()
        text = format_help(fmt)
        assert "<b>" in text
        assert "<code>" in text
