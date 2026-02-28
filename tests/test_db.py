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


async def test_get_recent_messages_all():
    """get_recent_messages_all returns messages across sessions, newest first."""
    async with get_session() as s:
        repo = Repository(s)
        # Create messages in different sessions
        await repo.add_message("session-a", "user", "a-msg-1")
        await repo.add_message("session-b", "user", "b-msg-1")
        await repo.add_message("session-a", "assistant", "a-reply-1")
        await repo.add_message("session-c", "user", "c-msg-1")
        await repo.add_message("session-b", "assistant", "b-reply-1")

    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_recent_messages_all(limit=30)
    assert len(msgs) == 5
    # Newest first
    assert msgs[0].content == "b-reply-1"
    assert msgs[1].content == "c-msg-1"
    assert msgs[4].content == "a-msg-1"
    # Multiple sessions represented
    session_names = {m.session_name for m in msgs}
    assert session_names == {"session-a", "session-b", "session-c"}


async def test_get_recent_messages_all_respects_limit():
    async with get_session() as s:
        repo = Repository(s)
        for i in range(10):
            await repo.add_message("sess", "user", f"msg-{i}")

    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_recent_messages_all(limit=3)
    assert len(msgs) == 3
    assert msgs[0].content == "msg-9"


async def test_get_recent_messages_all_empty():
    async with get_session() as s:
        repo = Repository(s)
        msgs = await repo.get_recent_messages_all()
    assert msgs == []


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


# ---------------------------------------------------------------
# Cron Jobs
# ---------------------------------------------------------------


async def test_add_cron_job():
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.add_cron_job(
            name="morning",
            cron_expression="0 7 * * *",
            prompt="Good morning briefing",
            session_name="default",
        )
    assert job.id is not None
    assert job.name == "morning"
    assert job.cron_expression == "0 7 * * *"
    assert job.prompt == "Good morning briefing"
    assert job.session_name == "default"
    assert job.enabled is True
    assert job.isolated is False
    assert job.last_run_at is None


async def test_add_cron_job_with_options():
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.add_cron_job(
            name="isolated_task",
            cron_expression="30 12 * * 1-5",
            prompt="Run checks",
            session_name="work",
            isolated=True,
            timezone="US/Pacific",
        )
    assert job.isolated is True
    assert job.timezone == "US/Pacific"


async def test_list_cron_jobs():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_cron_job("alpha", "0 8 * * *", "test", "default")
        await repo.add_cron_job("bravo", "0 9 * * *", "test", "default")

    async with get_session() as s:
        repo = Repository(s)
        jobs = await repo.list_cron_jobs()
    assert len(jobs) == 2
    assert jobs[0].name == "alpha"
    assert jobs[1].name == "bravo"


async def test_list_cron_jobs_enabled_only():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_cron_job("active", "0 8 * * *", "test", "default")
        j2 = await repo.add_cron_job("paused", "0 9 * * *", "test", "default")
        j2.enabled = False
        await s.flush()

    async with get_session() as s:
        repo = Repository(s)
        jobs = await repo.list_cron_jobs(enabled_only=True)
    assert len(jobs) == 1
    assert jobs[0].name == "active"


async def test_get_cron_job():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_cron_job("target", "0 8 * * *", "test", "default")

    async with get_session() as s:
        repo = Repository(s)
        job = await repo.get_cron_job("target")
    assert job is not None
    assert job.name == "target"


async def test_get_cron_job_not_found():
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.get_cron_job("nope")
    assert job is None


async def test_delete_cron_job():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_cron_job("temp", "0 8 * * *", "test", "default")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_cron_job("temp")
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        assert await repo.get_cron_job("temp") is None


async def test_delete_cron_job_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_cron_job("nope")
    assert deleted is False


async def test_toggle_cron_job():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_cron_job("toggle_test", "0 8 * * *", "test", "default")

    # Disable
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.toggle_cron_job("toggle_test", enabled=False)
    assert job is not None
    assert job.enabled is False

    # Re-enable
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.toggle_cron_job("toggle_test", enabled=True)
    assert job is not None
    assert job.enabled is True


