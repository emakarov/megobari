"""Website monitor command handlers."""

from __future__ import annotations

import json
import logging

from megobari.db import Repository, get_session
from megobari.transport import TransportContext

logger = logging.getLogger(__name__)

_ENTITY_TYPES = ("company", "person", "organization", "product")
_RESOURCE_TYPES = ("blog", "repo", "pricing", "jobs", "changelog", "deals")

_USAGE = (
    "Usage:\n"
    "/monitor \u2014 overview\n"
    "/monitor topic list|add|remove\n"
    "/monitor entity list|add|remove [topic]\n"
    "/monitor resource list|add|remove [entity]\n"
    "/monitor subscribe <target> <channel> [config]\n"
    "/monitor check [topic] [entity]\n"
    "/monitor baseline [topic] \u2014 generate initial digests\n"
    "/monitor report [topic] \u2014 generate full report\n"
    "/monitor digest [topic|entity]"
)


async def cmd_monitor(ctx: TransportContext) -> None:
    """Handle /monitor command: manage website monitoring."""
    args = ctx.args

    if not args:
        await _show_overview(ctx)
        return

    sub = args[0].lower()

    if sub == "topic":
        await _handle_topic(ctx, args[1:])
    elif sub == "entity":
        await _handle_entity(ctx, args[1:])
    elif sub == "resource":
        await _handle_resource(ctx, args[1:])
    elif sub == "subscribe":
        await _handle_subscribe(ctx, args[1:])
    elif sub == "check":
        await _handle_check(ctx, args[1:])
    elif sub == "baseline":
        await _handle_baseline(ctx, args[1:])
    elif sub == "report":
        await _handle_report(ctx, args[1:])
    elif sub == "digest":
        await _handle_digest(ctx, args[1:])
    else:
        await ctx.reply(_USAGE)


async def _show_overview(ctx: TransportContext) -> None:
    """Show overview of all monitor topics with entity/resource counts."""
    fmt = ctx.formatter
    try:
        async with get_session() as s:
            repo = Repository(s)
            topics = await repo.list_monitor_topics()
            if not topics:
                await ctx.reply(
                    "No monitor topics. Use /monitor topic add <name>"
                )
                return

            lines = [fmt.bold("Monitor Topics:"), ""]
            for t in topics:
                icon = "\u2705" if t.enabled else "\u23f8"
                entities = await repo.list_monitor_entities(topic_id=t.id)
                entity_count = len(entities)
                resource_count = 0
                for e in entities:
                    resources = await repo.list_monitor_resources(
                        entity_id=e.id
                    )
                    resource_count += len(resources)
                desc = ""
                if t.description:
                    desc = f" \u2014 {fmt.escape(t.description)}"
                lines.append(
                    f"{icon} {fmt.bold(fmt.escape(t.name))}{desc}"
                )
                lines.append(
                    f"   {entity_count} entities, {resource_count} resources"
                )
            await ctx.reply("\n".join(lines), formatted=True)
    except Exception:
        await ctx.reply("Failed to load monitor overview.")


