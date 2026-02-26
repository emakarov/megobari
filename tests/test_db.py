"""Tests for the database layer (models + repository)."""

import json

import pytest

from megobari.db import Repository, close_db, get_session, init_db


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


# ---------------------------------------------------------------
# Users
# ---------------------------------------------------------------

async def test_upsert_user_creates():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(
            telegram_id=12345,
            username="alice",
            first_name="Alice",
        )
    assert user.id is not None
    assert user.telegram_id == 12345
    assert user.username == "alice"


async def test_upsert_user_updates():
    async with get_session() as s:
        repo = Repository(s)
        await repo.upsert_user(telegram_id=12345, username="alice")

    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=12345, username="alice2")
    assert user.username == "alice2"


async def test_get_user():
    async with get_session() as s:
        repo = Repository(s)
        await repo.upsert_user(telegram_id=99)

    async with get_session() as s:
        repo = Repository(s)
        user = await repo.get_user(99)
    assert user is not None
    assert user.telegram_id == 99


async def test_get_user_not_found():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.get_user(999)
    assert user is None


# ---------------------------------------------------------------
# Personas
# ---------------------------------------------------------------

async def test_create_persona():
    async with get_session() as s:
        repo = Repository(s)
        p = await repo.create_persona(
            name="developer",
            description="Coding assistant",
            system_prompt="You are a developer",
            mcp_servers=["sgerp", "transit"],
            config={"temperature": 0.7},
        )
    assert p.id is not None
    assert p.name == "developer"
    assert json.loads(p.mcp_servers) == ["sgerp", "transit"]
    assert json.loads(p.config) == {"temperature": 0.7}


async def test_get_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(name="dev")

    async with get_session() as s:
        repo = Repository(s)
        p = await repo.get_persona("dev")
    assert p is not None
    assert p.name == "dev"


async def test_list_personas():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(name="bravo")
        await repo.create_persona(name="alpha")

    async with get_session() as s:
        repo = Repository(s)
        personas = await repo.list_personas()
    assert [p.name for p in personas] == ["alpha", "bravo"]


async def test_update_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(name="dev", description="old")

    async with get_session() as s:
        repo = Repository(s)
        p = await repo.update_persona("dev", description="new", mcp_servers=["a"])
    assert p is not None
    assert p.description == "new"
    assert Repository.persona_mcp_servers(p) == ["a"]


async def test_delete_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(name="temp")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_persona("temp")
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        assert await repo.get_persona("temp") is None


async def test_set_default_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(name="a", is_default=True)
        await repo.create_persona(name="b")

    async with get_session() as s:
        repo = Repository(s)
        p = await repo.set_default_persona("b")
    assert p is not None
    assert p.is_default is True

    # Check 'a' is no longer default
    async with get_session() as s:
        repo = Repository(s)
        a = await repo.get_persona("a")
    assert a.is_default is False


async def test_get_default_persona():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_persona(name="x", is_default=True)

    async with get_session() as s:
        repo = Repository(s)
        p = await repo.get_default_persona()
    assert p is not None
    assert p.name == "x"


async def test_persona_helpers():
    async with get_session() as s:
        repo = Repository(s)
        p = await repo.create_persona(
            name="t",
            mcp_servers=["a", "b"],
            config={"k": "v"},
        )
    assert Repository.persona_mcp_servers(p) == ["a", "b"]
    assert Repository.persona_config(p) == {"k": "v"}


async def test_persona_helpers_none():
    async with get_session() as s:
        repo = Repository(s)
        p = await repo.create_persona(name="empty")
    assert Repository.persona_mcp_servers(p) == []
    assert Repository.persona_config(p) == {}


# ---------------------------------------------------------------
# Conversation Summaries
# ---------------------------------------------------------------

