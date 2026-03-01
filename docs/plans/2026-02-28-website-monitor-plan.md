# Website Monitor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a website monitoring system that tracks companies/people across multiple resource types (blog, repo, pricing, jobs, changelog, deals), detects changes via content diffing, summarizes with Claude, and notifies subscribers via Telegram/Slack.

**Architecture:** Crawl4AI fetches clean markdown from URLs. Content is hashed and diffed against the previous snapshot. When changes are detected, Claude summarizes the diff. Digests are stored in DB and pushed to subscribers. Four daily scheduled runs + on-demand checks. Data hierarchy: Topic → Entity → Resource.

**Tech Stack:** Crawl4AI (async web scraping), SQLAlchemy async (models), Alembic (migration), existing cron system (scheduling), httpx (Slack webhooks).

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add crawl4ai and httpx to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "python-telegram-bot>=22.0",
    "claude-agent-sdk>=0.1.30",
    "python-dotenv>=1.0.0",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "alembic>=1.18.4",
    "croniter>=6.0",
    "crawl4ai>=0.6",
    "httpx>=0.27",
]
```

**Step 2: Install dependencies**

Run: `uv sync`
Expected: Successful installation

**Step 3: Verify crawl4ai setup**

Run: `uv run crawl4ai-setup`
Expected: Playwright browsers installed

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(monitor): add crawl4ai and httpx dependencies"
```

---

### Task 2: Add database models

**Files:**
- Modify: `src/megobari/db/models.py`
- Modify: `src/megobari/db/__init__.py`

**Step 1: Write the models in `db/models.py`**

Add these models at the end of the file, after the existing models:

```python
class MonitorTopic(Base):
    """Group of monitored entities (e.g. 'Logistics SaaS')."""

    __tablename__ = "monitor_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    entities: Mapped[list[MonitorEntity]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return f"<MonitorTopic name={self.name!r}>"


class MonitorEntity(Base):
    """A company, person, or organization being monitored."""

    __tablename__ = "monitor_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_topics.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50), default="company")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("topic_id", "name", name="uq_entity_topic_name"),
    )

    topic: Mapped[MonitorTopic] = relationship(back_populates="entities")
    resources: Mapped[list[MonitorResource]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return f"<MonitorEntity name={self.name!r} type={self.entity_type!r}>"


class MonitorResource(Base):
    """A specific URL to monitor for an entity (blog, repo, pricing page, etc)."""

    __tablename__ = "monitor_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_topics.id"), nullable=False)
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitor_entities.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    entity: Mapped[MonitorEntity] = relationship(back_populates="resources")

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return f"<MonitorResource name={self.name!r} type={self.resource_type!r}>"


class MonitorSnapshot(Base):
    """A single fetch result for a resource — stores content and change detection."""

    __tablename__ = "monitor_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_topics.id"), nullable=False)
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitor_entities.id"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitor_resources.id"), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    has_changes: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return f"<MonitorSnapshot resource_id={self.resource_id} changed={self.has_changes}>"


class MonitorDigest(Base):
    """AI-generated summary of changes detected in a snapshot."""

    __tablename__ = "monitor_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_topics.id"), nullable=False)
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitor_entities.id"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitor_resources.id"), nullable=False
    )
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitor_snapshots.id"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return f"<MonitorDigest resource_id={self.resource_id} type={self.change_type!r}>"


class MonitorSubscriber(Base):
    """Subscriber for monitor notifications — push to Telegram or Slack."""

    __tablename__ = "monitor_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("monitor_topics.id"), nullable=True
    )
    entity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("monitor_entities.id"), nullable=True
    )
    resource_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("monitor_resources.id"), nullable=True
    )
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_config: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return f"<MonitorSubscriber channel={self.channel_type!r}>"
```

**Step 2: Export new models from `db/__init__.py`**

Add to imports:

```python
from megobari.db.models import (
    # ... existing imports ...
    MonitorCompany,  # renamed from Entity in code
    MonitorDigest,
    MonitorEntity,
    MonitorResource,
    MonitorSnapshot,
    MonitorSubscriber,
    MonitorTopic,
)
```

Add to `__all__`:

```python
"MonitorDigest",
"MonitorEntity",
"MonitorResource",
"MonitorSnapshot",
"MonitorSubscriber",
"MonitorTopic",
```

**Step 3: Run linting**

Run: `uv run flake8 src/megobari/db/models.py src/megobari/db/__init__.py`
Expected: No errors

**Step 4: Commit**

```bash
git add src/megobari/db/models.py src/megobari/db/__init__.py
git commit -m "feat(monitor): add database models for website monitoring"
```

---

### Task 3: Create Alembic migration

**Files:**
- Create: `src/megobari/db/migrations/versions/2026_02_28_<rev>_add_monitor_tables.py`

**Step 1: Generate migration**

Run: `cd /Users/em/dev/megobari && uv run alembic revision --autogenerate -m "add monitor tables"`
Expected: New migration file created

**Step 2: Inspect the generated migration**

Read the generated file. Verify it creates all 6 tables: `monitor_topics`, `monitor_entities`, `monitor_resources`, `monitor_snapshots`, `monitor_digests`, `monitor_subscribers` with correct columns, foreign keys, and constraints.

**Step 3: Run migration**

Run: `uv run alembic upgrade head`
Expected: Tables created successfully

**Step 4: Run isort on the migration file**

Run: `uv run isort src/megobari/db/migrations/versions/2026_02_28_*_add_monitor_tables.py`

**Step 5: Commit**

```bash
git add src/megobari/db/migrations/versions/
git commit -m "feat(monitor): add alembic migration for monitor tables"
```

---

### Task 4: Add repository methods — topics and entities

**Files:**
- Modify: `src/megobari/db/repository.py`
- Test: `tests/test_db.py`

**Step 1: Write failing tests for topics CRUD**

Add to `tests/test_db.py`:

