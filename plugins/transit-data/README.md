# Transit Data

Skills for working with GTFS (General Transit Feed Specification) public transportation data.

## What's included

- **gtfs-analysis** — Route performance, network coverage, service pattern analysis

## Why this plugin

GTFS is the standard format for public transit data worldwide, but it has quirks (times past midnight, complex calendar logic, multiple related files). This skill teaches Claude the data model, common analysis patterns, and gotchas.

## Works well with

- TransitHouse MCP server for querying pre-loaded GTFS feeds via ClickHouse
- The `clickhouse-skills` plugin for optimizing transit data queries
