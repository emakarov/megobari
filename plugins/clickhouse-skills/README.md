# ClickHouse Skills

ClickHouse best practices skill with 28 validated rules covering schema design, query optimization, and data ingestion.

## What's included

- **Schema rules** (14 rules) — primary key design, partitioning, types, nullable handling
- **Query rules** (10 rules) — joins, materialized views, skipping indices
- **Insert rules** (4 rules) — batching, mutations, formats

## Why this plugin

ClickHouse has specific behaviors (columnar storage, sparse indexes, merge tree mechanics) where general database intuition can be misleading. These rules encode validated, ClickHouse-specific guidance from the official documentation.

## Source

Based on [ClickHouse Best Practices](https://clickhouse.com/docs/best-practices) documentation. Licensed under Apache-2.0.