```python
# ---------------------------------------------------------------
# Monitor Topics
# ---------------------------------------------------------------

async def test_add_monitor_topic():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Logistics SaaS", description="Route optimization companies")
    assert topic.id is not None
    assert topic.name == "Logistics SaaS"


async def test_list_monitor_topics():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic(name="A")
        await repo.add_monitor_topic(name="B")

    async with get_session() as s:
        repo = Repository(s)
        topics = await repo.list_monitor_topics()
    assert len(topics) == 2


async def test_get_monitor_topic():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic(name="Test")

    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.get_monitor_topic("Test")
    assert topic is not None
    assert topic.name == "Test"


async def test_delete_monitor_topic():
    async with get_session() as s:
        repo = Repository(s)
        await repo.add_monitor_topic(name="Del")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_topic("Del")
    assert deleted is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -k "monitor_topic" -v`
Expected: FAIL — methods don't exist yet

**Step 3: Write failing tests for entities CRUD**

```python
# ---------------------------------------------------------------
# Monitor Entities
# ---------------------------------------------------------------

async def test_add_monitor_entity():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Logistics")
        entity = await repo.add_monitor_entity(
            topic_id=topic.id, name="Routific", url="https://routific.com",
            entity_type="company",
        )
    assert entity.id is not None
    assert entity.topic_id == topic.id


async def test_list_monitor_entities():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Logistics")
        await repo.add_monitor_entity(topic_id=topic.id, name="A")
        await repo.add_monitor_entity(topic_id=topic.id, name="B")

    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities(topic_id=topic.id)
    assert len(entities) == 2


async def test_delete_monitor_entity():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Logistics")
        await repo.add_monitor_entity(topic_id=topic.id, name="Del")

    async with get_session() as s:
        repo = Repository(s)
        deleted = await repo.delete_monitor_entity("Del")
    assert deleted is True
```

**Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -k "monitor_entity" -v`
Expected: FAIL

**Step 5: Implement repository methods**

Add to `Repository` class in `db/repository.py`:

```python
    # -- Monitor Topics --

    async def add_monitor_topic(
        self, name: str, description: str | None = None,
    ) -> MonitorTopic:
        """Create a new monitor topic."""
        topic = MonitorTopic(name=name, description=description)
        self.session.add(topic)
        await self.session.flush()
        return topic

    async def list_monitor_topics(self, enabled_only: bool = False) -> list[MonitorTopic]:
        """List all monitor topics."""
        stmt = select(MonitorTopic).order_by(MonitorTopic.created_at.asc())
        if enabled_only:
            stmt = stmt.where(MonitorTopic.enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_monitor_topic(self, name: str) -> MonitorTopic | None:
        """Get a monitor topic by name."""
        stmt = select(MonitorTopic).where(MonitorTopic.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_monitor_topic(self, name: str) -> bool:
        """Delete a monitor topic by name (cascades to entities/resources)."""
        topic = await self.get_monitor_topic(name)
        if topic is None:
            return False
        await self.session.delete(topic)
        await self.session.flush()
        return True

    # -- Monitor Entities --

    async def add_monitor_entity(
        self,
        topic_id: int,
        name: str,
        url: str | None = None,
        entity_type: str = "company",
        description: str | None = None,
    ) -> MonitorEntity:
        """Create a new monitor entity within a topic."""
        entity = MonitorEntity(
            topic_id=topic_id, name=name, url=url,
            entity_type=entity_type, description=description,
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def list_monitor_entities(
        self, topic_id: int | None = None, enabled_only: bool = False,
    ) -> list[MonitorEntity]:
        """List monitor entities, optionally filtered by topic."""
        stmt = select(MonitorEntity).order_by(MonitorEntity.name.asc())
        if topic_id is not None:
            stmt = stmt.where(MonitorEntity.topic_id == topic_id)
        if enabled_only:
            stmt = stmt.where(MonitorEntity.enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_monitor_entity(self, name: str) -> MonitorEntity | None:
        """Get a monitor entity by name."""
        stmt = select(MonitorEntity).where(MonitorEntity.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_monitor_entity(self, name: str) -> bool:
        """Delete a monitor entity by name (cascades to resources)."""
        entity = await self.get_monitor_entity(name)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True
```

Add the necessary imports at the top of `repository.py`:

```python
from megobari.db.models import MonitorTopic, MonitorEntity
```

**Step 6: Run tests**

Run: `uv run pytest tests/test_db.py -k "monitor" -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/megobari/db/repository.py tests/test_db.py
git commit -m "feat(monitor): add repository methods for topics and entities"
```

---

### Task 5: Add repository methods — resources, snapshots, digests, subscribers

**Files:**
- Modify: `src/megobari/db/repository.py`
- Test: `tests/test_db.py`

**Step 1: Write failing tests for resources**

```python
# ---------------------------------------------------------------
# Monitor Resources
# ---------------------------------------------------------------

async def test_add_monitor_resource():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Logistics")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="Routific")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Routific Blog", url="https://routific.com/blog",
            resource_type="blog",
        )
    assert resource.id is not None
    assert resource.resource_type == "blog"


async def test_list_monitor_resources():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="Logistics")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="R")
        await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://r.com/blog", resource_type="blog",
        )
        await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Pricing", url="https://r.com/pricing", resource_type="pricing",
        )

    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(entity_id=entity.id)
    assert len(resources) == 2
```

**Step 2: Write failing tests for snapshots**

```python
# ---------------------------------------------------------------
# Monitor Snapshots
# ---------------------------------------------------------------

async def test_add_monitor_snapshot():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://e.com/blog", resource_type="blog",
        )
        snap = await repo.add_monitor_snapshot(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            content_hash="abc123", content_markdown="# Hello",
            has_changes=False,
        )
    assert snap.id is not None


async def test_get_latest_snapshot():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://e.com/blog", resource_type="blog",
        )
        await repo.add_monitor_snapshot(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            content_hash="first", content_markdown="old", has_changes=False,
        )
        await repo.add_monitor_snapshot(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            content_hash="second", content_markdown="new", has_changes=True,
        )

    async with get_session() as s:
        repo = Repository(s)
        latest = await repo.get_latest_monitor_snapshot(resource.id)
    assert latest is not None
    assert latest.content_hash == "second"
```

**Step 3: Write failing tests for digests and subscribers**

```python
# ---------------------------------------------------------------
# Monitor Digests
# ---------------------------------------------------------------