async def test_toggle_cron_job_not_found():
    async with get_session() as s:
        repo = Repository(s)
        result = await repo.toggle_cron_job("nope", enabled=False)
    assert result is None


async def test_update_cron_last_run():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_cron_job("lastrun", "0 8 * * *", "test", "default")

    async with get_session() as s:
        repo = Repository(s)
        await repo.update_cron_last_run("lastrun")

    async with get_session() as s:
        repo = Repository(s)
        job = await repo.get_cron_job("lastrun")
    assert job.last_run_at is not None


async def test_cron_job_repr():
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.add_cron_job("repr_test", "0 8 * * *", "test", "default")
    r = repr(job)
    assert "repr_test" in r
    assert "0 8 * * *" in r
    assert "enabled" in r


async def test_cron_job_repr_disabled():
    async with get_session() as s:
        repo = Repository(s)
        job = await repo.add_cron_job("dis_test", "0 8 * * *", "test", "default")
        job.enabled = False
        await s.flush()
    r = repr(job)
    assert "disabled" in r


# ---------------------------------------------------------------
# Heartbeat Checks
# ---------------------------------------------------------------


async def test_add_heartbeat_check():
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.add_heartbeat_check("disk", "Check disk usage > 90%")
    assert check.id is not None
    assert check.name == "disk"
    assert check.prompt == "Check disk usage > 90%"
    assert check.enabled is True


async def test_list_heartbeat_checks():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_heartbeat_check("disk", "Check disk")
        await repo.add_heartbeat_check("mem", "Check memory")
        checks = await repo.list_heartbeat_checks()
    assert len(checks) == 2
    assert checks[0].name == "disk"
    assert checks[1].name == "mem"


async def test_list_heartbeat_checks_enabled_only():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_heartbeat_check("active", "Active check")
        c = await repo.add_heartbeat_check("paused", "Paused check")
        c.enabled = False
        await s.flush()
        checks = await repo.list_heartbeat_checks(enabled_only=True)
    assert len(checks) == 1
    assert checks[0].name == "active"


async def test_get_heartbeat_check():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_heartbeat_check("disk", "Check disk")
        check = await repo.get_heartbeat_check("disk")
    assert check is not None
    assert check.name == "disk"


async def test_get_heartbeat_check_not_found():
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.get_heartbeat_check("nope")
    assert check is None


async def test_delete_heartbeat_check():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_heartbeat_check("disk", "Check disk")
        deleted = await repo.delete_heartbeat_check("disk")
    assert deleted is True
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.get_heartbeat_check("disk")
    assert check is None


async def test_delete_heartbeat_check_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_heartbeat_check("nope")
    assert deleted is False


async def test_toggle_heartbeat_check():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_heartbeat_check("disk", "Check disk")
        check = await repo.toggle_heartbeat_check("disk", enabled=False)
    assert check is not None
    assert check.enabled is False
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.toggle_heartbeat_check("disk", enabled=True)
    assert check.enabled is True


async def test_toggle_heartbeat_check_not_found():
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.toggle_heartbeat_check("nope", enabled=False)
    assert check is None


async def test_heartbeat_check_repr():
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.add_heartbeat_check("disk", "Check disk")
    r = repr(check)
    assert "disk" in r
    assert "enabled" in r


async def test_heartbeat_check_repr_disabled():
    async with get_session() as s:
        repo = Repository(s)
        check = await repo.add_heartbeat_check("disk", "Check disk")
        check.enabled = False
        await s.flush()
    r = repr(check)
    assert "disabled" in r


# ---------------------------------------------------------------
# Dashboard Tokens
# ---------------------------------------------------------------


