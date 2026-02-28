"""SQLAlchemy async models for megobari persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all models."""


class User(Base):
    """Telegram user we're talking to."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # relationships
    summaries: Mapped[list[ConversationSummary]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list[Memory]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation of User."""
        return f"<User telegram_id={self.telegram_id} username={self.username!r}>"


class Persona(Base):
    """Named persona — a combination of system prompt additions and MCP tool sets."""

    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of MCP server names to enable, e.g. '["sgerp", "transit"]'
    mcp_servers: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of skill names (priority order), e.g. '["jira", "clickhouse"]'
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON object of extra config, e.g. '{"temperature": 0.7}'
    config: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    summaries: Mapped[list[ConversationSummary]] = relationship(
        back_populates="persona"
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation of Persona."""
        return f"<Persona name={self.name!r}>"


class ConversationSummary(Base):
    """Periodic summary / milestone of a conversation."""

    __tablename__ = "conversation_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    persona_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("personas.id"), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Short one-line extract for token-efficient context injection
    short_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of topic strings, e.g. '["sgerp", "transit", "invoicing"]'
    topics: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    user: Mapped[User | None] = relationship(back_populates="summaries")
    persona: Mapped[Persona | None] = relationship(back_populates="summaries")

    def __repr__(self) -> str:
        """Return developer-friendly representation of ConversationSummary."""
        label = "milestone" if self.is_milestone else "summary"
        return f"<ConversationSummary [{label}] session={self.session_name!r}>"


class Message(Base):
    """Individual message in a conversation — for summarization."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # Whether this message has been included in a summary already
    summarized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:
        """Return developer-friendly representation of Message."""
        preview = self.content[:40] + "..." if len(self.content) > 40 else self.content
        return f"<Message role={self.role!r} session={self.session_name!r} {preview!r}>"


class UsageRecord(Base):
    """Per-query usage record — cost, turns, duration."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cost_usd: Mapped[float] = mapped_column(nullable=False, default=0.0)
    num_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:
        """Return developer-friendly representation of UsageRecord."""
        return (
            f"<UsageRecord session={self.session_name!r} "
            f"cost=${self.cost_usd:.4f} turns={self.num_turns}>"
        )


class CronJob(Base):
    """Scheduled task that runs on a cron expression."""

    __tablename__ = "cron_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)  # 5-field
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False)
    isolated: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation of CronJob."""
        state = "enabled" if self.enabled else "disabled"
        return f"<CronJob name={self.name!r} cron={self.cron_expression!r} [{state}]>"


class Memory(Base):
    """Long-term factual memory — things learned about the user or context."""

    __tablename__ = "memories"

    __table_args__ = (
        UniqueConstraint("user_id", "category", "key", name="uq_user_category_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON object for extra metadata
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # relationships
    user: Mapped[User | None] = relationship(back_populates="memories")

    def __repr__(self) -> str:
        """Return developer-friendly representation of Memory."""
        return f"<Memory category={self.category!r} key={self.key!r}>"
