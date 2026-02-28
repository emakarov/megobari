"""Admin, devops, and info command handlers."""

from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from megobari.db import Repository, get_session
from megobari.message_utils import format_help, format_session_info

from ._common import _get_sm, _reply, fmt

logger = logging.getLogger(__name__)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command to display help text."""
    await _reply(update, format_help(fmt), formatted=True)


async def cmd_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /current command to display active session info."""
    sm = _get_sm(context)
    session = sm.current
    if session is None:
        await _reply(update, "No active session. Use /new <name> first.")
        return
    await _reply(update, format_session_info(session, fmt), formatted=True)


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restart command to restart the bot process."""
    from megobari.actions import _do_restart, save_restart_marker

    chat_id = update.effective_chat.id
    save_restart_marker(chat_id)
    await _reply(update, "🔄 Restarting...")
    _do_restart()


async def cmd_release(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /release command to bump version, tag, push, and trigger PyPI publish."""
    import re
    import subprocess

    if not context.args:
        await _reply(update, "Usage: /release <version>\nExample: /release 0.2.0")
        return

    version = context.args[0].lstrip("v")
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        await _reply(update, f"Invalid version format: {version}\nExpected: X.Y.Z")
        return

    tag = f"v{version}"
    sm = _get_sm(context)
    session = sm.current
    project_root = session.cwd if session else str(Path.cwd())
    pyproject = Path(project_root) / "pyproject.toml"

    if not pyproject.is_file():
        await _reply(update, f"pyproject.toml not found in {project_root}")
        return

    await _reply(update, f"📦 Releasing {tag}...")

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
            await _reply(update, "⚠️ Could not find version field in pyproject.toml")
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

        await _reply(
            update,
            f"✅ Released {tag}\n"
            f"• Version bumped to {version}\n"
            f"• Tag {tag} pushed\n"
            f"• GitHub Actions will publish to PyPI",
        )

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else str(e)
        await _reply(update, f"❌ Release failed:\n{stderr}")
    except Exception as e:
        await _reply(update, f"❌ Release failed: {e}")


async def cmd_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /doctor command: run health checks."""
    sm = _get_sm(context)
    checks: list[str] = []

    # 1. Claude CLI check
    try:
        import claude_agent_sdk
        version = getattr(claude_agent_sdk, "__version__", "unknown")
        checks.append(f"✅ Claude SDK: v{version}")
    except ImportError:
        checks.append("❌ Claude SDK: not installed")

    # 2. CLI reachability
    try:
        import shutil
        cli_path = shutil.which("claude")
        if cli_path:
            checks.append(f"✅ Claude CLI: {cli_path}")
        else:
            checks.append("❌ Claude CLI: not found in PATH")
    except Exception as e:
        checks.append(f"❌ Claude CLI check failed: {e}")

    # 3. Sessions info
    all_sessions = sm.list_all()
    stale = sum(1 for s in all_sessions if s.session_id)
    checks.append(f"📋 Sessions: {len(all_sessions)} total, {stale} with context")

    # 4. Sessions dir disk usage
    sessions_dir = sm._sessions_dir
    if sessions_dir.exists():
        sessions_file = sessions_dir / "sessions.json"
        size_bytes = sessions_file.stat().st_size if sessions_file.exists() else 0
        if size_bytes < 1024:
            size_str = f"{size_bytes}B"
        else:
            size_str = f"{size_bytes / 1024:.1f}KB"
        checks.append(f"💾 Sessions file: {size_str}")
    else:
        checks.append("💾 Sessions dir: not found")

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
            f"🗄 DB: {user_count} users, {mem_count} memories, "
            f"{sum_count} summaries, {msg_count} messages"
        )
    except Exception as e:
        checks.append(f"❌ DB: {e}")

    # 6. Current session info
    session = sm.current
    if session:
        checks.append(
            f"🔧 Active session: {session.name} "
            f"(thinking={session.thinking}, effort={session.effort or 'default'})"
        )

    await _reply(update, "\n".join(checks))