async def test_create_dashboard_token():
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.create_dashboard_token("my-app", "tok_abcdef1234567890")
    assert dt.id is not None
    assert dt.name == "my-app"
    assert dt.token_prefix == "tok_abcd"
    assert dt.enabled is True
    assert dt.last_used_at is None
    # Token should be hashed, not stored raw
    assert dt.token_hash != "tok_abcdef1234567890"
    assert len(dt.token_hash) == 64  # sha256 hex digest


async def test_verify_dashboard_token_valid():
    token = "secret_token_for_testing"
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_dashboard_token("app", token)

    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.verify_dashboard_token(token)
    assert dt is not None
    assert dt.name == "app"
    assert dt.last_used_at is not None  # should be updated on verify


async def test_verify_dashboard_token_disabled():
    token = "secret_token_disabled"
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.create_dashboard_token("app", token)
        dt.enabled = False
        await s.flush()

    async with get_session() as s:
        repo = Repository(s)
        result = await repo.verify_dashboard_token(token)
    assert result is None


async def test_verify_dashboard_token_invalid():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_dashboard_token("app", "real_token")

    async with get_session() as s:
        repo = Repository(s)
        result = await repo.verify_dashboard_token("wrong_token")
    assert result is None


async def test_list_dashboard_tokens():
    async with get_session() as s:
        repo = Repository(s)
        await repo.create_dashboard_token("first", "token_one")
        await repo.create_dashboard_token("second", "token_two")

    async with get_session() as s:
        repo = Repository(s)
        tokens = await repo.list_dashboard_tokens()
    assert len(tokens) == 2
    # Ordered by created_at desc, so "second" comes first
    assert tokens[0].name == "second"
    assert tokens[1].name == "first"


async def test_list_dashboard_tokens_empty():
    async with get_session() as s:
        repo = Repository(s)
        tokens = await repo.list_dashboard_tokens()
    assert tokens == []


async def test_toggle_dashboard_token():
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.create_dashboard_token("app", "some_token")
        token_id = dt.id

    # Disable
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.toggle_dashboard_token(token_id, enabled=False)
    assert dt is not None
    assert dt.enabled is False

    # Re-enable
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.toggle_dashboard_token(token_id, enabled=True)
    assert dt is not None
    assert dt.enabled is True


async def test_toggle_dashboard_token_not_found():
    async with get_session() as s:
        repo = Repository(s)
        result = await repo.toggle_dashboard_token(9999, enabled=False)
    assert result is None


async def test_delete_dashboard_token():
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.create_dashboard_token("temp", "temp_token")
        token_id = dt.id

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_dashboard_token(token_id)
    assert deleted is True

    # Verify it's gone
    async with get_session() as s:
        repo = Repository(s)
        tokens = await repo.list_dashboard_tokens()
    assert len(tokens) == 0


async def test_delete_dashboard_token_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_dashboard_token(9999)
    assert deleted is False


async def test_dashboard_token_repr():
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.create_dashboard_token("my-app", "tok_12345678rest")
    r = repr(dt)
    assert "my-app" in r
    assert "tok_1234" in r
    assert "enabled" in r


async def test_dashboard_token_repr_disabled():
    async with get_session() as s:
        repo = Repository(s)
        dt = await repo.create_dashboard_token("my-app", "tok_12345678rest")
        dt.enabled = False
        await s.flush()
    r = repr(dt)
    assert "disabled" in r


# ---------------------------------------------------------------
# Monitor Topics
# ---------------------------------------------------------------


async def test_add_monitor_topic():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic("Logistics SaaS", description="Competitor watch")
    assert topic.id is not None
    assert topic.name == "Logistics SaaS"
    assert topic.description == "Competitor watch"
    assert topic.enabled is True


async def test_add_monitor_topic_no_description():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic("Minimal")
    assert topic.description is None


async def test_list_monitor_topics():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic("Alpha")
        await repo.add_monitor_topic("Bravo")

    async with get_session() as s:
        repo = Repository(s)
        topics = await repo.list_monitor_topics()
    assert len(topics) == 2


