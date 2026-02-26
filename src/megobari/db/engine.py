"""Async engine and session factory — swap DB by changing the URL."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Default DB path next to sessions
_DEFAULT_DB_DIR = Path.home() / ".megobari"
_DEFAULT_DB_NAME = "megobari.db"

# Path to migrations directory (sibling to this file)
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _default_url() -> str:
    """Build default SQLite URL."""
    _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _DEFAULT_DB_DIR / _DEFAULT_DB_NAME
    return f"sqlite+aiosqlite:///{db_path}"


def _run_migrations_on_connection(connection) -> None:
    """Run Alembic upgrade head using an existing synchronous connection.

    This avoids creating a new engine or event loop — safe to call
    from within ``await conn.run_sync(...)``.

    Args:
        connection: A synchronous SQLAlchemy connection.
    """
    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    script = ScriptDirectory.from_config(config)

    def do_upgrade(rev, context):
        return script._upgrade_revs("head", rev)

    with EnvironmentContext(
        config,
        script,
        fn=do_upgrade,
        as_sql=False,
        destination_rev="head",
    ) as env:
        env.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with env.begin_transaction():
            env.run_migrations()


def _stamp_head_on_connection(connection) -> None:  # pragma: no cover
    """Stamp the database at alembic head without running migrations.

    Args:
        connection: A synchronous SQLAlchemy connection.
    """
    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    script = ScriptDirectory.from_config(config)

    def do_stamp(rev, context):
        return script._stamp_revs("head", rev)

    with EnvironmentContext(
        config,
        script,
        fn=do_stamp,
        as_sql=False,
        destination_rev="head",
    ) as env:
        env.configure(
            connection=connection,
            target_metadata=Base.metadata,
        )
        with env.begin_transaction():
            env.run_migrations()


async def init_db(url: str | None = None) -> AsyncEngine:
    """Initialize the async engine and run migrations.

    For persistent databases, runs Alembic migrations (upgrade head).
    For in-memory databases (tests), uses create_all() for speed.

    Args:
        url: SQLAlchemy async URL. Defaults to sqlite+aiosqlite:///~/.megobari/megobari.db
             For PostgreSQL: "postgresql+asyncpg://user:pass@host/db"
    """
    global _engine, _session_factory

    if url is None:
        url = _default_url()

    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    is_memory = url == "sqlite+aiosqlite://" or ":memory:" in url

    if is_memory:
        # Tests: use create_all() — fast, no migration files needed
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        # Production: run Alembic migrations through our async engine
        try:
            async with _engine.begin() as conn:
                await conn.run_sync(_run_migrations_on_connection)
            logger.info("Database migrations applied successfully")
        except Exception as exc:  # pragma: no cover
            # If tables already exist but no alembic_version table,
            # stamp the DB at head so future migrations work
            if "already exists" in str(exc).lower():
                logger.info("Existing DB without alembic_version — stamping at head")
                async with _engine.begin() as conn:
                    await conn.run_sync(_stamp_head_on_connection)
            else:
                logger.warning(
                    "Alembic migration failed, falling back to create_all",
                    exc_info=True,
                )
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
