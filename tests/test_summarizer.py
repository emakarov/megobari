"""Tests for the summarizer module."""

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.summarizer import (
    _format_messages,
    _parse_summary,
    check_and_summarize,
    log_message,
    maybe_summarize_background,
)


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


async def _mock_send(prompt: str) -> str:
    """Fake Claude call — returns a canned summary in short+full format."""
    return (
        "Discussed testing and databases\n"
        "---FULL---\n"
        "Summary: discussed testing and databases. "
        "Set up in-memory SQLite for tests."
    )


async def _populate_messages(session_name: str, count: int) -> None:
    """Add N message pairs (user + assistant) to the DB."""
    async with get_session() as s:
        repo = Repository(s)
        for i in range(count):
            await repo.add_message(session_name, "user", f"Question {i}")
            await repo.add_message(session_name, "assistant", f"Answer {i}")


async def test_log_message():
    await log_message("sess", "user", "hello")
    await log_message("sess", "assistant", "hi there")

    async with get_session() as s:
        repo = Repository(s)
        count = await repo.count_unsummarized("sess")
    assert count == 2


async def test_log_message_survives_errors():
    """log_message should not raise even if DB is broken."""
    await close_db()
    # Should not raise
    await log_message("sess", "user", "hello")
    # Re-init for fixture cleanup
    await init_db("sqlite+aiosqlite://")


async def test_check_and_summarize_below_threshold():
    await _populate_messages("sess", 5)  # 10 messages, but threshold is 20
    result = await check_and_summarize("sess", _mock_send, threshold=20)
    assert result is False


async def test_check_and_summarize_triggers():
    await _populate_messages("sess", 10)  # 20 messages

    result = await check_and_summarize("sess", _mock_send, threshold=20)
    assert result is True

    # Verify summary was saved
    async with get_session() as s:
        repo = Repository(s)
        summaries = await repo.get_summaries(session_name="sess")
    assert len(summaries) == 1
    assert "Summary:" in summaries[0].summary
    assert summaries[0].short_summary is not None
    assert "Discussed testing" in summaries[0].short_summary
    assert summaries[0].message_count == 20

    # All messages should be marked as summarized
    async with get_session() as s:
        repo = Repository(s)
        unsummarized = await repo.count_unsummarized("sess")
    assert unsummarized == 0


async def test_check_and_summarize_only_affects_target_session():
    await _populate_messages("sess_a", 10)  # 20 messages
    await _populate_messages("sess_b", 3)   # 6 messages

    await check_and_summarize("sess_a", _mock_send, threshold=20)

    async with get_session() as s:
        repo = Repository(s)
        unsummarized_b = await repo.count_unsummarized("sess_b")
    assert unsummarized_b == 6  # untouched


async def test_check_and_summarize_with_user_id():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=123)
        uid = user.id

    await _populate_messages("sess", 10)

    await check_and_summarize("sess", _mock_send, user_id=uid, threshold=20)

    async with get_session() as s:
        repo = Repository(s)
        summaries = await repo.get_summaries(session_name="sess")
    assert summaries[0].user_id == uid


async def test_check_and_summarize_handles_send_failure():
    await _populate_messages("sess", 10)

    async def _failing_send(prompt: str) -> str:
        raise RuntimeError("Claude is down")

    result = await check_and_summarize("sess", _failing_send, threshold=20)
    assert result is False

    # Messages should NOT be marked as summarized
    async with get_session() as s:
        repo = Repository(s)
        count = await repo.count_unsummarized("sess")
    assert count == 20


async def test_maybe_summarize_background_no_raise():
    """Fire-and-forget wrapper should never raise."""
    async def _failing_send(prompt: str) -> str:
        raise RuntimeError("boom")

    await _populate_messages("sess", 10)
    # Should not raise
    await maybe_summarize_background("sess", _failing_send, threshold=20)


async def test_format_messages():
    from megobari.db.models import Message

    msgs = [
        Message(session_name="s", role="user", content="What is Python?"),
        Message(session_name="s", role="assistant", content="A programming language."),
    ]
    result = _format_messages(msgs)
    assert "User: What is Python?" in result
    assert "Assistant: A programming language." in result


async def test_format_messages_truncates_long_content():
    from megobari.db.models import Message

    long_text = "x" * 5000
    msgs = [Message(session_name="s", role="assistant", content=long_text)]
    result = _format_messages(msgs)
    assert "[truncated]" in result
    assert len(result) < 3000


async def test_successive_summarizations():
    """After first summary, new messages accumulate and trigger a second."""
    await _populate_messages("sess", 5)  # 10 messages
    await check_and_summarize("sess", _mock_send, threshold=10)

    # Add more messages
    await _populate_messages("sess", 5)  # 10 more
    result = await check_and_summarize("sess", _mock_send, threshold=10)
    assert result is True

    async with get_session() as s:
        repo = Repository(s)
        summaries = await repo.get_summaries(session_name="sess")
    assert len(summaries) == 2


# ---------------------------------------------------------------
# _parse_summary tests
# ---------------------------------------------------------------


def test_parse_summary_with_delimiter():
    raw = "Short extract here\n---FULL---\nFull detailed summary here."
    short, full = _parse_summary(raw)
    assert short == "Short extract here"
    assert full == "Full detailed summary here."


def test_parse_summary_without_delimiter():
    """Fallback: no delimiter, short is first 150 chars of full."""
    raw = "Just a plain summary without any delimiter."
    short, full = _parse_summary(raw)
    assert full == raw
    assert short == raw  # under 150 chars, same as full


def test_parse_summary_without_delimiter_long():
    """Fallback for long text without delimiter."""
    raw = "Word " * 50  # 250 chars
    short, full = _parse_summary(raw)
    assert full == raw.strip()
    assert len(short) <= 153  # 150 + "..."
    assert short.endswith("...")


def test_parse_summary_short_too_long():
    """If short part exceeds 200 chars, it gets truncated."""
    long_short = "x" * 250
    raw = f"{long_short}\n---FULL---\nFull summary."
    short, full = _parse_summary(raw)
    assert len(short) == 200
    assert short.endswith("...")
    assert full == "Full summary."


def test_parse_summary_whitespace_handling():
    """Whitespace around delimiter is stripped."""
    raw = "  Short  \n\n---FULL---\n\n  Full text  "
    short, full = _parse_summary(raw)
    assert short == "Short"
    assert full == "Full text"


def test_parse_summary_multiple_delimiters():
    """Only split on the first delimiter."""
    raw = "Short\n---FULL---\nPart 1\n---FULL---\nPart 2"
    short, full = _parse_summary(raw)
    assert short == "Short"
    assert "Part 1" in full
    assert "---FULL---" in full  # second delimiter stays in full text
