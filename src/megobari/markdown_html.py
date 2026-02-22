"""Convert Markdown text to Telegram-compatible HTML.

Handles the subset of Markdown that Claude typically produces:
  - **bold** / __bold__        → <b>
  - *italic*                   → <i>
  - `inline code`              → <code>
  - ```code blocks```          → <pre> (with optional language)
  - [link text](url)           → <a href>
  - # / ## / ### headings      → <b>
  - > blockquotes              → <blockquote>
  - Unordered lists (- / * / •)
  - Ordered lists (1. 2. 3.)
  - ~~strikethrough~~          → <s>
  - --- / *** horizontal rules → em-dash line
  - | tables |                 → <pre> with aligned columns

Uses only tags supported by Telegram Bot API ``parse_mode='HTML'``:
<b>, <i>, <u>, <s>, <code>, <pre>, <a>, <blockquote>,
<blockquote expandable>, <tg-spoiler>, <tg-emoji>.

All other text is HTML-escaped to prevent injection.
"""

from __future__ import annotations

import html
import re


def markdown_to_html(text: str) -> str:
    """Convert Markdown to Telegram-safe HTML.

    Returns a string suitable for ``parse_mode='HTML'`` in Telegram.
    """
    if not text:
        return text

    # Split out fenced code blocks first — they must not be processed
    parts = _split_code_blocks(text)
    result_parts: list[str] = []

    for is_code, content in parts:
        if is_code:
            result_parts.append(content)  # already formatted
        else:
            # Split tables out of inline content
            table_parts = _split_tables(content)
            for is_table, segment in table_parts:
                if is_table:
                    result_parts.append(segment)
                else:
                    result_parts.append(_convert_inline(segment))

    return "".join(result_parts)