async def test_add_monitor_digest():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://e.com/blog", resource_type="blog",
        )
        snap = await repo.add_monitor_snapshot(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            content_hash="abc", content_markdown="text", has_changes=True,
        )
        digest = await repo.add_monitor_digest(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            snapshot_id=snap.id, summary="New blog post about X", change_type="new_post",
        )
    assert digest.id is not None
    assert digest.change_type == "new_post"


async def test_list_monitor_digests():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://e.com/blog", resource_type="blog",
        )
        snap = await repo.add_monitor_snapshot(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            content_hash="abc", content_markdown="text", has_changes=True,
        )
        await repo.add_monitor_digest(
            topic_id=topic.id, entity_id=entity.id, resource_id=resource.id,
            snapshot_id=snap.id, summary="Post 1", change_type="new_post",
        )

    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests(topic_id=topic.id)
    assert len(digests) == 1


# ---------------------------------------------------------------
# Monitor Subscribers
# ---------------------------------------------------------------

async def test_add_monitor_subscriber():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        sub = await repo.add_monitor_subscriber(
            topic_id=topic.id, channel_type="telegram",
            channel_config='{"chat_id": 123}',
        )
    assert sub.id is not None
    assert sub.channel_type == "telegram"


async def test_list_monitor_subscribers_for_topic():
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        await repo.add_monitor_subscriber(
            topic_id=topic.id, channel_type="telegram",
            channel_config='{"chat_id": 123}',
        )

    async with get_session() as s:
        repo = Repository(s)
        subs = await repo.list_monitor_subscribers(topic_id=topic.id)
    assert len(subs) == 1
