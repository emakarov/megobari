# Website Monitor — Design Document

Date: 2026-02-28

## Purpose

Daily monitoring of websites, blogs, repos, and other resources for companies and people of interest. Grouped by topics (e.g. "Logistics SaaS"). Changes detected via content diffing, summarized by Claude, delivered to subscribers via Telegram and Slack.

## Data Model

### Hierarchy

Topic → Entity → Resource (denormalized FKs at every level)

### Tables

**MonitorTopic**
- `id` (PK), `name` (unique), `description`, `enabled` (bool), `created_at`

**MonitorEntity**
- `id` (PK), `topic_id` (FK)
- `name`, `url` (main site/profile)
- `entity_type`: company | person | organization | product
- `description`, `enabled`, `created_at`

**MonitorResource**
- `id` (PK), `topic_id` (FK), `entity_id` (FK)
- `name`, `url`
- `resource_type`: blog | repo | pricing | jobs | changelog | deals
- `enabled`, `last_checked_at`, `last_changed_at`, `created_at`

**MonitorSnapshot**
- `id` (PK), `topic_id` (FK), `entity_id` (FK), `resource_id` (FK)
- `fetched_at`, `content_hash` (SHA-256), `content_markdown` (full text)
- `has_changes` (bool, compared to previous snapshot)

**MonitorDigest**
- `id` (PK), `topic_id` (FK), `entity_id` (FK), `resource_id` (FK), `snapshot_id` (FK)
- `created_at`, `summary` (Claude-generated), `change_type` (new_post | price_change | new_release | new_job | etc)

**MonitorSubscriber**
- `id` (PK)
- `topic_id` (FK, nullable), `entity_id` (FK, nullable), `resource_id` (FK, nullable)
  - Subscribe at any level: whole topic, single entity, or single resource
- `channel_type`: telegram | slack
- `channel_config` (JSON): `{ "chat_id": 123456 }` or `{ "webhook_url": "https://hooks.slack.com/..." }`
- `enabled`, `created_at`

## Technology

- **Scraping**: Crawl4AI (async, self-hosted, Playwright-based, clean markdown output)
- **Analysis**: Claude via Agent SDK (only called when changes detected)
- **Storage**: SQLite via SQLAlchemy async (existing DB infrastructure)
- **Scheduling**: Existing cron system

## Processing Pipeline

```
Cron trigger (4x daily: morning/noon/afternoon/evening)
  or manual /monitor check
        │
        ▼
For each enabled resource:
  1. Crawl4AI fetch → clean markdown
  2. SHA-256 hash
  3. Compare to last snapshot hash
     ├─ Same → skip, update last_checked_at
     └─ Different → save MonitorSnapshot (has_changes=True)
        │
        ▼ (only changed resources)
  4. Claude summarization:
     - Input: previous markdown + new markdown
     - Prompt: "What changed? Categorize the change"
     - Output: summary + change_type
     - Save as MonitorDigest
        │
        ▼
  5. Notify subscribers:
     - Find matching subscribers (topic/entity/resource level)
     - Group digests per subscriber
     - Push via Telegram bot.send_message / Slack webhook POST
```

### Key behaviors

- Resources checked independently — one failure doesn't block others
- First snapshot is baseline — no notification sent
- No changes across all entities = silent run (no notification)
- Claude only invoked when content hash differs (cost-efficient)

## Schedule

- **Morning** (~08:00)
- **Noon** (~12:00)
- **Afternoon** (~16:00)
- **Evening** (~20:00)
- **By request** — `/monitor check [topic|entity]`

All resources checked on every run. No per-resource frequency configuration.

## Command Interface

```
/monitor                          — overview: list topics with entity counts
/monitor topic list               — list all topics
/monitor topic add <name>         — create topic
/monitor topic remove <name>      — delete topic + cascade

/monitor entity list [topic]      — list entities, optionally filtered by topic
/monitor entity add <topic> <name> <url> [type]  — add entity to topic
/monitor entity remove <name>     — delete entity + cascade

/monitor resource list [entity]   — list resources for entity
/monitor resource add <entity> <url> [type] [name]  — add resource
/monitor resource remove <id>     — delete resource

/monitor subscribe <target> <channel_type> [channel_config]
/monitor check [topic|entity]     — trigger immediate check
/monitor digest [topic|entity]    — show latest digests
```

## Bootstrapping

Two complementary paths:

1. **Claude-assisted discovery**: Tell Claude "add Routific to Logistics SaaS" — Claude finds blog, pricing, changelog, repo URLs and registers them as resources automatically.
2. **Manual management**: Use `/monitor entity add` and `/monitor resource add` commands for fine-grained control. Edit/remove after Claude discovery.

## Notification Format

Grouped digest per subscriber per run:

```
📊 Monitor Digest — Morning

🏷 Logistics SaaS

  🏢 Routific
    📝 Blog: "New post: AI-Powered Route Optimization in 2026"
    💰 Pricing: Free tier removed, starter now $49/mo

  🏢 OptimoRoute
    🔄 Changelog: v4.2 — Added real-time traffic integration
    👥 Jobs: 3 new engineering positions posted

2 of 17 entities had changes
```

## Web Interface

Dashboard reads MonitorDigest / MonitorSnapshot tables directly via existing FastAPI API layer. No subscription model needed for web — it's pull-based.

## Dependencies to Add

- `crawl4ai` — async web crawler with clean markdown output
- Playwright browsers (installed via `crawl4ai-setup`)

## Integration Points

- New handler module: `handlers/monitoring.py`
- New DB models in `db/models.py`
- New Alembic migration
- New repository methods in `db/repository.py`
- New API routes in `api/routes/monitoring.py`
- Cron jobs created on first setup (4x daily schedule)
