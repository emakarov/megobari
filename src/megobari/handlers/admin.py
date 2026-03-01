"""Admin, devops, and info command handlers."""

from __future__ import annotations

import logging
from pathlib import Path

from megobari.db import Repository, get_session
from megobari.message_utils import format_help, format_session_info
from megobari.transport import TransportContext

logger = logging.getLogger(__name__)


async def cmd_help(ctx: TransportContext) -> None:
    """Handle /help command to display help text."""
    fmt = ctx.formatter
    await ctx.reply(format_help(fmt), formatted=True)


async def cmd_current(ctx: TransportContext) -> None:
    """Handle /current command to display active session info."""
    fmt = ctx.formatter
    sm = ctx.session_manager
    session = sm.current
    if session is None:
        await ctx.reply("No active session. Use /new <name> first.")
        return
    await ctx.reply(format_session_info(session, fmt), formatted=True)


async def cmd_restart(ctx: TransportContext) -> None:
    """Handle /restart command to restart the bot process."""
    from megobari.actions import _do_restart, save_restart_marker
    from megobari.summarizer import log_message

    chat_id = ctx.chat_id
    save_restart_marker(chat_id)
    await ctx.reply("\U0001f504 Restarting...")
    try:
        session_name = ctx.session_manager.current.name if ctx.session_manager.current else "main"
        await log_message(session_name, "assistant", "🔄 Restarting...")
    except Exception:
        pass
    _do_restart()


async def cmd_release(ctx: TransportContext) -> None:
    """Handle /release command to bump version, tag, push, and trigger PyPI publish."""
    import re
    import subprocess

    if not ctx.args:
        await ctx.reply("Usage: /release <version>\nExample: /release 0.2.0")
        return

    version = ctx.args[0].lstrip("v")
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        await ctx.reply(f"Invalid version format: {version}\nExpected: X.Y.Z")
        return

    tag = f"v{version}"
    sm = ctx.session_manager
    session = sm.current
    project_root = session.cwd if session else str(Path.cwd())
    pyproject = Path(project_root) / "pyproject.toml"

    if not pyproject.is_file():
        await ctx.reply(f"pyproject.toml not found in {project_root}")
        return

    await ctx.reply(f"\U0001f4e6 Releasing {tag}...")

    try:
        # Update version in pyproject.toml
        content = pyproject.read_text()
        new_content = re.sub(
            r'^version\s*=\s*"[^"]*"',
            f'version = "{version}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if new_content == content:
            await ctx.reply("\u26a0\ufe0f Could not find version field in pyproject.toml")
            return
        pyproject.write_text(new_content)

        # Git commit, tag, push
        def _run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd, cwd=project_root, capture_output=True, text=True, check=True
            )

        _run(["git", "add", "pyproject.toml"])
        _run(["git", "commit", "-m", f"Release {tag}"])
        _run(["git", "tag", tag])
        _run(["git", "push"])
        _run(["git", "push", "--tags"])

        await ctx.reply(
            f"\u2705 Released {tag}\n"
            f"\u2022 Version bumped to {version}\n"
            f"\u2022 Tag {tag} pushed\n"
            f"\u2022 GitHub Actions will publish to PyPI",
        )

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else str(e)
        await ctx.reply(f"\u274c Release failed:\n{stderr}")
    except Exception as e:
        await ctx.reply(f"\u274c Release failed: {e}")


async def cmd_doctor(ctx: TransportContext) -> None:
    """Handle /doctor command: run health checks."""
    sm = ctx.session_manager
    checks: list[str] = []

    # 1. Claude CLI check
    try:
        import claude_agent_sdk
        version = getattr(claude_agent_sdk, "__version__", "unknown")
        checks.append(f"\u2705 Claude SDK: v{version}")
    except ImportError:
        checks.append("\u274c Claude SDK: not installed")

    # 2. CLI reachability
    try:
        import shutil
        cli_path = shutil.which("claude")
        if cli_path:
            checks.append(f"\u2705 Claude CLI: {cli_path}")
        else:
            checks.append("\u274c Claude CLI: not found in PATH")
    except Exception as e:
        checks.append(f"\u274c Claude CLI check failed: {e}")

    # 3. Sessions info
    all_sessions = sm.list_all()
    stale = sum(1 for s in all_sessions if s.session_id)
    checks.append(f"\U0001f4cb Sessions: {len(all_sessions)} total, {stale} with context")

    # 4. Sessions dir disk usage
    sessions_dir = sm._sessions_dir
    if sessions_dir.exists():
        sessions_file = sessions_dir / "sessions.json"
        size_bytes = sessions_file.stat().st_size if sessions_file.exists() else 0
        if size_bytes < 1024:
            size_str = f"{size_bytes}B"
        else:
            size_str = f"{size_bytes / 1024:.1f}KB"
        checks.append(f"\U0001f4be Sessions file: {size_str}")
    else:
        checks.append("\U0001f4be Sessions dir: not found")

    # 5. Database check
    try:
        async with get_session() as s:
            repo = Repository(s)
            from sqlalchemy import func, select

            from megobari.db.models import ConversationSummary, Memory, Message, User
            await repo.list_memories()  # just to test connectivity
            result = await s.execute(select(func.count()).select_from(User))
            user_count = result.scalar()
            result = await s.execute(select(func.count()).select_from(Memory))
            mem_count = result.scalar()
            result = await s.execute(select(func.count()).select_from(ConversationSummary))
            sum_count = result.scalar()
            result = await s.execute(select(func.count()).select_from(Message))
            msg_count = result.scalar()
        checks.append(
            f"\U0001f5c4 DB: {user_count} users, {mem_count} memories, "
            f"{sum_count} summaries, {msg_count} messages"
        )
    except Exception as e:
        checks.append(f"\u274c DB: {e}")

    # 6. Current session info
    session = sm.current
    if session:
        checks.append(
            f"\U0001f527 Active session: {session.name} "
            f"(thinking={session.thinking}, effort={session.effort or 'default'})"
        )

    await ctx.reply("\n".join(checks))


async def cmd_migrate(ctx: TransportContext) -> None:
    """Handle /migrate command: run Alembic migrations on the live DB."""
    from megobari.db.engine import close_db, init_db

    await ctx.reply("\U0001f504 Running database migrations...")
    try:
        await close_db()
        await init_db()
        await ctx.reply("\u2705 Migrations applied successfully.")
    except Exception as e:
        logger.exception("Migration failed")
        await ctx.reply(f"\u274c Migration failed: {e}")