async def _handle_topic(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor topic subcommands."""
    fmt = ctx.formatter

    if not args or args[0].lower() == "list":
        try:
            async with get_session() as s:
                repo = Repository(s)
                topics = await repo.list_monitor_topics()
            if not topics:
                await ctx.reply("No topics. Use /monitor topic add <name>")
                return
            lines = [fmt.bold("Topics:"), ""]
            for t in topics:
                icon = "\u2705" if t.enabled else "\u23f8"
                desc = ""
                if t.description:
                    desc = f" \u2014 {fmt.escape(t.description)}"
                lines.append(
                    f"{icon} {fmt.bold(fmt.escape(t.name))}{desc}"
                )
            await ctx.reply("\n".join(lines), formatted=True)
        except Exception:
            await ctx.reply("Failed to list topics.")
        return

    action = args[0].lower()

    if action == "add":
        if len(args) < 2:
            await ctx.reply(
                "Usage: /monitor topic add <name> [description]"
            )
            return
        name = args[1]
        description = " ".join(args[2:]) if len(args) > 2 else None
        try:
            async with get_session() as s:
                repo = Repository(s)
                existing = await repo.get_monitor_topic(name)
                if existing:
                    await ctx.reply(
                        f"Topic '{name}' already exists."
                    )
                    return
                await repo.add_monitor_topic(
                    name=name, description=description
                )
            await ctx.reply(f"\u2705 Topic '{name}' created")
        except Exception:
            await ctx.reply("Failed to create topic.")

    elif action == "remove":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor topic remove <name>")
            return
        name = args[1]
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_monitor_topic(name)
            if deleted:
                await ctx.reply(f"\u2705 Deleted topic '{name}'")
            else:
                await ctx.reply(f"Topic '{name}' not found.")
        except Exception:
            await ctx.reply("Failed to delete topic.")

    else:
        await ctx.reply(
            "Usage: /monitor topic list|add|remove"
        )


async def _handle_entity(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor entity subcommands."""
    fmt = ctx.formatter

    if not args or args[0].lower() == "list":
        # /monitor entity list [topic]
        topic_filter = args[1] if len(args) > 1 else None
        try:
            async with get_session() as s:
                repo = Repository(s)
                topic_id = None
                if topic_filter:
                    topic = await repo.get_monitor_topic(topic_filter)
                    if not topic:
                        await ctx.reply(
                            f"Topic '{topic_filter}' not found."
                        )
                        return
                    topic_id = topic.id
                entities = await repo.list_monitor_entities(
                    topic_id=topic_id
                )
            if not entities:
                await ctx.reply(
                    "No entities. Use /monitor entity add "
                    "<topic> <name> <url> [type]"
                )
                return
            lines = [fmt.bold("Entities:"), ""]
            for e in entities:
                icon = "\u2705" if e.enabled else "\u23f8"
                lines.append(
                    f"{icon} {fmt.bold(fmt.escape(e.name))} "
                    f"({e.entity_type})"
                )
                if e.url:
                    lines.append(f"   {fmt.escape(e.url)}")
            await ctx.reply("\n".join(lines), formatted=True)
        except Exception:
            await ctx.reply("Failed to list entities.")
        return

    action = args[0].lower()

    if action == "add":
        # /monitor entity add <topic> <name> <url> [type]
        if len(args) < 4:
            await ctx.reply(
                "Usage: /monitor entity add <topic> <name> <url> [type]\n"
                f"Types: {', '.join(_ENTITY_TYPES)}"
            )
            return
        topic_name = args[1]
        name = args[2]
        url = args[3]
        entity_type = args[4] if len(args) > 4 else "company"
        if entity_type not in _ENTITY_TYPES:
            await ctx.reply(
                f"Invalid type '{entity_type}'. "
                f"Valid: {', '.join(_ENTITY_TYPES)}"
            )
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                topic = await repo.get_monitor_topic(topic_name)
                if not topic:
                    await ctx.reply(
                        f"Topic '{topic_name}' not found."
                    )
                    return
                existing = await repo.get_monitor_entity(name)
                if existing:
                    await ctx.reply(
                        f"Entity '{name}' already exists."
                    )
                    return
                await repo.add_monitor_entity(
                    topic_id=topic.id,
                    name=name,
                    url=url,
                    entity_type=entity_type,
                )
            await ctx.reply(
                f"\u2705 Entity '{name}' added to topic '{topic_name}'"
            )
        except Exception:
            await ctx.reply("Failed to add entity.")

    elif action == "remove":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor entity remove <name>")
            return
        name = args[1]
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_monitor_entity(name)
            if deleted:
                await ctx.reply(f"\u2705 Deleted entity '{name}'")
            else:
                await ctx.reply(f"Entity '{name}' not found.")
        except Exception:
            await ctx.reply("Failed to delete entity.")

    else:
        await ctx.reply(
            "Usage: /monitor entity list|add|remove"
        )


async def _handle_resource(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor resource subcommands."""
    fmt = ctx.formatter

    if not args or args[0].lower() == "list":
        # /monitor resource list [entity]
        entity_filter = args[1] if len(args) > 1 else None
        try:
            async with get_session() as s:
                repo = Repository(s)
                entity_id = None
                if entity_filter:
                    entity = await repo.get_monitor_entity(entity_filter)
                    if not entity:
                        await ctx.reply(
                            f"Entity '{entity_filter}' not found."
                        )
                        return
                    entity_id = entity.id
                resources = await repo.list_monitor_resources(
                    entity_id=entity_id
                )
            if not resources:
                await ctx.reply(
                    "No resources. Use /monitor resource add "
                    "<entity> <url> <type> [name]"
                )
                return
            lines = [fmt.bold("Resources:"), ""]
            for r in resources:
                last = (
                    r.last_checked_at.strftime("%m-%d %H:%M")
                    if r.last_checked_at
                    else "never"
                )
                lines.append(
                    f"[{r.id}] {fmt.bold(fmt.escape(r.name))} "
                    f"({r.resource_type})"
                )
                lines.append(
                    f"   {fmt.escape(r.url)} (last: {last})"
                )
            await ctx.reply("\n".join(lines), formatted=True)
        except Exception:
            await ctx.reply("Failed to list resources.")
        return

    action = args[0].lower()

    if action == "add":
        # /monitor resource add <entity> <url> <type> [name]
        if len(args) < 4:
            await ctx.reply(
                "Usage: /monitor resource add <entity> <url> <type> [name]\n"
                f"Types: {', '.join(_RESOURCE_TYPES)}"
            )
            return
        entity_name = args[1]
        url = args[2]
        resource_type = args[3]
        if resource_type not in _RESOURCE_TYPES:
            await ctx.reply(
                f"Invalid type '{resource_type}'. "
                f"Valid: {', '.join(_RESOURCE_TYPES)}"
            )
            return
        resource_name = (
            " ".join(args[4:])
            if len(args) > 4
            else f"{entity_name} {resource_type}"
        )
        try:
            async with get_session() as s:
                repo = Repository(s)
                entity = await repo.get_monitor_entity(entity_name)
                if not entity:
                    await ctx.reply(
                        f"Entity '{entity_name}' not found."
                    )
                    return
                await repo.add_monitor_resource(
                    topic_id=entity.topic_id,
                    entity_id=entity.id,
                    name=resource_name,
                    url=url,
                    resource_type=resource_type,
                )
            await ctx.reply(
                f"\u2705 Resource '{resource_name}' added to '{entity_name}'"
            )
        except Exception:
            await ctx.reply("Failed to add resource.")

    elif action == "remove":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor resource remove <id>")
            return
        try:
            resource_id = int(args[1])
        except ValueError:
            await ctx.reply("Resource ID must be a number.")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_monitor_resource(resource_id)
            if deleted:
                await ctx.reply(f"\u2705 Deleted resource #{resource_id}")
            else:
                await ctx.reply(f"Resource #{resource_id} not found.")
        except Exception:
            await ctx.reply("Failed to delete resource.")

    else:
        await ctx.reply(
            "Usage: /monitor resource list|add|remove"
        )


async def _handle_subscribe(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor subscribe <target> <channel_type> [config]."""
    if len(args) < 2:
        await ctx.reply(
            "Usage: /monitor subscribe <target> <channel_type> [config]\n"
            "Channels: telegram, slack\n"
            "Slack requires webhook URL as 3rd arg"
        )
        return

    target_name = args[0]
    channel_type = args[1].lower()

    if channel_type not in ("telegram", "slack"):
        await ctx.reply("Channel must be 'telegram' or 'slack'.")
        return

    # Build config
    if channel_type == "telegram":
        config = json.dumps({"chat_id": ctx.chat_id})
    else:
        if len(args) < 3:
            await ctx.reply(
                "Slack requires webhook URL: "
                "/monitor subscribe <target> slack <webhook_url>"
            )
            return
        config = json.dumps({"webhook_url": args[2]})

    # Resolve target: try topic first, then entity
    try:
        async with get_session() as s:
            repo = Repository(s)
            topic = await repo.get_monitor_topic(target_name)
            if topic:
                await repo.add_monitor_subscriber(
                    channel_type=channel_type,
                    channel_config=config,
                    topic_id=topic.id,
                )
                await ctx.reply(
                    f"\u2705 Subscribed to topic '{target_name}' "
                    f"via {channel_type}"
                )
                return

            entity = await repo.get_monitor_entity(target_name)
            if entity:
                await repo.add_monitor_subscriber(
                    channel_type=channel_type,
                    channel_config=config,
                    entity_id=entity.id,
                )
                await ctx.reply(
                    f"\u2705 Subscribed to entity '{target_name}' "
                    f"via {channel_type}"
                )
                return

        await ctx.reply(
            f"'{target_name}' not found as topic or entity."
        )
    except Exception:
        await ctx.reply("Failed to add subscription.")


async def _handle_check(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor check [topic] [entity]."""
    from megobari.monitor import _format_digest_message, notify_subscribers, run_monitor_check

    topic_name = args[0] if len(args) > 0 else None
    entity_name = args[1] if len(args) > 1 else None

    await ctx.reply("\U0001f50d Running monitor check...")

    try:
        digests = await run_monitor_check(
            topic_name=topic_name,
            entity_name=entity_name,
        )
        label = "Check"
        if topic_name:
            label = f"Check [{topic_name}]"
        message = _format_digest_message(digests, run_label=label)
        await ctx.reply(message, formatted=True)

        if digests:
            await notify_subscribers(digests, run_label=label)
    except Exception:
        logger.exception("Monitor check failed")
        await ctx.reply("Monitor check failed.")


async def _handle_baseline(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor baseline [topic] — generate initial digests."""
    from megobari.monitor import generate_baseline_digests

    topic_name = args[0] if args else None

    await ctx.reply("\U0001f4cb Generating baseline digests...")

    try:
        digests = await generate_baseline_digests(topic_name=topic_name)
        if not digests:
            await ctx.reply("No new baseline digests to generate.")
            return

        # Group by entity
        by_entity: dict[str, list[dict]] = {}
        for d in digests:
            ename = d.get("entity_name", "Unknown")
            by_entity.setdefault(ename, []).append(d)

        fmt = ctx.formatter
        lines = [
            fmt.bold(f"Baseline Digests: {len(digests)} summaries"),
            "",
        ]
        for entity_name, entity_digests in by_entity.items():
            lines.append(f"\U0001f3e2 {fmt.bold(fmt.escape(entity_name))}")
            for d in entity_digests:
                lines.append(
                    f"  \U0001f4cb {d['resource_name']}: "
                    f"{fmt.escape(d['summary'])}"
                )
            lines.append("")

        await ctx.reply("\n".join(lines), formatted=True)
    except Exception:
        logger.exception("Baseline digest generation failed")
        await ctx.reply("Baseline digest generation failed.")


async def _handle_report(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor report [topic] — generate and save a full report."""
    from megobari.monitor import generate_report

    topic_name = args[0] if args else None

    await ctx.reply("\U0001f4ca Generating market intelligence report...")

    try:
        report = await generate_report(topic_name=topic_name)
        # Send first ~3500 chars (Telegram message limit ~4096)
        preview = report[:3500]
        if len(report) > 3500:
            preview += "\n\n... (full report available in dashboard)"
        await ctx.reply(preview)
    except Exception:
        logger.exception("Report generation failed")
        await ctx.reply("Report generation failed.")


async def _handle_digest(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor digest [topic|entity]."""
    fmt = ctx.formatter
    filter_name = args[0] if args else None

    try:
        async with get_session() as s:
            repo = Repository(s)
            topic_id = None
            entity_id = None

            if filter_name:
                topic = await repo.get_monitor_topic(filter_name)
                if topic:
                    topic_id = topic.id
                else:
                    entity = await repo.get_monitor_entity(filter_name)
                    if entity:
                        entity_id = entity.id
                    else:
                        await ctx.reply(
                            f"'{filter_name}' not found as "
                            "topic or entity."
                        )
                        return

            digests = await repo.list_monitor_digests(
                topic_id=topic_id,
                entity_id=entity_id,
                limit=20,
            )

        if not digests:
            await ctx.reply("No digests found.")
            return

        from megobari.monitor import _CHANGE_ICONS

        lines = [fmt.bold("Recent Digests:"), ""]
        for d in digests:
            icon = _CHANGE_ICONS.get(d.change_type, "\U0001f4c4")
            ts = d.created_at.strftime("%m-%d %H:%M")
            lines.append(
                f"{icon} [{ts}] {fmt.code(d.change_type)}: "
                f"{fmt.escape(d.summary)}"
            )
        await ctx.reply("\n".join(lines), formatted=True)
    except Exception:
        await ctx.reply("Failed to load digests.")
