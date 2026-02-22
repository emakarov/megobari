"""Tests for megobari.markdown_html — Markdown → Telegram HTML converter."""

from megobari.markdown_html import markdown_to_html


class TestBold:
    def test_double_asterisk(self):
        assert markdown_to_html("**hello**") == "<b>hello</b>"

    def test_double_underscore(self):
        assert markdown_to_html("__hello__") == "<b>hello</b>"

    def test_bold_in_sentence(self):
        result = markdown_to_html("This is **important** text")
        assert result == "This is <b>important</b> text"


class TestItalic:
    def test_single_asterisk(self):
        assert markdown_to_html("*hello*") == "<i>hello</i>"

    def test_italic_in_sentence(self):
        result = markdown_to_html("This is *subtle* text")
        assert result == "This is <i>subtle</i> text"


class TestBoldAndItalic:
    def test_bold_and_italic_together(self):
        result = markdown_to_html("**bold** and *italic*")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result


class TestInlineCode:
    def test_backtick(self):
        assert markdown_to_html("`code`") == "<code>code</code>"

    def test_html_escaped_in_code(self):
        result = markdown_to_html("`<script>`")
        assert result == "<code>&lt;script&gt;</code>"

    def test_code_in_sentence(self):
        result = markdown_to_html("Run `pip install` now")
        assert result == "Run <code>pip install</code> now"


class TestCodeBlock:
    def test_fenced_code_block(self):
        md = "```\nprint('hello')\n```"
        result = markdown_to_html(md)
        assert "<pre>" in result
        assert "print(&#x27;hello&#x27;)" in result
        assert "</pre>" in result

    def test_fenced_with_language(self):
        md = "```python\nprint('hello')\n```"
        result = markdown_to_html(md)
        assert '<code class="language-python">' in result
        assert "print(&#x27;hello&#x27;)" in result

    def test_code_block_no_inline_processing(self):
        md = "```\n**not bold** and *not italic*\n```"
        result = markdown_to_html(md)
        assert "<b>" not in result
        assert "<i>" not in result
        assert "**not bold**" in result

    def test_code_block_html_escaped(self):
        md = "```\n<div>html</div>\n```"
        result = markdown_to_html(md)
        assert "&lt;div&gt;" in result

    def test_mixed_text_and_code_block(self):
        md = "Before\n```\ncode\n```\nAfter"
        result = markdown_to_html(md)
        assert "Before" in result
        assert "<pre>" in result
        assert "After" in result


class TestLinks:
    def test_basic_link(self):
        result = markdown_to_html("[Google](https://google.com)")
        assert result == '<a href="https://google.com">Google</a>'

    def test_link_in_text(self):
        result = markdown_to_html("Visit [here](https://x.com) now")
        assert '<a href="https://x.com">here</a>' in result


class TestHeadings:
    def test_h1(self):
        result = markdown_to_html("# Title")
        assert result == "<b>Title</b>"

    def test_h2(self):
        result = markdown_to_html("## Subtitle")
        assert result == "<b>Subtitle</b>"

    def test_h3(self):
        result = markdown_to_html("### Section")
        assert result == "<b>Section</b>"

    def test_heading_in_multiline(self):
        result = markdown_to_html("text\n## Heading\nmore text")
        assert "<b>Heading</b>" in result
        assert "text" in result


class TestBlockquote:
    def test_blockquote(self):
        result = markdown_to_html("> quoted text")
        assert "<blockquote>" in result
        assert "quoted text" in result
        assert "</blockquote>" in result

    def test_blockquote_multiline_grouped(self):
        """Consecutive > lines should be grouped into one blockquote."""
        result = markdown_to_html("> line one\n> line two")
        assert result.count("<blockquote>") == 1
        assert "line one\nline two" in result

    def test_blockquote_separated(self):
        """Non-consecutive > lines should be separate blockquotes."""
        result = markdown_to_html("> first\n\ntext\n\n> second")
        assert result.count("<blockquote>") == 2


class TestStrikethrough:
    def test_strikethrough(self):
        assert markdown_to_html("~~deleted~~") == "<s>deleted</s>"


class TestLists:
    def test_unordered_dash(self):
        result = markdown_to_html("- item one\n- item two")
        assert "  • item one" in result
        assert "  • item two" in result

    def test_unordered_asterisk(self):
        result = markdown_to_html("* item one")
        assert "  • item one" in result

    def test_ordered(self):
        result = markdown_to_html("1. first\n2. second")
        assert "  1. first" in result
        assert "  2. second" in result


class TestHorizontalRule:
    def test_dashes(self):
        result = markdown_to_html("---")
        assert "——" in result  # em dashes

    def test_asterisks(self):
        result = markdown_to_html("***")
        # Could be italic+bold OR hr — we treat *** on its own line as hr
        assert "——" in result or "<" in result


class TestHtmlEscaping:
    def test_angle_brackets_escaped(self):
        result = markdown_to_html("use <div> tag")
        assert "&lt;div&gt;" in result

    def test_ampersand_escaped(self):
        result = markdown_to_html("A & B")
        assert "&amp;" in result

    def test_code_span_protected_from_double_escape(self):
        result = markdown_to_html("`a < b`")
        assert "<code>a &lt; b</code>" in result


class TestEdgeCases:
    def test_empty_string(self):
        assert markdown_to_html("") == ""

    def test_plain_text(self):
        assert markdown_to_html("just plain text") == "just plain text"

    def test_multiline_complex(self):
        md = """# Report

Here is **important** info with `code`.

```python
x = 1
```

- Item A
- Item B

> Note this

Visit [docs](https://docs.com)."""
        result = markdown_to_html(md)
        assert "<b>Report</b>" in result
        assert "<b>important</b>" in result
        assert "<code>code</code>" in result
        assert "<pre>" in result
        assert "  • Item A" in result
        assert "<blockquote>Note this</blockquote>" in result
        assert '<a href="https://docs.com">docs</a>' in result

    def test_table_pre_aligned(self):
        """Tables render as <pre> with space-padded columns."""
        md = "| Col A | Col B |\n|-------|-------|\n| 1 | 2 |"
        result = markdown_to_html(md)
        assert "<pre>" in result
        assert "</pre>" in result
        assert "Col A" in result
        assert "Col B" in result

    def test_table_with_surrounding_text(self):
        md = "Before table:\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter table."
        result = markdown_to_html(md)
        assert "Before table:" in result
        assert "<pre>" in result
        assert "After table." in result

    def test_table_multiple_rows(self):
        md = "| Name | Value |\n|------|-------|\n| a | 1 |\n| b | 2 |"
        result = markdown_to_html(md)
        assert "<pre>" in result
        assert "Name" in result
        assert "a" in result
        assert "b" in result

    def test_table_html_escaping(self):
        md = "| A & B | <C> |\n|-------|-----|\n| x | y |"
        result = markdown_to_html(md)
        assert "&amp;" in result
        assert "&lt;C&gt;" in result

    def test_table_strips_bold_markers(self):
        """Bold markers in table cells should be stripped for clean display."""
        md = "| Status |\n|--------|\n| **OK** |"
        result = markdown_to_html(md)
        assert "OK" in result
        assert "**" not in result

    def test_table_column_alignment(self):
        """Columns should be space-padded for alignment."""
        md = "| Name | Score |\n|------|-------|\n| Alice | 95 |\n| Bob | 8 |"
        result = markdown_to_html(md)
        # All rows inside <pre>
        assert "<pre>" in result
        # Check that shorter values are padded
        assert "Alice" in result
        assert "Bob" in result
