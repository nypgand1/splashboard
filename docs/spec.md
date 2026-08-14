# Splashboard product spec

This file is the source of truth for product behavior. Tests and later feature work check against it.

## Scope

- Web dashboard for Taipei Fubon Braves schedule and single-game views.
- UI strings are English, including loading, empty, and error copy.
- No Report PDF export. Rotation is Plotly only, with no separate dark mode.

## Pages

### Home `/`

- Show `Loading...`, then load the current-season schedule asynchronously.
- Columns: Time, Game Type, Venue, Home Team, Score, Away Team.
- For `PENDING` / `IN_PROGRESS` / `FINISHED` / `CONFIRMED`, the score is a link to `/game/<fixtureId>`.
- On Synergy failure: `Failed to load games. Please try again later.` (HTTP 200, no unhandled exception).
- When the season list is empty: `No games available.`

### Game `/game/<game_id>`

Top tabs, left to right:

1. Box Score
2. Rotation
3. Play-By-Play
4. Lineup Stats
5. Report

Box Score is the default. Tab panes stay mounted. Hidden-tab render callbacks return `no_update` and do not rebuild children.

A `dcc.Store` that is `None` or invalid JSON is treated as an empty object. Callbacks must not crash.

## Finished vs live

- Finished statuses: `FINISHED`, `CONFIRMED` (compared after strip).
- Every other status (`IN_PROGRESS`, `PENDING`, unknown, empty) is live.
- Finished games:
  - use official routes (URL has **no** `/live` suffix)
  - freeze the report cache (no TTL rebuild)
  - disable the Game-page interval
- Live games:
  - use `/live` routes (except fixture roster and org persons/entities/venues)
  - UI interval = 30 seconds
  - PBP HTTP cache and live report cache = 25 seconds
  - Play-By-Play and Rotation share that cadence

## Rotation

- Plotly heatmap, colorscale `PuBu`.
- Fixed width 1220px, not 100%.
- Margin ticks in steps of 5.
- Player rows sort by first time on court, then jersey; DNP rows last.
- Scoring heatmap accumulates team points per minute bucket.
- Period labels: 1–4 → `1Q`–`4Q`; official OT `periodId` 11 → `OT`, 12 → `2OT`; legacy `periodId` 5 still reads as `OT`.

## Report

- Draggable / resizable block canvas.
- Period tables (PTS / Foul / Timeout) use `period_label` for column names.
- No PDF.

## Lineup Stats

- Lineup size is selectable from 5 down to 2.
- New store shape is nested by size. The old shape (team name as top-level key) still reads as the 5-player tables.

## Config and deploy

- Public hosts, org id, and season ids live in git (`synergy_inbounder/settings.py`).
- Credentials come only from `SYNERGY_CREDENTIAL_ID` and `SYNERGY_CREDENTIAL_SECRET`.
- Missing credentials must fail clearly at token fetch. Do not POST empty strings.
- Default tests do not call live Synergy.