async def test_add_summary():
    async with get_session() as s:
        repo = Repository(s)
        cs = await repo.add_summary(
            session_name="default",
            summary="Worked on sgerp MCP tools",
            short_summary="sgerp MCP tools",
            topics=["sgerp", "mcp"],
            message_count=42,
            is_milestone=True,
        )
    assert cs.id is not None
    assert cs.is_milestone is True
    assert cs.short_summary == "sgerp MCP tools"
    assert Repository.summary_topics(cs) == ["sgerp", "mcp"]


async def test_add_summary_without_short_summary():
    """short_summary is optional — should default to None."""
    async with get_session() as s:
        repo = Repository(s)
        cs = await repo.add_summary(
            session_name="default",
            summary="Full summary text",
        )
    assert cs.id is not None
    assert cs.short_summary is None


async def test_get_summaries_filter():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(session_name="a", summary="one")
        await repo.add_summary(session_name="b", summary="two", is_milestone=True)
        await repo.add_summary(session_name="a", summary="three", is_milestone=True)

    async with get_session() as s:
        repo = Repository(s)
        all_a = await repo.get_summaries(session_name="a")
    assert len(all_a) == 2

    async with get_session() as s:
        repo = Repository(s)
        milestones = await repo.get_summaries(milestones_only=True)
    assert len(milestones) == 2


async def test_search_summaries():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_summary(session_name="x", summary="Built transit analysis tools")
        await repo.add_summary(session_name="x", summary="Fixed invoicing bug")

    async with get_session() as s:
        repo = Repository(s)
        results = await repo.search_summaries("transit")
    assert len(results) == 1
    assert "transit" in results[0].summary


async def test_summary_with_user_and_persona():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=1)
        persona = await repo.create_persona(name="dev")
        cs = await repo.add_summary(
            session_name="s1",
            summary="test",
            user_id=user.id,
            persona_id=persona.id,
        )
    assert cs.user_id is not None
    assert cs.persona_id is not None


# ---------------------------------------------------------------
# Memories
# ---------------------------------------------------------------

async def test_set_and_get_memory():
    async with get_session() as s:
        repo = Repository(s)
        mem = await repo.set_memory(
            category="preference",
            key="language",
            content="Python",
            metadata={"confidence": 0.95},
        )
    assert mem.id is not None
    assert mem.content == "Python"

    async with get_session() as s:
        repo = Repository(s)
        got = await repo.get_memory("preference", "language")
    assert got is not None
    assert Repository.memory_metadata(got) == {"confidence": 0.95}


async def test_set_memory_upserts():
    async with get_session() as s:
        repo = Repository(s)
        await repo.set_memory(category="pref", key="lang", content="Python")

    async with get_session() as s:
        repo = Repository(s)
        mem = await repo.set_memory(category="pref", key="lang", content="Rust")
    assert mem.content == "Rust"

    # Only one row
    async with get_session() as s:
        repo = Repository(s)
        all_mems = await repo.list_memories(category="pref")
    assert len(all_mems) == 1


async def test_list_memories():
    async with get_session() as s:
        repo = Repository(s)
        await repo.set_memory(category="pref", key="a", content="1")
        await repo.set_memory(category="pref", key="b", content="2")
        await repo.set_memory(category="fact", key="c", content="3")

    async with get_session() as s:
        repo = Repository(s)
        prefs = await repo.list_memories(category="pref")
    assert len(prefs) == 2

    async with get_session() as s:
        repo = Repository(s)
        all_mems = await repo.list_memories()
    assert len(all_mems) == 3


async def test_delete_memory():
    async with get_session() as s:
        repo = Repository(s)
        await repo.set_memory(category="tmp", key="x", content="val")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_memory("tmp", "x")
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        assert await repo.get_memory("tmp", "x") is None


async def test_delete_memory_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_memory("nope", "nope")
    assert deleted is False


