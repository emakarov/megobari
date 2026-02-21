---
name: gtfs-analysis
description: Use when working with GTFS (General Transit Feed Specification) data — analyzing routes, stops, trips, service patterns, and transit network coverage.
---

# GTFS Analysis

Skills for analyzing public transportation data in GTFS format.

## When to Use This Skill

Use when the user asks about:
- Transit route analysis (frequency, span of service, headways)
- Stop and station coverage
- Service patterns by day of week
- Trip scheduling and vehicle requirements
- Network coverage and density analysis
- Comparing transit feeds or agencies

## GTFS Data Model

GTFS feeds contain these core files:

| File | Contains |
|---|---|
| `agency.txt` | Transit agency info |
| `routes.txt` | Route definitions (name, type, color) |
| `trips.txt` | Individual trips on routes |
| `stop_times.txt` | Arrival/departure times at stops |
| `stops.txt` | Stop locations (lat/lon, name) |
| `calendar.txt` | Service patterns by day of week |
| `calendar_dates.txt` | Service exceptions |
| `shapes.txt` | Route geometry |

## Analysis Patterns

### Route Performance
- **Frequency**: trips per hour during peak/off-peak
- **Span of service**: first to last departure
- **Headway regularity**: consistency of intervals between trips

### Network Coverage
- **Stop density**: stops per area using H3 hexagonal grids
- **Service area**: geographic extent of the network
- **Route overlap**: identify corridors with multiple routes

### Service Patterns
- **Weekday vs weekend**: compare service levels
- **Peak identification**: find morning/evening rush patterns
- **Seasonal variation**: compare different feed versions

## Tips

- GTFS times can exceed 24:00:00 for trips past midnight (e.g., 25:30:00 = 1:30 AM)
- `route_type` codes: 0=tram, 1=subway, 2=rail, 3=bus, 4=ferry, 5=cable, 6=gondola, 7=funicular
- Always check `calendar.txt` and `calendar_dates.txt` together for accurate service days
- Use `shapes.txt` for route geometry, not stop locations
