"""Handler modules for the Telegram bot.

Re-exports all public names for backward compatibility.
"""

from megobari.handlers._common import (
    SessionUsage,
    _accumulate_usage,
    _busy_sessions,
    _get_sm,
    _persist_usage,
    _reply,
    _set_reaction,
    _track_user,
    fmt,
)
from megobari.handlers.admin import cmd_current, cmd_doctor, cmd_help, cmd_release, cmd_restart
from megobari.handlers.claude import (
    StreamingAccumulator,
    _busy_emoji,
    _process_prompt,
    _send_typing_periodically,
    handle_document,
    handle_message,
    handle_photo,
    handle_voice,
)
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
    "fmt",
    "_busy_sessions",
    "_get_sm",
    "_reply",
    "_track_user",
    "_set_reaction",
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
    # scheduling
    "cmd_cron",
    "cmd_heartbeat",
    # claude
    "_send_typing_periodically",
    "StreamingAccumulator",
    "_busy_emoji",
    "handle_message",
    "_process_prompt",
    "handle_photo",
    "handle_document",
    "handle_voice",
]