# ---------------------------------------------------------------------------
# Fenced code blocks
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(\w*)\n(.*?)```",
    re.DOTALL,
)


def _split_code_blocks(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_code_block, content) segments."""
    parts: list[tuple[bool, str]] = []
    last_end = 0

    for m in _CODE_BLOCK_RE.finditer(text):
        if m.start() > last_end:
            parts.append((False, text[last_end:m.start()]))
        lang = m.group(1)
        code = m.group(2)
        # Remove trailing newline inside block if present
        if code.endswith("\n"):
            code = code[:-1]
        if lang:
            parts.append((True, f'<pre><code class="language-{html.escape(lang)}">'
                                f"{html.escape(code)}</code></pre>"))
        else:
            parts.append((True, f"<pre>{html.escape(code)}</pre>"))
        last_end = m.end()

    if last_end < len(text):
        parts.append((False, text[last_end:]))

    return parts


# ---------------------------------------------------------------------------
# Markdown tables → <pre> with aligned columns
# ---------------------------------------------------------------------------

# A table line: starts with |, contains at least one more |
_TABLE_LINE_RE = re.compile(r"^\|.+\|[ \t]*$", re.MULTILINE)

# Separator line: | --- | --- | (with optional colons for alignment)
_TABLE_SEP_RE = re.compile(r"^\|[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|[ \t]*$")


def _split_tables(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_table, content) segments.

    Consecutive lines that look like a Markdown table (starting/ending with |)
    are rendered as a ``<pre>`` block with cleaned-up alignment.
    """
    lines = text.split("\n")
    parts: list[tuple[bool, str]] = []
    buf: list[str] = []
    in_table = False

    def _flush_text() -> None:
        if buf:
            parts.append((False, "\n".join(buf)))
            buf.clear()

    def _flush_table(table_lines: list[str]) -> None:
        rendered = _render_table(table_lines)
        parts.append((True, rendered))

    table_buf: list[str] = []

    for line in lines:
        if _TABLE_LINE_RE.match(line):
            if not in_table:
                _flush_text()
                in_table = True
                table_buf = []
            table_buf.append(line)
        else:
            if in_table:
                _flush_table(table_buf)
                in_table = False
                table_buf = []
            buf.append(line)

    if in_table:
        _flush_table(table_buf)
    else:
        _flush_text()

    return parts


def _render_table(table_lines: list[str]) -> str:
    """Render Markdown table as a ``<pre>`` block with space-padded columns.

    Telegram doesn't support HTML tables, so we render inside ``<pre>`` with
    monospace alignment.  No box-drawing characters — just spaces for padding.
    """
    rows: list[list[str]] = []

    for line in table_lines:
        stripped = line.strip()
        if _TABLE_SEP_RE.match(stripped):
            continue  # skip separator lines
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = [c.strip().replace("**", "") for c in stripped.split("|")]
        rows.append(cells)

    if not rows:
        return html.escape("\n".join(table_lines))

    # Compute column widths
    n_cols = max(len(r) for r in rows)
    widths = [0] * n_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < n_cols:
                widths[i] = max(widths[i], len(cell))

    # Format each row with space padding
    formatted: list[str] = []
    for row in rows:
        parts = []
        for i in range(n_cols):
            cell = row[i] if i < len(row) else ""
            parts.append(cell.ljust(widths[i]))
        formatted.append("  ".join(parts))

    return f"<pre>{html.escape(chr(10).join(formatted))}</pre>"


# ---------------------------------------------------------------------------
# Inline conversion (applied to non-code-block segments)
# ---------------------------------------------------------------------------

# Inline code: `...`
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

# Bold: **...**  or __...__
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")

# Italic: *...*  (but not **)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")

# Strikethrough: ~~...~~
_STRIKE_RE = re.compile(r"~~(.+?)~~")

# Links: [text](url)
_LINK_RE = re.compile(r"\[([^\]]+)]\(([^)]+)\)")

# Headings: # ... at start of line
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Blockquote: > ... at start of line
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$", re.MULTILINE)

# Horizontal rules: ---, ***, ___  (3+ chars, alone on line)
_HR_RE = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)

# Unordered list items: - item, * item, • item
_UL_RE = re.compile(r"^[ \t]*[-*•]\s+", re.MULTILINE)

# Ordered list items: 1. item, 2. item
_OL_RE = re.compile(r"^[ \t]*(\d+)\.\s+", re.MULTILINE)


def _collapse_blockquotes(
    text: str, placeholder_fn: callable,
) -> str:
    """Group consecutive ``> ...`` lines into ``<blockquote>`` blocks."""
    lines = text.split("\n")
    result: list[str] = []
    quote_buf: list[str] = []

    def _flush_quote() -> None:
        if quote_buf:
            inner = "\n".join(quote_buf)
            result.append(placeholder_fn(
                f"<blockquote>{html.escape(inner)}</blockquote>"
            ))
            quote_buf.clear()

    for line in lines:
        m = _BLOCKQUOTE_RE.match(line)
        if m:
            quote_buf.append(m.group(1))
        else:
            _flush_quote()
            result.append(line)

    _flush_quote()
    return "\n".join(result)


def _convert_inline(text: str) -> str:
    """Convert inline Markdown to HTML (for non-code-block segments)."""
    # ---- Phase 1: extract things that must not be HTML-escaped ----

    # Protect inline code spans
    placeholders: list[str] = []

    def _placeholder(html_content: str) -> str:
        idx = len(placeholders)
        placeholders.append(html_content)
        return f"\x00PH{idx}\x00"

    def _save_code(m: re.Match) -> str:
        return _placeholder(f"<code>{html.escape(m.group(1))}</code>")

    text = _INLINE_CODE_RE.sub(_save_code, text)

    # Horizontal rules (before escaping, since --- uses special chars)
    text = _HR_RE.sub(lambda m: _placeholder("—" * 20), text)

    # Headings (# chars get escaped otherwise)
    text = _HEADING_RE.sub(
        lambda m: _placeholder(f"<b>{html.escape(m.group(2))}</b>"), text
    )

    # Blockquotes — group consecutive > lines into <blockquote>
    text = _collapse_blockquotes(text, _placeholder)

    # Links: [text](url)  — protect from escaping
    text = _LINK_RE.sub(
        lambda m: _placeholder(
            f'<a href="{html.escape(m.group(2))}">'
            f"{html.escape(m.group(1))}</a>"
        ),
        text,
    )

    # ---- Phase 2: HTML-escape everything else ----
    text = html.escape(text)

    # ---- Phase 3: inline formatting (on escaped text) ----

    # Bold (before italic, since * is shared)
    text = _BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)

    # Italic
    text = _ITALIC_RE.sub(lambda m: f"<i>{m.group(1)}</i>", text)

    # Strikethrough
    text = _STRIKE_RE.sub(lambda m: f"<s>{m.group(1)}</s>", text)

    # Unordered lists: replace marker with bullet
    text = _UL_RE.sub("  • ", text)

    # Ordered lists: keep number with dot
    text = _OL_RE.sub(lambda m: f"  {m.group(1)}. ", text)

    # ---- Phase 4: restore placeholders ----
    for idx, ph_html in enumerate(placeholders):
        text = text.replace(f"\x00PH{idx}\x00", ph_html)

    return text