async def test_memory_per_user():
    async with get_session() as s:
        repo = Repository(s)
        u1 = await repo.upsert_user(telegram_id=1)
        u2 = await repo.upsert_user(telegram_id=2)
        await repo.set_memory("pref", "color", "blue", user_id=u1.id)
        await repo.set_memory("pref", "color", "red", user_id=u2.id)

    async with get_session() as s:
        repo = Repository(s)
        m1 = await repo.list_memories(category="pref", user_id=u1.id)
        m2 = await repo.list_memories(category="pref", user_id=u2.id)
    assert m1[0].content == "blue"
    assert m2[0].content == "red"


async def test_memory_metadata_none():
    async with get_session() as s:
        repo = Repository(s)
        mem = await repo.set_memory(category="c", key="k", content="v")
    assert Repository.memory_metadata(mem) == {}


# ---------------------------------------------------------------
# Messages
# ---------------------------------------------------------------

async def test_add_message():
    async with get_session() as s:
        repo = Repository(s)
        msg = await repo.add_message(
            session_name="default",
            role="user",
            content="Hello there",
        )
    assert msg.id is not None
    assert msg.role == "user"
    assert msg.summarized is False


async def test_get_unsummarized_messages():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_message("sess", "user", "msg 1")
        await repo.add_message("sess", "assistant", "reply 1")
        await repo.add_message("other", "user", "msg X")

    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_unsummarized_messages("sess")
    assert len(msgs) == 2
    assert msgs[0].content == "msg 1"  # ordered by created_at asc


async def test_count_unsummarized():
    async with get_session() as s:
        repo = Repository(s)
        for i in range(5):
            await repo.add_message("sess", "user", f"msg {i}")

    async with get_session() as s:
        repo = Repository(s)
        count = await repo.count_unsummarized("sess")
    assert count == 5


async def test_mark_summarized():
    async with get_session() as s:
        repo = Repository(s)
        m1 = await repo.add_message("sess", "user", "msg 1")
        m2 = await repo.add_message("sess", "assistant", "reply 1")
        await repo.add_message("sess", "user", "msg 2")

    async with get_session() as s:
        repo = Repository(s)
        await repo.mark_summarized([m1.id, m2.id])

    async with get_session() as s:
        repo = Repository(s)
        unsummarized = await repo.get_unsummarized_messages("sess")
    assert len(unsummarized) == 1
    assert unsummarized[0].content == "msg 2"


async def test_mark_summarized_empty():
    """mark_summarized with empty list should be a no-op."""
    async with get_session() as s:
        repo = Repository(s)
        await repo.mark_summarized([])  # should not raise


async def test_get_recent_messages():
    async with get_session() as s:
        repo = Repository(s)
        for i in range(10):
            await repo.add_message("sess", "user", f"msg {i}")

    async with get_session() as s:
        repo = Repository(s)
        recent = await repo.get_recent_messages("sess", limit=3)
    assert len(recent) == 3
    assert recent[0].content == "msg 9"  # newest first


async def test_message_repr():
    async with get_session() as s:
        repo = Repository(s)
        msg = await repo.add_message("sess", "user", "Hello world")
    assert "role='user'" in repr(msg)
    assert "Hello world" in repr(msg)


# ---------------------------------------------------------------
# Engine
# ---------------------------------------------------------------

async def test_get_session_without_init_raises():
    await close_db()
    with pytest.raises(RuntimeError, match="not initialized"):
        async with get_session():
            pass
    # Re-init for autouse fixture cleanup
    await init_db("sqlite+aiosqlite://")


async def test_model_reprs():
    """Smoke test __repr__ for all models."""
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=1, username="test")
        persona = await repo.create_persona(name="p")
        cs = await repo.add_summary(
            session_name="s", summary="x", is_milestone=True
        )
        mem = await repo.set_memory("cat", "key", "val")

    assert "telegram_id=1" in repr(user)
    assert "name='p'" in repr(persona)
    assert "milestone" in repr(cs)
    assert "category='cat'" in repr(mem)


# ---------------------------------------------------------------
# Usage Records
# ---------------------------------------------------------------


