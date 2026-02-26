"""Async engine and session factory — swap DB by changing the URL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from megobari.db.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Default DB path next to sessions
_DEFAULT_DB_DIR = Path.home() / ".megobari"
_DEFAULT_DB_NAME = "megobari.db"


def _default_url() -> str:
    _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _DEFAULT_DB_DIR / _DEFAULT_DB_NAME
    return f"sqlite+aiosqlite:///{db_path}"


async def init_db(url: str | None = None) -> AsyncEngine:
    """Initialize the async engine and create tables.

    Args:
        url: SQLAlchemy async URL. Defaults to sqlite+aiosqlite:///~/.megobari/megobari.db
             For PostgreSQL: "postgresql+asyncpg://user:pass@host/db"
    """
    global _engine, _session_factory

    if url is None:
        url = _default_url()

    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return _engine


async def close_db() -> None:
    """Close the engine and release connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for database operations.

    Usage:
        async with get_session() as session:
            result = await session.execute(...)
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
