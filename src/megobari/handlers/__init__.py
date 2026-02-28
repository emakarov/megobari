"""Handler modules for the Telegram bot.

Re-exports all public names so that handlers can be used via
``from megobari.handlers import cmd_start`` etc.
"""

from megobari.handlers._common import (
    SessionUsage,
    _accumulate_usage,
    _busy_emoji,
    _busy_sessions,
    _persist_usage,
    _track_user,
)
from megobari.handlers.admin import (
    cmd_current,
    cmd_doctor,
    cmd_help,
    cmd_migrate,
    cmd_release,
    cmd_restart,
)
from megobari.handlers.claude import (
    StreamingAccumulator,
    _process_prompt,
    _send_typing_periodically,
    handle_document,
    handle_message,
    handle_photo,
    handle_voice,
)
from megobari.handlers.dashboard import cmd_dashboard
from megobari.handlers.monitoring import cmd_monitor
from megobari.handlers.persona import cmd_mcp, cmd_memory, cmd_persona, cmd_skills, cmd_summaries
from megobari.handlers.scheduling import cmd_cron, cmd_heartbeat
from megobari.handlers.sessions import (
    cmd_delete,
    cmd_new,
    cmd_permissions,
    cmd_rename,
    cmd_sessions,
    cmd_start,
    cmd_stream,
    cmd_switch,
)
from megobari.handlers.tuning import cmd_autonomous, cmd_effort, cmd_model, cmd_think
from megobari.handlers.usage import cmd_compact, cmd_context, cmd_history, cmd_usage
from megobari.handlers.workspace import cmd_cd, cmd_dirs, cmd_file

__all__ = [
    # _common
    "_busy_sessions",
    "_busy_emoji",
    "_track_user",
    "SessionUsage",
    "_accumulate_usage",
    "_persist_usage",
    # sessions
    "cmd_start",
    "cmd_new",
    "cmd_sessions",
    "cmd_switch",
    "cmd_delete",
    "cmd_rename",
    "cmd_stream",
    "cmd_permissions",
    # workspace
    "cmd_cd",
    "cmd_dirs",
    "cmd_file",
    # admin
    "cmd_help",
    "cmd_current",
    "cmd_restart",
    "cmd_release",
    "cmd_doctor",
    "cmd_migrate",
    # tuning
    "cmd_think",
    "cmd_effort",
    "cmd_model",
    "cmd_autonomous",
    # persona
    "cmd_persona",
    "cmd_mcp",
    "cmd_skills",
    "cmd_memory",
    "cmd_summaries",
    # usage
    "cmd_usage",
    "cmd_compact",
    "cmd_context",
    "cmd_history",
    # dashboard
    "cmd_dashboard",
    # monitoring
    "cmd_monitor",
    # scheduling
    "cmd_cron",
    "cmd_heartbeat",
    # claude
    "_send_typing_periodically",
    "StreamingAccumulator",
    "handle_message",
    "_process_prompt",
    "handle_photo",
    "handle_document",
    "handle_voice",
]