async def test_add_usage():
    async with get_session() as s:
        repo = Repository(s)
        rec = await repo.add_usage("sess1", cost_usd=0.05, num_turns=10, duration_ms=30000)
    assert rec.id is not None
    assert rec.cost_usd == 0.05
    assert rec.session_name == "sess1"


async def test_get_session_usage():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_usage("sess1", 0.01, 3, 5000)
        await repo.add_usage("sess1", 0.02, 5, 8000)
        await repo.add_usage("other", 0.10, 20, 50000)

    async with get_session() as s:
        repo = Repository(s)
        usage = await repo.get_session_usage("sess1")
    assert usage["total_cost"] == pytest.approx(0.03)
    assert usage["total_turns"] == 8
    assert usage["total_duration_ms"] == 13000
    assert usage["query_count"] == 2


async def test_get_session_usage_empty():
    async with get_session() as s:
        repo = Repository(s)
        usage = await repo.get_session_usage("nonexistent")
    assert usage["total_cost"] == 0.0
    assert usage["query_count"] == 0


async def test_get_total_usage():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_usage("sess1", 0.01, 3, 5000)
        await repo.add_usage("sess2", 0.02, 5, 8000)
        await repo.add_usage("sess1", 0.03, 7, 12000)

    async with get_session() as s:
        repo = Repository(s)
        total = await repo.get_total_usage()
    assert total["total_cost"] == pytest.approx(0.06)
    assert total["total_turns"] == 15
    assert total["total_duration_ms"] == 25000
    assert total["query_count"] == 3
    assert total["session_count"] == 2


async def test_get_usage_records():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_usage("sess1", 0.01, 3, 5000)
        await repo.add_usage("sess1", 0.02, 5, 8000)
        await repo.add_usage("sess2", 0.10, 20, 50000)

    async with get_session() as s:
        repo = Repository(s)
        all_records = await repo.get_usage_records()
    assert len(all_records) == 3

    async with get_session() as s:
        repo = Repository(s)
        sess1_records = await repo.get_usage_records(session_name="sess1")
    assert len(sess1_records) == 2


async def test_usage_record_repr():
    async with get_session() as s:
        repo = Repository(s)
        rec = await repo.add_usage("sess1", 0.05, 10, 30000)
    assert "sess1" in repr(rec)
    assert "$0.0500" in repr(rec)


async def test_usage_with_user():
    async with get_session() as s:
        repo = Repository(s)
        user = await repo.upsert_user(telegram_id=42)
        rec = await repo.add_usage("sess1", 0.01, 3, 5000, user_id=user.id)
    assert rec.user_id == user.id


# ---------------------------------------------------------------
# Alembic migration engine
# ---------------------------------------------------------------


async def test_init_db_with_file_runs_alembic(tmp_path):
    """init_db with a file-based SQLite should run Alembic migrations."""
    await close_db()
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = await init_db(url)
    assert engine is not None
    assert db_path.exists()

    # Verify tables were created via Alembic
    async with get_session() as s:
        repo = Repository(s)
        count = await repo.count_unsummarized("nonexistent")
    assert count == 0

    # Verify alembic_version table exists
    async with get_session() as s:
        from sqlalchemy import text
        result = await s.execute(text("SELECT version_num FROM alembic_version"))
        versions = result.scalars().all()
    assert len(versions) == 1  # stamped at head

    await close_db()
    await init_db("sqlite+aiosqlite://")  # restore for fixture


async def test_init_db_alembic_idempotent(tmp_path):
    """Running init_db twice on the same DB should not fail."""
    await close_db()
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    await init_db(url)
    await close_db()
    # Second init should be a no-op (already at head)
    await init_db(url)

    async with get_session() as s:
        repo = Repository(s)
        await repo.add_message("sess", "user", "works")
    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_unsummarized_messages("sess")
    assert len(msgs) == 1

    await close_db()
    await init_db("sqlite+aiosqlite://")  # restore for fixture