```

**Step 4: Run all monitor tests to verify they fail**

Run: `uv run pytest tests/test_db.py -k "monitor" -v`
Expected: FAIL on all new tests

**Step 5: Implement repository methods**

Add to `Repository` class in `db/repository.py`:

```python
    # -- Monitor Resources --

    async def add_monitor_resource(
        self,
        topic_id: int,
        entity_id: int,
        name: str,
        url: str,
        resource_type: str,
    ) -> MonitorResource:
        """Create a new monitor resource."""
        resource = MonitorResource(
            topic_id=topic_id, entity_id=entity_id,
            name=name, url=url, resource_type=resource_type,
        )
        self.session.add(resource)
        await self.session.flush()
        return resource

    async def list_monitor_resources(
        self,
        entity_id: int | None = None,
        topic_id: int | None = None,
        enabled_only: bool = False,
    ) -> list[MonitorResource]:
        """List monitor resources, optionally filtered."""
        stmt = select(MonitorResource).order_by(MonitorResource.name.asc())
        if entity_id is not None:
            stmt = stmt.where(MonitorResource.entity_id == entity_id)
        if topic_id is not None:
            stmt = stmt.where(MonitorResource.topic_id == topic_id)
        if enabled_only:
            stmt = stmt.where(MonitorResource.enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_monitor_resource(self, resource_id: int) -> bool:
        """Delete a monitor resource by ID."""
        stmt = select(MonitorResource).where(MonitorResource.id == resource_id)
        result = await self.session.execute(stmt)
        resource = result.scalar_one_or_none()
        if resource is None:
            return False
        await self.session.delete(resource)
        await self.session.flush()
        return True

    async def update_monitor_resource_checked(self, resource_id: int, changed: bool = False) -> None:
        """Update last_checked_at (and last_changed_at if changed) for a resource."""
        now = _utcnow()
        values: dict = {"last_checked_at": now}
        if changed:
            values["last_changed_at"] = now
        stmt = (
            update(MonitorResource)
            .where(MonitorResource.id == resource_id)
            .values(**values)
        )
        await self.session.execute(stmt)

    # -- Monitor Snapshots --

    async def add_monitor_snapshot(
        self,
        topic_id: int,
        entity_id: int,
        resource_id: int,
        content_hash: str,
        content_markdown: str,
        has_changes: bool = False,
    ) -> MonitorSnapshot:
        """Create a new snapshot for a resource."""
        snap = MonitorSnapshot(
            topic_id=topic_id, entity_id=entity_id, resource_id=resource_id,
            content_hash=content_hash, content_markdown=content_markdown,
            has_changes=has_changes,
        )
        self.session.add(snap)
        await self.session.flush()
        return snap

    async def get_latest_monitor_snapshot(self, resource_id: int) -> MonitorSnapshot | None:
        """Get the most recent snapshot for a resource."""
        stmt = (
            select(MonitorSnapshot)
            .where(MonitorSnapshot.resource_id == resource_id)
            .order_by(MonitorSnapshot.fetched_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # -- Monitor Digests --

    async def add_monitor_digest(
        self,
        topic_id: int,
        entity_id: int,
        resource_id: int,
        snapshot_id: int,
        summary: str,
        change_type: str,
    ) -> MonitorDigest:
        """Create a new digest entry."""
        digest = MonitorDigest(
            topic_id=topic_id, entity_id=entity_id, resource_id=resource_id,
            snapshot_id=snapshot_id, summary=summary, change_type=change_type,
        )
        self.session.add(digest)
        await self.session.flush()
        return digest

    async def list_monitor_digests(
        self,
        topic_id: int | None = None,
        entity_id: int | None = None,
        resource_id: int | None = None,
        limit: int = 50,
    ) -> list[MonitorDigest]:
        """List monitor digests, optionally filtered. Most recent first."""
        stmt = select(MonitorDigest).order_by(MonitorDigest.created_at.desc()).limit(limit)
        if topic_id is not None:
            stmt = stmt.where(MonitorDigest.topic_id == topic_id)
        if entity_id is not None:
            stmt = stmt.where(MonitorDigest.entity_id == entity_id)
        if resource_id is not None:
            stmt = stmt.where(MonitorDigest.resource_id == resource_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # -- Monitor Subscribers --

    async def add_monitor_subscriber(
        self,
        channel_type: str,
        channel_config: str,
        topic_id: int | None = None,
        entity_id: int | None = None,
        resource_id: int | None = None,
    ) -> MonitorSubscriber:
        """Create a new monitor subscriber."""
        sub = MonitorSubscriber(
            topic_id=topic_id, entity_id=entity_id, resource_id=resource_id,
            channel_type=channel_type, channel_config=channel_config,
        )
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def list_monitor_subscribers(
        self,
        topic_id: int | None = None,
        entity_id: int | None = None,
        resource_id: int | None = None,
    ) -> list[MonitorSubscriber]:
        """List subscribers matching a scope (topic/entity/resource)."""
        stmt = select(MonitorSubscriber).where(MonitorSubscriber.enabled.is_(True))
        conditions = []
        if topic_id is not None:
            conditions.append(MonitorSubscriber.topic_id == topic_id)
        if entity_id is not None:
            conditions.append(MonitorSubscriber.entity_id == entity_id)
        if resource_id is not None:
            conditions.append(MonitorSubscriber.resource_id == resource_id)
        if conditions:
            stmt = stmt.where(sa.or_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_monitor_subscriber(self, subscriber_id: int) -> bool:
        """Delete a subscriber by ID."""
        stmt = select(MonitorSubscriber).where(MonitorSubscriber.id == subscriber_id)
        result = await self.session.execute(stmt)
        sub = result.scalar_one_or_none()
        if sub is None:
            return False
        await self.session.delete(sub)
        await self.session.flush()
        return True
```

Add imports at top of `repository.py`:

```python
from megobari.db.models import (
    MonitorResource, MonitorSnapshot, MonitorDigest, MonitorSubscriber,
)
import sqlalchemy as sa
```

**Step 6: Run all monitor tests**

Run: `uv run pytest tests/test_db.py -k "monitor" -v`
Expected: All PASS

**Step 7: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

**Step 8: Commit**

```bash
git add src/megobari/db/repository.py tests/test_db.py
git commit -m "feat(monitor): add repository methods for resources, snapshots, digests, subscribers"
```

---

### Task 6: Build the monitor engine (scraping + diffing + summarization)

**Files:**
- Create: `src/megobari/monitor.py`
- Test: `tests/test_monitor.py`

**Step 1: Write failing tests for the monitor engine**

Create `tests/test_monitor.py`:

```python
"""Tests for the website monitor engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from megobari.db import Repository, close_db, get_session, init_db
from megobari.monitor import compute_content_hash, check_resource, run_monitor_check


@pytest.fixture(autouse=True)
async def db():
    """Create an in-memory SQLite DB for each test."""
    await init_db("sqlite+aiosqlite://")
    yield
    await close_db()


def test_compute_content_hash():
    assert compute_content_hash("hello") == compute_content_hash("hello")
    assert compute_content_hash("hello") != compute_content_hash("world")


async def test_check_resource_first_snapshot():
    """First check should create a baseline snapshot with no changes."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://example.com/blog", resource_type="blog",
        )
        resource_id = resource.id

    with patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "# Welcome to our blog"
        result = await check_resource(resource_id)

    assert result is not None
    assert result["has_changes"] is False
    assert result["is_baseline"] is True


async def test_check_resource_no_change():
    """Second check with same content should report no changes."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://example.com/blog", resource_type="blog",
        )
        resource_id = resource.id

    with patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "# Same content"
        await check_resource(resource_id)  # baseline
        result = await check_resource(resource_id)  # second check

    assert result is not None
    assert result["has_changes"] is False
    assert result["is_baseline"] is False


async def test_check_resource_with_change():
    """Changed content should be detected and flagged."""
    async with get_session() as s:
        repo = Repository(s)
        topic = await repo.add_monitor_topic(name="T")
        entity = await repo.add_monitor_entity(topic_id=topic.id, name="E")
        resource = await repo.add_monitor_resource(
            topic_id=topic.id, entity_id=entity.id,
            name="Blog", url="https://example.com/blog", resource_type="blog",
        )
        resource_id = resource.id

    with patch("megobari.monitor.fetch_url_markdown", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "# Old content"
        await check_resource(resource_id)  # baseline

        mock_fetch.return_value = "# New content with new post"
        result = await check_resource(resource_id)  # changed!

    assert result is not None
    assert result["has_changes"] is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_monitor.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement the monitor engine**

Create `src/megobari/monitor.py`:

```python
"""Website monitor engine — fetch, diff, summarize, notify."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx

from megobari.db import Repository, get_session

logger = logging.getLogger(__name__)


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


async def fetch_url_markdown(url: str) -> str:
    """Fetch a URL and return clean markdown using Crawl4AI."""
    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown or ""


async def check_resource(resource_id: int) -> dict[str, Any] | None:
    """Check a single resource for changes.

    Returns a dict with check results, or None if the resource doesn't exist.
    Keys: has_changes, is_baseline, resource_id, content_hash, snapshot_id
    """
    async with get_session() as s:
        repo = Repository(s)
        from megobari.db.models import MonitorResource
        from sqlalchemy import select

        stmt = select(MonitorResource).where(MonitorResource.id == resource_id)
        result = await s.execute(stmt)
        resource = result.scalar_one_or_none()
        if resource is None:
            return None

        topic_id = resource.topic_id
        entity_id = resource.entity_id
        url = resource.url

        # Fetch content
        try:
            markdown = await fetch_url_markdown(url)
        except Exception:
            logger.warning("Failed to fetch %s", url, exc_info=True)
            return None

        content_hash = compute_content_hash(markdown)

        # Get previous snapshot
        prev = await repo.get_latest_monitor_snapshot(resource_id)
        is_baseline = prev is None
        has_changes = not is_baseline and prev.content_hash != content_hash

        # Save snapshot
        snap = await repo.add_monitor_snapshot(
            topic_id=topic_id,
            entity_id=entity_id,
            resource_id=resource_id,
            content_hash=content_hash,
            content_markdown=markdown,
            has_changes=has_changes,
        )

        # Update resource timestamps
        await repo.update_monitor_resource_checked(resource_id, changed=has_changes)

    return {
        "resource_id": resource_id,
        "has_changes": has_changes,
        "is_baseline": is_baseline,
        "content_hash": content_hash,
        "snapshot_id": snap.id,
        "topic_id": topic_id,
        "entity_id": entity_id,
    }


async def summarize_changes(
    resource_id: int,
    snapshot_id: int,
    previous_markdown: str,
    new_markdown: str,
    resource_name: str,
    resource_type: str,
) -> dict[str, str] | None:
    """Use Claude to summarize what changed between two snapshots.

    Returns dict with 'summary' and 'change_type', or None on failure.
    """
    from megobari.claude_bridge import send_to_claude
    from megobari.session import Session

    prompt = (
        f"Compare these two versions of a {resource_type} page for '{resource_name}'. "
        "Summarize what changed in 1-2 concise sentences. "
        "Also classify the change as one of: new_post, price_change, new_release, "
        "new_job, new_deal, content_update, new_feature.\n\n"
        "Respond ONLY with JSON: {\"summary\": \"...\", \"change_type\": \"...\"}\n\n"
        f"=== PREVIOUS VERSION ===\n{previous_markdown[:4000]}\n\n"
        f"=== NEW VERSION ===\n{new_markdown[:4000]}"
    )

    session = Session(name="monitor:summarize", cwd="/tmp")
    try:
        response, _, _, _ = await send_to_claude(prompt=prompt, session=session)
        data = json.loads(response)
        return {"summary": data["summary"], "change_type": data["change_type"]}
    except Exception:
        logger.warning("Failed to summarize changes for resource %d", resource_id, exc_info=True)
        return None


async def run_monitor_check(
    topic_name: str | None = None,
    entity_name: str | None = None,
) -> list[dict[str, Any]]:
    """Run monitor checks for all enabled resources, optionally filtered.

    Returns list of dicts with digest info for changed resources.
    """
    digests: list[dict[str, Any]] = []

    async with get_session() as s:
        repo = Repository(s)

        # Resolve filter
        topic_id = None
        entity_id = None
        if topic_name:
            topic = await repo.get_monitor_topic(topic_name)
            if topic:
                topic_id = topic.id
        if entity_name:
            entity = await repo.get_monitor_entity(entity_name)
            if entity:
                entity_id = entity.id

        resources = await repo.list_monitor_resources(
            topic_id=topic_id,
            enabled_only=True,
        )
        if entity_id:
            resources = [r for r in resources if r.entity_id == entity_id]

    # Check each resource independently
    for resource in resources:
        try:
            result = await check_resource(resource.id)
            if result is None:
                continue

            if result["is_baseline"]:
                logger.info("Baseline snapshot for resource %d (%s)", resource.id, resource.name)
                continue

            if not result["has_changes"]:
                continue

            # Get previous and current markdown for summarization
            async with get_session() as s:
                repo = Repository(s)
                from megobari.db.models import MonitorSnapshot
                from sqlalchemy import select

                stmt = (
                    select(MonitorSnapshot)
                    .where(MonitorSnapshot.resource_id == resource.id)
                    .order_by(MonitorSnapshot.fetched_at.desc())
                    .limit(2)
                )
                res = await s.execute(stmt)
                snaps = list(res.scalars().all())

            if len(snaps) < 2:
                continue

            new_snap, prev_snap = snaps[0], snaps[1]

            # Summarize with Claude
            summary_result = await summarize_changes(
                resource_id=resource.id,
                snapshot_id=new_snap.id,
                previous_markdown=prev_snap.content_markdown,
                new_markdown=new_snap.content_markdown,
                resource_name=resource.name,
                resource_type=resource.resource_type,
            )

            if summary_result:
                # Save digest
                async with get_session() as s:
                    repo = Repository(s)
                    digest = await repo.add_monitor_digest(
                        topic_id=result["topic_id"],
                        entity_id=result["entity_id"],
                        resource_id=resource.id,
                        snapshot_id=new_snap.id,
                        summary=summary_result["summary"],
                        change_type=summary_result["change_type"],
                    )
                    digests.append({
                        "resource_name": resource.name,
                        "entity_id": result["entity_id"],
                        "topic_id": result["topic_id"],
                        "summary": summary_result["summary"],
                        "change_type": summary_result["change_type"],
                        "digest_id": digest.id,
                    })

        except Exception:
            logger.warning("Failed to check resource %d", resource.id, exc_info=True)

    return digests


async def notify_subscribers(digests: list[dict[str, Any]], run_label: str = "Check") -> None:
    """Send digest notifications to matching subscribers."""
    if not digests:
        return

    # Group digests by topic_id for subscriber matching
    topic_ids = {d["topic_id"] for d in digests}

    async with get_session() as s:
        repo = Repository(s)
        for topic_id in topic_ids:
            subs = await repo.list_monitor_subscribers(topic_id=topic_id)
            topic_digests = [d for d in digests if d["topic_id"] == topic_id]

            for sub in subs:
                try:
                    config = json.loads(sub.channel_config)
                    message = _format_digest_message(topic_digests, run_label)

                    if sub.channel_type == "telegram":
                        # Telegram notification is handled by caller (needs bot instance)
                        logger.info(
                            "Telegram notification for chat %s: %d changes",
                            config.get("chat_id"), len(topic_digests),
                        )
                    elif sub.channel_type == "slack":
                        await _send_slack_webhook(config["webhook_url"], message)
                except Exception:
                    logger.warning(
                        "Failed to notify subscriber %d", sub.id, exc_info=True,
                    )


def _format_digest_message(digests: list[dict[str, Any]], run_label: str) -> str:
    """Format digest entries into a readable message."""
    lines = [f"\U0001f4ca Monitor Digest — {run_label}", ""]
    for d in digests:
        icon = {
            "new_post": "\U0001f4dd",
            "price_change": "\U0001f4b0",
            "new_release": "\U0001f504",
            "new_job": "\U0001f465",
            "new_deal": "\U0001f91d",
            "content_update": "\U0001f4c4",
            "new_feature": "\u2728",
        }.get(d["change_type"], "\U0001f50d")
        lines.append(f"  {icon} {d['resource_name']}: {d['summary']}")
    lines.append(f"\n{len(digests)} change(s) detected")
    return "\n".join(lines)


async def _send_slack_webhook(webhook_url: str, message: str) -> None:
    """Post a message to a Slack webhook."""
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json={"text": message}, timeout=10)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_monitor.py -v`
Expected: All PASS

**Step 5: Run linting**

Run: `uv run flake8 src/megobari/monitor.py tests/test_monitor.py`
Expected: No errors

**Step 6: Commit**

```bash
git add src/megobari/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): add monitor engine — fetch, diff, summarize, notify"
```

---

### Task 7: Add /monitor handler

**Files:**
- Create: `src/megobari/handlers/monitoring.py`
- Modify: `src/megobari/handlers/__init__.py`
- Modify: `src/megobari/bot.py`

**Step 1: Create the handler module**

Create `src/megobari/handlers/monitoring.py`:

```python
"""Website monitor command handlers."""

from __future__ import annotations

import asyncio
import json
import logging

from megobari.db import Repository, get_session
from megobari.transport import TransportContext

logger = logging.getLogger(__name__)


async def cmd_monitor(ctx: TransportContext) -> None:
    """Handle /monitor command: manage website monitoring."""
    fmt = ctx.formatter
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
    elif sub == "digest":
        await _handle_digest(ctx, args[1:])
    else:
        await ctx.reply(
            "Usage:\n"
            "/monitor — overview\n"
            "/monitor topic list|add|remove\n"
            "/monitor entity list|add|remove [topic]\n"
            "/monitor resource list|add|remove [entity]\n"
            "/monitor subscribe <target> <channel> [config]\n"
            "/monitor check [topic|entity]\n"
            "/monitor digest [topic|entity]",
        )


async def _show_overview(ctx: TransportContext) -> None:
    """Show overview of all topics with entity counts."""
    fmt = ctx.formatter
    try:
        async with get_session() as s:
            repo = Repository(s)
            topics = await repo.list_monitor_topics()
            if not topics:
                await ctx.reply("No monitor topics. Use /monitor topic add <name>")
                return
            lines = [fmt.bold("Monitor Topics:"), ""]
            for t in topics:
                entities = await repo.list_monitor_entities(topic_id=t.id)
                total_resources = 0
                for e in entities:
                    resources = await repo.list_monitor_resources(entity_id=e.id)
                    total_resources += len(resources)
                state = "\u2705" if t.enabled else "\u23f8"
                lines.append(
                    f"{state} {fmt.bold(fmt.escape(t.name))}: "
                    f"{len(entities)} entities, {total_resources} resources"
                )
    except Exception:
        await ctx.reply("Failed to load monitor data.")
        return
    await ctx.reply("\n".join(lines), formatted=True)


async def _handle_topic(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor topic subcommands."""
    fmt = ctx.formatter
    if not args or args[0] == "list":
        await _show_overview(ctx)
        return

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor topic add <name> [description]")
            return
        name = args[1]
        desc = " ".join(args[2:]) if len(args) > 2 else None
        try:
            async with get_session() as s:
                repo = Repository(s)
                existing = await repo.get_monitor_topic(name)
                if existing:
                    await ctx.reply(f"Topic '{name}' already exists.")
                    return
                await repo.add_monitor_topic(name=name, description=desc)
            await ctx.reply(f"\u2705 Topic '{name}' created")
        except Exception:
            await ctx.reply("Failed to create topic.")

    elif sub == "remove":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor topic remove <name>")
            return
        name = args[1]
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_monitor_topic(name)
            if deleted:
                await ctx.reply(f"\u2705 Deleted topic '{name}' and all its entities/resources")
            else:
                await ctx.reply(f"Topic '{name}' not found.")
        except Exception:
            await ctx.reply("Failed to delete topic.")


async def _handle_entity(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor entity subcommands."""
    fmt = ctx.formatter
    if not args or args[0] == "list":
        # List entities, optionally filtered by topic
        topic_name = args[1] if len(args) > 1 else None
        try:
            async with get_session() as s:
                repo = Repository(s)
                topic_id = None
                if topic_name:
                    topic = await repo.get_monitor_topic(topic_name)
                    if not topic:
                        await ctx.reply(f"Topic '{topic_name}' not found.")
                        return
                    topic_id = topic.id
                entities = await repo.list_monitor_entities(topic_id=topic_id)
            if not entities:
                await ctx.reply("No entities found.")
                return
            lines = [fmt.bold("Entities:"), ""]
            for e in entities:
                state = "\u2705" if e.enabled else "\u23f8"
                lines.append(f"{state} {fmt.bold(fmt.escape(e.name))} ({e.entity_type})")
                if e.url:
                    lines.append(f"   {e.url}")
            await ctx.reply("\n".join(lines), formatted=True)
        except Exception:
            await ctx.reply("Failed to list entities.")
        return

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 4:
            await ctx.reply(
                "Usage: /monitor entity add <topic> <name> <url> [type]\n"
                "Types: company, person, organization, product"
            )
            return
        topic_name, name, url = args[1], args[2], args[3]
        entity_type = args[4] if len(args) > 4 else "company"
        try:
            async with get_session() as s:
                repo = Repository(s)
                topic = await repo.get_monitor_topic(topic_name)
                if not topic:
                    await ctx.reply(f"Topic '{topic_name}' not found.")
                    return
                await repo.add_monitor_entity(
                    topic_id=topic.id, name=name, url=url, entity_type=entity_type,
                )
            await ctx.reply(f"\u2705 Entity '{name}' added to '{topic_name}'")
        except Exception:
            await ctx.reply("Failed to add entity.")

    elif sub == "remove":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor entity remove <name>")
            return
        try:
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_monitor_entity(args[1])
            if deleted:
                await ctx.reply(f"\u2705 Deleted entity '{args[1]}' and all its resources")
            else:
                await ctx.reply(f"Entity '{args[1]}' not found.")
        except Exception:
            await ctx.reply("Failed to delete entity.")


async def _handle_resource(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor resource subcommands."""
    fmt = ctx.formatter
    if not args or args[0] == "list":
        entity_name = args[1] if len(args) > 1 else None
        try:
            async with get_session() as s:
                repo = Repository(s)
                entity_id = None
                if entity_name:
                    entity = await repo.get_monitor_entity(entity_name)
                    if not entity:
                        await ctx.reply(f"Entity '{entity_name}' not found.")
                        return
                    entity_id = entity.id
                resources = await repo.list_monitor_resources(entity_id=entity_id)
            if not resources:
                await ctx.reply("No resources found.")
                return
            lines = [fmt.bold("Resources:"), ""]
            for r in resources:
                state = "\u2705" if r.enabled else "\u23f8"
                last = r.last_checked_at.strftime("%m-%d %H:%M") if r.last_checked_at else "never"
                lines.append(f"{state} [{r.resource_type}] {fmt.bold(fmt.escape(r.name))} (last: {last})")
                lines.append(f"   {r.url}")
            await ctx.reply("\n".join(lines), formatted=True)
        except Exception:
            await ctx.reply("Failed to list resources.")
        return

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 4:
            await ctx.reply(
                "Usage: /monitor resource add <entity> <url> <type> [name]\n"
                "Types: blog, repo, pricing, jobs, changelog, deals"
            )
            return
        entity_name, url, rtype = args[1], args[2], args[3]
        name = args[4] if len(args) > 4 else f"{entity_name} {rtype}"
        try:
            async with get_session() as s:
                repo = Repository(s)
                entity = await repo.get_monitor_entity(entity_name)
                if not entity:
                    await ctx.reply(f"Entity '{entity_name}' not found.")
                    return
                await repo.add_monitor_resource(
                    topic_id=entity.topic_id, entity_id=entity.id,
                    name=name, url=url, resource_type=rtype,
                )
            await ctx.reply(f"\u2705 Resource '{name}' added to '{entity_name}'")
        except Exception:
            await ctx.reply("Failed to add resource.")

    elif sub == "remove":
        if len(args) < 2:
            await ctx.reply("Usage: /monitor resource remove <id>")
            return
        try:
            rid = int(args[1])
            async with get_session() as s:
                repo = Repository(s)
                deleted = await repo.delete_monitor_resource(rid)
            if deleted:
                await ctx.reply(f"\u2705 Deleted resource #{rid}")
            else:
                await ctx.reply(f"Resource #{rid} not found.")
        except ValueError:
            await ctx.reply("Resource ID must be a number.")
        except Exception:
            await ctx.reply("Failed to delete resource.")


async def _handle_subscribe(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor subscribe subcommands."""
    if len(args) < 2:
        await ctx.reply(
            "Usage: /monitor subscribe <target> <channel_type> [config]\n"
            "Examples:\n"
            '  /monitor subscribe "Logistics SaaS" telegram\n'
            "  /monitor subscribe Routific slack https://hooks.slack.com/..."
        )
        return

    target, channel_type = args[0], args[1].lower()

    if channel_type == "telegram":
        config = json.dumps({"chat_id": ctx.chat_id})
    elif channel_type == "slack":
        if len(args) < 3:
            await ctx.reply("Slack requires a webhook URL.")
            return
        config = json.dumps({"webhook_url": args[2]})
    else:
        await ctx.reply(f"Unknown channel type: {channel_type}. Use 'telegram' or 'slack'.")
        return

    try:
        async with get_session() as s:
            repo = Repository(s)
            # Try as topic first, then entity
            topic = await repo.get_monitor_topic(target)
            if topic:
                await repo.add_monitor_subscriber(
                    topic_id=topic.id, channel_type=channel_type,
                    channel_config=config,
                )
                await ctx.reply(f"\u2705 Subscribed to topic '{target}' via {channel_type}")
                return

            entity = await repo.get_monitor_entity(target)
            if entity:
                await repo.add_monitor_subscriber(
                    entity_id=entity.id, channel_type=channel_type,
                    channel_config=config,
                )
                await ctx.reply(f"\u2705 Subscribed to entity '{target}' via {channel_type}")
                return

            await ctx.reply(f"'{target}' not found as topic or entity.")
    except Exception:
        await ctx.reply("Failed to subscribe.")


async def _handle_check(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor check — trigger immediate monitoring run."""
    from megobari.monitor import run_monitor_check, notify_subscribers

    topic_name = args[0] if args else None
    entity_name = args[1] if len(args) > 1 else None

    await ctx.reply("\U0001f50d Running monitor check...")
    await ctx.send_typing()

    try:
        digests = await run_monitor_check(
            topic_name=topic_name, entity_name=entity_name,
        )
        if digests:
            from megobari.monitor import _format_digest_message
            msg = _format_digest_message(digests, "Manual check")
            await ctx.reply(msg)
            await notify_subscribers(digests, "Manual check")
        else:
            await ctx.reply("No changes detected.")
    except Exception:
        logger.exception("Monitor check failed")
        await ctx.reply("Monitor check failed. Check logs.")


async def _handle_digest(ctx: TransportContext, args: list[str]) -> None:
    """Handle /monitor digest — show latest digests."""
    fmt = ctx.formatter
    try:
        async with get_session() as s:
            repo = Repository(s)
            topic_id = None
            entity_id = None
            if args:
                topic = await repo.get_monitor_topic(args[0])
                if topic:
                    topic_id = topic.id
                else:
                    entity = await repo.get_monitor_entity(args[0])
                    if entity:
                        entity_id = entity.id

            digests = await repo.list_monitor_digests(
                topic_id=topic_id, entity_id=entity_id, limit=20,
            )

        if not digests:
            await ctx.reply("No digests found.")
            return

        lines = [fmt.bold("Latest Digests:"), ""]
        for d in digests:
            ts = d.created_at.strftime("%m-%d %H:%M")
            lines.append(f"[{ts}] {d.change_type}: {d.summary[:100]}")
        await ctx.reply("\n".join(lines), formatted=True)
    except Exception:
        await ctx.reply("Failed to load digests.")
```

**Step 2: Export from handlers/__init__.py**

Add to `src/megobari/handlers/__init__.py`:

```python
from megobari.handlers.monitoring import cmd_monitor
```

And add `"cmd_monitor"` to the `__all__` list.

**Step 3: Register in bot.py**

Add to the `_cmds` dict in `create_application()`:

```python
"monitor": cmd_monitor,
```

**Step 4: Run linting**

Run: `uv run flake8 src/megobari/handlers/monitoring.py`
Expected: No errors

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/megobari/handlers/monitoring.py src/megobari/handlers/__init__.py src/megobari/bot.py
git commit -m "feat(monitor): add /monitor command handler with subcommands"
```

---

### Task 8: Integrate with scheduler for 4x daily runs

**Files:**
- Modify: `src/megobari/scheduler.py`

**Step 1: Add monitor scheduling to the scheduler**

Add a method to `Scheduler` class:

```python
    async def _run_monitor_checks(self) -> None:
        """Run website monitor checks and notify subscribers."""
        from megobari.monitor import notify_subscribers, run_monitor_check

        hour = datetime.now(timezone.utc).hour
        run_labels = {8: "Morning", 12: "Noon", 16: "Afternoon", 20: "Evening"}
        label = run_labels.get(hour, f"{hour}:00")

        try:
            digests = await run_monitor_check()
            if digests:
                await notify_subscribers(digests, label)

                # Send Telegram notifications for telegram subscribers
                from megobari.monitor import _format_digest_message
                msg = _format_digest_message(digests, label)
                if len(msg) > 4000:
                    msg = msg[:3997] + "..."
                await self._bot.send_message(chat_id=self._chat_id, text=msg)
        except Exception:
            logger.exception("Monitor check failed")
```

In the `_loop` method, add monitor check scheduling. The monitor runs at fixed hours (8, 12, 16, 20 UTC). Add a check similar to heartbeat:

```python
    _MONITOR_HOURS = {8, 12, 16, 20}

    async def _loop(self) -> None:
        """Run cron checks every 60 seconds."""
        try:
            last_heartbeat = datetime.now(timezone.utc)
            last_monitor_hour: int | None = None
            while not self._stop_event.is_set():
                now = datetime.now(timezone.utc)

                # Check cron jobs
                await self._run_due_crons(now)

                # Monitor checks at fixed hours
                current_hour = now.hour
                if current_hour in self._MONITOR_HOURS and current_hour != last_monitor_hour:
                    last_monitor_hour = current_hour
                    asyncio.create_task(self._run_monitor_checks())

                # Heartbeat check
                # ... rest unchanged ...
```

**Step 2: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/megobari/scheduler.py
git commit -m "feat(monitor): integrate monitor checks with scheduler at 4x daily"
```

---

### Task 9: Add API routes for monitoring

**Files:**
- Create: `src/megobari/api/routes/monitoring.py`
- Modify: `src/megobari/api/app.py`

**Step 1: Create API routes**

Create `src/megobari/api/routes/monitoring.py`:

```python
"""Website monitoring API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from megobari.db import Repository, get_session

router = APIRouter(tags=["monitoring"])


@router.get("/monitor/topics")
async def list_topics(request: Request) -> list[dict]:
    """All monitor topics with entity counts."""
    async with get_session() as s:
        repo = Repository(s)
        topics = await repo.list_monitor_topics()
        result = []
        for t in topics:
            entities = await repo.list_monitor_entities(topic_id=t.id)
            result.append({
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "enabled": t.enabled,
                "entity_count": len(entities),
                "created_at": t.created_at.isoformat(),
            })
    return result


@router.get("/monitor/entities")
async def list_entities(request: Request, topic_id: int | None = None) -> list[dict]:
    """All monitor entities, optionally filtered by topic."""
    async with get_session() as s:
        repo = Repository(s)
        entities = await repo.list_monitor_entities(topic_id=topic_id)
        result = []
        for e in entities:
            resources = await repo.list_monitor_resources(entity_id=e.id)
            result.append({
                "id": e.id,
                "topic_id": e.topic_id,
                "name": e.name,
                "url": e.url,
                "entity_type": e.entity_type,
                "description": e.description,
                "enabled": e.enabled,
                "resource_count": len(resources),
                "created_at": e.created_at.isoformat(),
            })
    return result


@router.get("/monitor/resources")
async def list_resources(
    request: Request, entity_id: int | None = None, topic_id: int | None = None,
) -> list[dict]:
    """All monitor resources."""
    async with get_session() as s:
        repo = Repository(s)
        resources = await repo.list_monitor_resources(
            entity_id=entity_id, topic_id=topic_id,
        )
    return [
        {
            "id": r.id,
            "topic_id": r.topic_id,
            "entity_id": r.entity_id,
            "name": r.name,
            "url": r.url,
            "resource_type": r.resource_type,
            "enabled": r.enabled,
            "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
            "last_changed_at": r.last_changed_at.isoformat() if r.last_changed_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in resources
    ]


@router.get("/monitor/digests")
async def list_digests(
    request: Request,
    topic_id: int | None = None,
    entity_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Latest monitor digests."""
    async with get_session() as s:
        repo = Repository(s)
        digests = await repo.list_monitor_digests(
            topic_id=topic_id, entity_id=entity_id, limit=limit,
        )
    return [
        {
            "id": d.id,
            "topic_id": d.topic_id,
            "entity_id": d.entity_id,
            "resource_id": d.resource_id,
            "summary": d.summary,
            "change_type": d.change_type,
            "created_at": d.created_at.isoformat(),
        }
        for d in digests
    ]
```

**Step 2: Register in app.py**

Add import and include_router in `create_api()`:

```python
from megobari.api.routes import monitoring
app.include_router(monitoring.router, prefix="/api", dependencies=auth_dep)
```

**Step 3: Run linting**

Run: `uv run flake8 src/megobari/api/routes/monitoring.py`
Expected: No errors

**Step 4: Commit**

```bash
git add src/megobari/api/routes/monitoring.py src/megobari/api/app.py
git commit -m "feat(monitor): add API routes for monitoring data"
```

---

### Task 10: Add /help entry and run full validation

**Files:**
- Modify: `src/megobari/handlers/admin.py` (add /monitor to help text)

**Step 1: Add /monitor to help command**

Find the help text in `handlers/admin.py` and add:

```
/monitor — website monitoring (topics, entities, resources)
```

**Step 2: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All PASS

**Step 3: Run all linters**

Run: `uv run flake8 src/ tests/ && uv run isort --check src/ tests/ && uv run pydocstyle --config=pyproject.toml src/`
Expected: All clean

**Step 4: Commit**

```bash
git add src/megobari/handlers/admin.py
git commit -m "feat(monitor): add /monitor to help text"
```