async def test_list_monitor_topics_enabled_only():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic("Active")
        t2 = await repo.add_monitor_topic("Disabled")
        t2.enabled = False
        await s.flush()

    async with get_session() as s:
        repo = Repository(s)
        topics = await repo.list_monitor_topics(enabled_only=True)
    assert len(topics) == 1
    assert topics[0].name == "Active"


async def test_get_monitor_topic():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic("Target")

    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.get_monitor_topic("Target")
    assert topic is not None
    assert topic.name == "Target"


async def test_get_monitor_topic_not_found():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.get_monitor_topic("nope")
    assert topic is None


async def test_delete_monitor_topic():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic("ToDelete")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_topic("ToDelete")
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        assert await repo.get_monitor_topic("ToDelete") is None


async def test_delete_monitor_topic_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_topic("nope")
    assert deleted is False


async def test_delete_monitor_topic_cascades_entities():
    """Deleting a topic should cascade-delete its entities and resources."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic("CascadeTopic")
        entity = await repo.add_monitor_entity(topic.id, "SomeCompany")
        await repo.add_monitor_resource(
            topic.id, entity.id, "Blog", "https://example.com/blog", "blog"
        )

    async with get_session() as s:
        repo = Repository(s)
        await repo.delete_monitor_topic("CascadeTopic")

    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities()
    assert len(entities) == 0


# ---------------------------------------------------------------
# Monitor Entities
# ---------------------------------------------------------------


async def test_add_monitor_entity():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic("Tech")
        entity = await repo.add_monitor_entity(
            topic.id, "Acme Corp", url="https://acme.com",
            entity_type="company", description="A competitor",
        )
    assert entity.id is not None
    assert entity.name == "Acme Corp"
    assert entity.entity_type == "company"
    assert entity.enabled is True


async def test_add_monitor_entity_defaults():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic("Tech")
        entity = await repo.add_monitor_entity(topic.id, "BasicCo")
    assert entity.entity_type == "company"
    assert entity.url is None
    assert entity.description is None


async def test_list_monitor_entities():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        await repo.add_monitor_entity(t.id, "Alpha")
        await repo.add_monitor_entity(t.id, "Bravo")

    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities()
    assert len(entities) == 2


async def test_list_monitor_entities_by_topic():
    async with get_session() as s:
        repo = Repository(s)
        t1 = await repo.add_monitor_topic("Tech")
        t2 = await repo.add_monitor_topic("Finance")
        await repo.add_monitor_entity(t1.id, "TechCo")
        await repo.add_monitor_entity(t2.id, "FinCo")

    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities(topic_id=t1.id)
    assert len(entities) == 1
    assert entities[0].name == "TechCo"


async def test_list_monitor_entities_enabled_only():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        await repo.add_monitor_entity(t.id, "Active")
        e2 = await repo.add_monitor_entity(t.id, "Disabled")
        e2.enabled = False
        await s.flush()

    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities(enabled_only=True)
    assert len(entities) == 1
    assert entities[0].name == "Active"


async def test_get_monitor_entity():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        await repo.add_monitor_entity(t.id, "Target")

    async with get_session() as s:
        repo = Repository(s)
        entity = await repo.get_monitor_entity("Target")
    assert entity is not None
    assert entity.name == "Target"


async def test_get_monitor_entity_not_found():
    async with get_session() as s:
        repo = Repository(s)
        entity = await repo.get_monitor_entity("nope")
    assert entity is None


async def test_delete_monitor_entity():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        await repo.add_monitor_entity(t.id, "ToDelete")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_entity("ToDelete")
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        assert await repo.get_monitor_entity("ToDelete") is None


async def test_delete_monitor_entity_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_entity("nope")
    assert deleted is False


async def test_delete_monitor_entity_cascades_resources():
    """Deleting an entity should cascade-delete its resources."""
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "CascadeEntity")
        await repo.add_monitor_resource(
            t.id, e.id, "Blog", "https://example.com/blog", "blog"
        )

    async with get_session() as s:
        repo = Repository(s)
        await repo.delete_monitor_entity("CascadeEntity")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources()
    assert len(resources) == 0


# ---------------------------------------------------------------
# Monitor Resources
# ---------------------------------------------------------------


async def test_add_monitor_resource():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(
            t.id, e.id, "Pricing Page", "https://acme.com/pricing", "pricing"
        )
    assert r.id is not None
    assert r.name == "Pricing Page"
    assert r.resource_type == "pricing"
    assert r.enabled is True
    assert r.last_checked_at is None
    assert r.last_changed_at is None


async def test_list_monitor_resources():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        await repo.add_monitor_resource(t.id, e.id, "Blog", "https://acme.com/blog", "blog")
        await repo.add_monitor_resource(t.id, e.id, "Docs", "https://acme.com/docs", "docs")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources()
    assert len(resources) == 2


async def test_list_monitor_resources_by_entity():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e1 = await repo.add_monitor_entity(t.id, "Acme")
        e2 = await repo.add_monitor_entity(t.id, "Beta")
        await repo.add_monitor_resource(t.id, e1.id, "Blog", "https://acme.com", "blog")
        await repo.add_monitor_resource(t.id, e2.id, "Docs", "https://beta.com", "docs")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(entity_id=e1.id)
    assert len(resources) == 1
    assert resources[0].name == "Blog"


async def test_list_monitor_resources_by_topic():
    async with get_session() as s:
        repo = Repository(s)
        t1 = await repo.add_monitor_topic("Tech")
        t2 = await repo.add_monitor_topic("Finance")
        e1 = await repo.add_monitor_entity(t1.id, "TechCo")
        e2 = await repo.add_monitor_entity(t2.id, "FinCo")
        await repo.add_monitor_resource(t1.id, e1.id, "R1", "https://a.com", "blog")
        await repo.add_monitor_resource(t2.id, e2.id, "R2", "https://b.com", "blog")

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(topic_id=t1.id)
    assert len(resources) == 1
    assert resources[0].name == "R1"


async def test_list_monitor_resources_enabled_only():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        await repo.add_monitor_resource(t.id, e.id, "Active", "https://a.com", "blog")
        r2 = await repo.add_monitor_resource(t.id, e.id, "Off", "https://b.com", "blog")
        r2.enabled = False
        await s.flush()

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(enabled_only=True)
    assert len(resources) == 1
    assert resources[0].name == "Active"


async def test_delete_monitor_resource():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        rid = r.id

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_resource(rid)
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources()
    assert len(resources) == 0


async def test_delete_monitor_resource_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_resource(9999)
    assert deleted is False


async def test_update_monitor_resource_checked():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        rid = r.id

    # Check without changes
    async with get_session() as s:
        repo = Repository(s)
        await repo.update_monitor_resource_checked(rid, changed=False)

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources()
        r = resources[0]
    assert r.last_checked_at is not None
    assert r.last_changed_at is None


async def test_update_monitor_resource_checked_with_change():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        rid = r.id

    # Check with changes
    async with get_session() as s:
        repo = Repository(s)
        await repo.update_monitor_resource_checked(rid, changed=True)

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources()
        r = resources[0]
    assert r.last_checked_at is not None
    assert r.last_changed_at is not None


# ---------------------------------------------------------------
# Monitor Snapshots
# ---------------------------------------------------------------


async def test_add_monitor_snapshot():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        snap = await repo.add_monitor_snapshot(
            t.id, e.id, r.id, "abc123hash", "# Hello World", has_changes=True,
        )
    assert snap.id is not None
    assert snap.content_hash == "abc123hash"
    assert snap.content_markdown == "# Hello World"
    assert snap.has_changes is True


async def test_add_monitor_snapshot_no_changes():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        snap = await repo.add_monitor_snapshot(
            t.id, e.id, r.id, "abc123hash", "# Hello World",
        )
    assert snap.has_changes is False


async def test_get_latest_monitor_snapshot():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        await repo.add_monitor_snapshot(t.id, e.id, r.id, "hash1", "First")
        await repo.add_monitor_snapshot(t.id, e.id, r.id, "hash2", "Second")
        rid = r.id

    async with get_session() as s:
        repo = Repository(s)
        snap = await repo.get_latest_monitor_snapshot(rid)
    assert snap is not None
    assert snap.content_hash == "hash2"
    assert snap.content_markdown == "Second"


async def test_get_latest_monitor_snapshot_none():
    async with get_session() as s:
        repo = Repository(s)
        snap = await repo.get_latest_monitor_snapshot(9999)
    assert snap is None


# ---------------------------------------------------------------
# Monitor Digests
# ---------------------------------------------------------------


async def test_add_monitor_digest():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        snap = await repo.add_monitor_snapshot(t.id, e.id, r.id, "h", "content")
        digest = await repo.add_monitor_digest(
            t.id, e.id, r.id, snap.id, "Pricing changed by 20%", "pricing_change",
        )
    assert digest.id is not None
    assert digest.summary == "Pricing changed by 20%"
    assert digest.change_type == "pricing_change"


async def test_list_monitor_digests():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        snap = await repo.add_monitor_snapshot(t.id, e.id, r.id, "h", "content")
        await repo.add_monitor_digest(t.id, e.id, r.id, snap.id, "First", "update")
        await repo.add_monitor_digest(t.id, e.id, r.id, snap.id, "Second", "update")

    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests()
    assert len(digests) == 2
    # Most recent first
    assert digests[0].summary == "Second"
    assert digests[1].summary == "First"


async def test_list_monitor_digests_by_topic():
    async with get_session() as s:
        repo = Repository(s)
        t1 = await repo.add_monitor_topic("Tech")
        t2 = await repo.add_monitor_topic("Finance")
        e1 = await repo.add_monitor_entity(t1.id, "TechCo")
        e2 = await repo.add_monitor_entity(t2.id, "FinCo")
        r1 = await repo.add_monitor_resource(t1.id, e1.id, "R1", "https://a.com", "blog")
        r2 = await repo.add_monitor_resource(t2.id, e2.id, "R2", "https://b.com", "blog")
        s1 = await repo.add_monitor_snapshot(t1.id, e1.id, r1.id, "h1", "c1")
        s2 = await repo.add_monitor_snapshot(t2.id, e2.id, r2.id, "h2", "c2")
        await repo.add_monitor_digest(t1.id, e1.id, r1.id, s1.id, "Tech digest", "update")
        await repo.add_monitor_digest(t2.id, e2.id, r2.id, s2.id, "Fin digest", "update")

    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests(topic_id=t1.id)
    assert len(digests) == 1
    assert digests[0].summary == "Tech digest"


async def test_list_monitor_digests_by_entity():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e1 = await repo.add_monitor_entity(t.id, "Acme")
        e2 = await repo.add_monitor_entity(t.id, "Beta")
        r1 = await repo.add_monitor_resource(t.id, e1.id, "R1", "https://a.com", "blog")
        r2 = await repo.add_monitor_resource(t.id, e2.id, "R2", "https://b.com", "blog")
        s1 = await repo.add_monitor_snapshot(t.id, e1.id, r1.id, "h", "c")
        s2 = await repo.add_monitor_snapshot(t.id, e2.id, r2.id, "h", "c")
        await repo.add_monitor_digest(t.id, e1.id, r1.id, s1.id, "Acme change", "update")
        await repo.add_monitor_digest(t.id, e2.id, r2.id, s2.id, "Beta change", "update")

    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests(entity_id=e1.id)
    assert len(digests) == 1
    assert digests[0].summary == "Acme change"


async def test_list_monitor_digests_limit():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        snap = await repo.add_monitor_snapshot(t.id, e.id, r.id, "h", "c")
        for i in range(5):
            await repo.add_monitor_digest(t.id, e.id, r.id, snap.id, f"D{i}", "update")

    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests(limit=3)
    assert len(digests) == 3


# ---------------------------------------------------------------
# Monitor Subscribers
# ---------------------------------------------------------------


async def test_add_monitor_subscriber():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        sub = await repo.add_monitor_subscriber(
            "telegram", '{"chat_id": 123}', topic_id=t.id,
        )
    assert sub.id is not None
    assert sub.channel_type == "telegram"
    assert sub.channel_config == '{"chat_id": 123}'
    assert sub.topic_id == t.id
    assert sub.entity_id is None
    assert sub.resource_id is None
    assert sub.enabled is True


async def test_add_monitor_subscriber_entity_level():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        sub = await repo.add_monitor_subscriber(
            "telegram", '{"chat_id": 456}', entity_id=e.id,
        )
    assert sub.entity_id == e.id
    assert sub.topic_id is None


async def test_add_monitor_subscriber_resource_level():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        sub = await repo.add_monitor_subscriber(
            "telegram", '{"chat_id": 789}', resource_id=r.id,
        )
    assert sub.resource_id == r.id


async def test_list_monitor_subscribers_by_topic():
    """list_monitor_subscribers should use OR for filter conditions."""
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        # Sub at topic level
        await repo.add_monitor_subscriber("telegram", '{"c": 1}', topic_id=t.id)
        # Sub at entity level
        await repo.add_monitor_subscriber("telegram", '{"c": 2}', entity_id=e.id)
        # Sub at resource level
        await repo.add_monitor_subscriber("telegram", '{"c": 3}', resource_id=r.id)

    async with get_session() as s:
        repo = Repository(s)
        # Query with topic_id — should match the topic-level subscriber
        subs = await repo.list_monitor_subscribers(topic_id=t.id)
    assert len(subs) == 1
    assert subs[0].channel_config == '{"c": 1}'


async def test_list_monitor_subscribers_or_filter():
    """When passing multiple filter params, use OR."""
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        e = await repo.add_monitor_entity(t.id, "Acme")
        r = await repo.add_monitor_resource(t.id, e.id, "Blog", "https://a.com", "blog")
        await repo.add_monitor_subscriber("telegram", '{"c": 1}', topic_id=t.id)
        await repo.add_monitor_subscriber("telegram", '{"c": 2}', entity_id=e.id)
        await repo.add_monitor_subscriber("telegram", '{"c": 3}', resource_id=r.id)

    async with get_session() as s:
        repo = Repository(s)
        # Query with topic_id AND entity_id — should return both via OR
        subs = await repo.list_monitor_subscribers(topic_id=t.id, entity_id=e.id)
    assert len(subs) == 2


async def test_list_monitor_subscribers_only_enabled():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        await repo.add_monitor_subscriber("telegram", '{"c": 1}', topic_id=t.id)
        s2 = await repo.add_monitor_subscriber("telegram", '{"c": 2}', topic_id=t.id)
        s2.enabled = False
        await s.flush()

    async with get_session() as s:
        repo = Repository(s)
        subs = await repo.list_monitor_subscribers(topic_id=t.id)
    assert len(subs) == 1


async def test_list_monitor_subscribers_no_filter():
    """Without filters, return all enabled subscribers."""
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        await repo.add_monitor_subscriber("telegram", '{"c": 1}', topic_id=t.id)
        await repo.add_monitor_subscriber("email", '{"e": "x@x.com"}')

    async with get_session() as s:
        repo = Repository(s)
        subs = await repo.list_monitor_subscribers()
    assert len(subs) == 2


async def test_delete_monitor_subscriber():
    async with get_session() as s:
        repo = Repository(s)
        t = await repo.add_monitor_topic("Tech")
        sub = await repo.add_monitor_subscriber("telegram", '{"c": 1}', topic_id=t.id)
        sid = sub.id

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_subscriber(sid)
    assert deleted is True

    async with get_session() as s:
        repo = Repository(s)
        subs = await repo.list_monitor_subscribers()
    assert len(subs) == 0


async def test_delete_monitor_subscriber_not_found():
    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_subscriber(9999)
    assert deleted is False
