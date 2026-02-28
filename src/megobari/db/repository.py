"""Repository — async CRUD for all models."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from megobari.db.models import (
    ConversationSummary,
    CronJob,
    Memory,
    Message,
    Persona,
    UsageRecord,
    User,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    """High-level async data access. Accepts a session from get_session()."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def upsert_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        """Create or update a user by telegram_id. Returns the User."""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self.session.add(user)
        else:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            user.last_seen_at = _utcnow()
        await self.session.flush()
        return user

    async def get_user(self, telegram_id: int) -> User | None:
        """Get user by telegram_id."""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Personas
    # ------------------------------------------------------------------

    async def create_persona(
        self,
        name: str,
        description: str | None = None,
        system_prompt: str | None = None,
        mcp_servers: list[str] | None = None,
        config: dict | None = None,
        is_default: bool = False,
    ) -> Persona:
        """Create a new persona."""
        persona = Persona(
            name=name,
            description=description,
            system_prompt=system_prompt,
            mcp_servers=json.dumps(mcp_servers) if mcp_servers else None,
            config=json.dumps(config) if config else None,
            is_default=is_default,
        )
        self.session.add(persona)
        await self.session.flush()
        return persona

    async def get_persona(self, name: str) -> Persona | None:
        """Get persona by name."""
        stmt = select(Persona).where(Persona.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_persona(self) -> Persona | None:
        """Get the default persona (if any)."""
        stmt = select(Persona).where(Persona.is_default.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_personas(self) -> list[Persona]:
        """List all personas."""
        stmt = select(Persona).order_by(Persona.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_persona(
        self,
        name: str,
        **kwargs,
    ) -> Persona | None:
        """Update persona fields. Pass mcp_servers as list, config as dict."""
        persona = await self.get_persona(name)
        if persona is None:
            return None
        for field, value in kwargs.items():
            if field == "mcp_servers" and isinstance(value, list):
                setattr(persona, field, json.dumps(value))
            elif field == "config" and isinstance(value, dict):
                setattr(persona, field, json.dumps(value))
            else:
                setattr(persona, field, value)
        await self.session.flush()
        return persona

    async def delete_persona(self, name: str) -> bool:
        """Delete persona by name. Returns True if deleted."""
        persona = await self.get_persona(name)
        if persona is None:
            return False
        await self.session.delete(persona)
        await self.session.flush()
        return True

    async def set_default_persona(self, name: str) -> Persona | None:
        """Set a persona as default (clears previous default)."""
        # Clear existing default
        stmt = select(Persona).where(Persona.is_default.is_(True))
        result = await self.session.execute(stmt)
        for p in result.scalars().all():
            p.is_default = False

        persona = await self.get_persona(name)
        if persona is None:
            return None
        persona.is_default = True
        await self.session.flush()
        return persona

    # ------------------------------------------------------------------
    # Persona helpers (JSON field accessors)
    # ------------------------------------------------------------------

    @staticmethod
    def persona_mcp_servers(persona: Persona) -> list[str]:
        """Parse mcp_servers JSON field."""
        if persona.mcp_servers is None:
            return []
        return json.loads(persona.mcp_servers)

    @staticmethod
    def persona_config(persona: Persona) -> dict:
        """Parse config JSON field."""
        if persona.config is None:
            return {}
        return json.loads(persona.config)

    # ------------------------------------------------------------------
    # Conversation Summaries
    # ------------------------------------------------------------------

    async def add_summary(
        self,
        session_name: str,
        summary: str,
        user_id: int | None = None,
        persona_id: int | None = None,
        topics: list[str] | None = None,
        message_count: int = 0,
        is_milestone: bool = False,
        short_summary: str | None = None,
    ) -> ConversationSummary:
        """Save a conversation summary."""
        cs = ConversationSummary(
            session_name=session_name,
            summary=summary,
            short_summary=short_summary,
            user_id=user_id,
            persona_id=persona_id,
            topics=json.dumps(topics) if topics else None,
            message_count=message_count,
            is_milestone=is_milestone,
        )
        self.session.add(cs)
        await self.session.flush()
        return cs

    async def get_summaries(
        self,
        session_name: str | None = None,
        milestones_only: bool = False,
        limit: int = 50,
    ) -> list[ConversationSummary]:
        """Get summaries, optionally filtered by session and milestone flag."""
        stmt = select(ConversationSummary).order_by(
            ConversationSummary.created_at.desc()
        )
        if session_name is not None:
            stmt = stmt.where(ConversationSummary.session_name == session_name)
        if milestones_only:
            stmt = stmt.where(ConversationSummary.is_milestone.is_(True))
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_summaries(
        self, query: str, limit: int = 20
    ) -> list[ConversationSummary]:
        """Search summaries by text content (LIKE match)."""
        stmt = (
            select(ConversationSummary)
            .where(ConversationSummary.summary.ilike(f"%{query}%"))
            .order_by(ConversationSummary.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Conversation Summary helpers
    # ------------------------------------------------------------------

    @staticmethod
    def summary_topics(cs: ConversationSummary) -> list[str]:
        """Parse topics JSON field."""
        if cs.topics is None:
            return []
        return json.loads(cs.topics)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(
        self,
        session_name: str,
        role: str,
        content: str,
        user_id: int | None = None,
    ) -> Message:
        """Log a message (user or assistant) for later summarization."""
        msg = Message(
            session_name=session_name,
            role=role,
            content=content,
            user_id=user_id,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_unsummarized_messages(
        self,
        session_name: str,
        limit: int = 200,
    ) -> list[Message]:
        """Get messages not yet included in any summary."""
        stmt = (
            select(Message)
            .where(
                Message.session_name == session_name,
                Message.summarized.is_(False),
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_unsummarized(self, session_name: str) -> int:
        """Count messages not yet summarized for a session."""
        stmt = (
            select(func.count(Message.id))
            .where(
                Message.session_name == session_name,
                Message.summarized.is_(False),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def mark_summarized(self, message_ids: list[int]) -> None:
        """Mark messages as included in a summary."""
        if not message_ids:
            return
        stmt = (
            update(Message)
            .where(Message.id.in_(message_ids))
            .values(summarized=True)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_recent_messages(
        self,
        session_name: str,
        limit: int = 50,
    ) -> list[Message]:
        """Get most recent messages for a session (newest first)."""
        stmt = (
            select(Message)
            .where(Message.session_name == session_name)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------

    async def set_memory(
        self,
        category: str,
        key: str,
        content: str,
        user_id: int | None = None,
        metadata: dict | None = None,
    ) -> Memory:
        """Create or update a memory entry (upsert by user_id+category+key)."""
        stmt = select(Memory).where(
            Memory.category == category,
            Memory.key == key,
        )
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        else:
            stmt = stmt.where(Memory.user_id.is_(None))

        result = await self.session.execute(stmt)
        mem = result.scalar_one_or_none()

        if mem is None:
            mem = Memory(
                user_id=user_id,
                category=category,
                key=key,
                content=content,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            self.session.add(mem)
        else:
            mem.content = content
            if metadata is not None:
                mem.metadata_json = json.dumps(metadata)
            mem.updated_at = _utcnow()
        await self.session.flush()
        return mem

    async def get_memory(
        self,
        category: str,
        key: str,
        user_id: int | None = None,
    ) -> Memory | None:
        """Get a specific memory by category+key."""
        stmt = select(Memory).where(
            Memory.category == category,
            Memory.key == key,
        )
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        else:
            stmt = stmt.where(Memory.user_id.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_memories(
        self,
        category: str | None = None,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[Memory]:
        """List memories, optionally filtered by category and/or user."""
        stmt = select(Memory).order_by(Memory.updated_at.desc())
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_memory(
        self,
        category: str,
        key: str,
        user_id: int | None = None,
    ) -> bool:
        """Delete a memory. Returns True if deleted."""
        mem = await self.get_memory(category, key, user_id)
        if mem is None:
            return False
        await self.session.delete(mem)
        await self.session.flush()
        return True

    @staticmethod
    def memory_metadata(mem: Memory) -> dict:
        """Parse metadata_json field."""
        if mem.metadata_json is None:
            return {}
        return json.loads(mem.metadata_json)

    # ------------------------------------------------------------------
    # Usage Records
    # ------------------------------------------------------------------

    async def add_usage(
        self,
        session_name: str,
        cost_usd: float,
        num_turns: int,
        duration_ms: int,
        user_id: int | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> UsageRecord:
        """Record a single query's usage."""
        record = UsageRecord(
            session_name=session_name,
            cost_usd=cost_usd,
            num_turns=num_turns,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            user_id=user_id,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_session_usage(
        self, session_name: str
    ) -> dict:
        """Get aggregated usage for a session.

        Returns dict with keys: total_cost, total_turns, total_duration_ms, query_count.
        """
        stmt = select(
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0).label("total_cost"),
            func.coalesce(func.sum(UsageRecord.num_turns), 0).label("total_turns"),
            func.coalesce(func.sum(UsageRecord.duration_ms), 0).label("total_duration_ms"),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0).label("total_output_tokens"),
            func.count(UsageRecord.id).label("query_count"),
        ).where(UsageRecord.session_name == session_name)
        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "total_cost": row.total_cost,
            "total_turns": row.total_turns,
            "total_duration_ms": row.total_duration_ms,
            "total_input_tokens": row.total_input_tokens,
            "total_output_tokens": row.total_output_tokens,
            "query_count": row.query_count,
        }

    async def get_total_usage(self) -> dict:
        """Get aggregated usage across all sessions.

        Returns dict with keys: total_cost, total_turns, total_duration_ms,
        total_input_tokens, total_output_tokens, query_count, session_count.
        """
        stmt = select(
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0).label("total_cost"),
            func.coalesce(func.sum(UsageRecord.num_turns), 0).label("total_turns"),
            func.coalesce(func.sum(UsageRecord.duration_ms), 0).label("total_duration_ms"),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0).label("total_output_tokens"),
            func.count(UsageRecord.id).label("query_count"),
            func.count(func.distinct(UsageRecord.session_name)).label("session_count"),
        )
        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "total_cost": row.total_cost,
            "total_turns": row.total_turns,
            "total_duration_ms": row.total_duration_ms,
            "total_input_tokens": row.total_input_tokens,
            "total_output_tokens": row.total_output_tokens,
            "query_count": row.query_count,
            "session_count": row.session_count,
        }

    async def get_usage_records(
        self,
        session_name: str | None = None,
        limit: int = 50,
    ) -> list[UsageRecord]:
        """Get recent usage records, optionally filtered by session."""
        stmt = select(UsageRecord).order_by(UsageRecord.created_at.desc())
        if session_name is not None:
            stmt = stmt.where(UsageRecord.session_name == session_name)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Cron Jobs
    # ------------------------------------------------------------------

    async def add_cron_job(
        self,
        name: str,
        cron_expression: str,
        prompt: str,
        session_name: str,
        isolated: bool = False,
        timezone: str | None = None,
    ) -> CronJob:
        """Create a new cron job."""
        job = CronJob(
            name=name,
            cron_expression=cron_expression,
            prompt=prompt,
            session_name=session_name,
            isolated=isolated,
            timezone=timezone,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def list_cron_jobs(self, enabled_only: bool = False) -> list[CronJob]:
        """List all cron jobs, optionally only enabled ones."""
        stmt = select(CronJob).order_by(CronJob.created_at.asc())
        if enabled_only:
            stmt = stmt.where(CronJob.enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_cron_job(self, name: str) -> CronJob | None:
        """Get a cron job by name."""
        stmt = select(CronJob).where(CronJob.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_cron_job(self, name: str) -> bool:
        """Delete a cron job by name. Returns True if deleted."""
        job = await self.get_cron_job(name)
        if job is None:
            return False
        await self.session.delete(job)
        await self.session.flush()
        return True

    async def toggle_cron_job(self, name: str, enabled: bool) -> CronJob | None:
        """Enable or disable a cron job. Returns the updated job or None."""
        job = await self.get_cron_job(name)
        if job is None:
            return None
        job.enabled = enabled
        await self.session.flush()
        return job

    async def update_cron_last_run(self, name: str) -> None:
        """Update the last_run_at timestamp for a cron job."""
        stmt = (
            update(CronJob)
            .where(CronJob.name == name)
            .values(last_run_at=_utcnow())
        )
        await self.session.execute(stmt)
