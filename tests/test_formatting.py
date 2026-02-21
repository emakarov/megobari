"""Tests for the Formatter abstraction."""

from __future__ import annotations

from megobari.formatting import PlainTextFormatter, TelegramFormatter


class TestTelegramFormatter:
    def setup_method(self):
        self.fmt = TelegramFormatter()

    def test_parse_mode(self):
        assert self.fmt.parse_mode == "HTML"

    def test_bold(self):
        assert self.fmt.bold("hi") == "<b>hi</b>"

    def test_italic(self):
        assert self.fmt.italic("hi") == "<i>hi</i>"

    def test_code_escapes(self):
        result = self.fmt.code("<script>")
        assert "<code>" in result
        assert "&lt;script&gt;" in result

    def test_pre_escapes(self):
        result = self.fmt.pre("a & b")
        assert "<pre>" in result
        assert "a &amp; b" in result

    def test_escape(self):
        assert self.fmt.escape("a < b & c") == "a &lt; b &amp; c"


class TestPlainTextFormatter:
    def setup_method(self):
        self.fmt = PlainTextFormatter()

    def test_parse_mode(self):
        assert self.fmt.parse_mode is None

    def test_noop(self):
        assert self.fmt.bold("hi") == "hi"
        assert self.fmt.italic("hi") == "hi"
        assert self.fmt.code("hi") == "hi"
        assert self.fmt.pre("hi") == "hi"
        assert self.fmt.escape("<>&") == "<>&"
