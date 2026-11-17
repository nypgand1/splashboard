# Splashboard

A game dashboard for Taipei Fubon Braves. It reads Sportradar DataCore / Synergy basketball REST for PLG (`b1vqz`) and EASL (`b1e0z`), lists the selected league and season on Home, and shows Box Score, Rotation, Shot Chart, Lineup Stats, Matchups, Play-By-Play, and Report on the Game page.

## Requirements

- Python 3.10+
- Synergy credentials (see environment variables below)

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
# fill the four SYNERGY_PLG_* and SYNERGY_EASL_* credential variables
```

## Local run

```bash
uvicorn app:server --host 127.0.0.1 --port 8050 --workers 1
```

Open `http://localhost:8050` (not `127.0.0.1`; Google keeps the OAuth state cookie on one host). The live budget is process-local, so the process stays at one worker. Fly uses the same pin in `Procfile`. Sign-in is Google. Without `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` the process still starts, and `POST /login` answers that sign-in is unavailable.

## Tests

Tests do not call live Synergy. A clean clone only needs `requirements.txt`; `.env` is optional.

Unit suite (every change):

```bash
python3 -m unittest discover -s tests -v
```

Browser smoke (before commit, or when UI work is done). First machine also needs Chromium:

```bash
python3 -m playwright install chromium
python3 -m pytest tests/e2e -q
```

Smoke drives a local app with fixtures. It does not call live Synergy. `tests/e2e` covers Home, Game, and Report (first-paint, delete page, notes, PDF, sticky).

## Environment variables

| Variable | Purpose |
|---|---|
| `SYNERGY_PLG_CREDENTIAL_ID` | PLG credential id for the token endpoint |
| `SYNERGY_PLG_CREDENTIAL_SECRET` | PLG credential secret for the token endpoint |
| `SYNERGY_EASL_CREDENTIAL_ID` | EASL credential id for the token endpoint |
| `SYNERGY_EASL_CREDENTIAL_SECRET` | EASL credential secret for the token endpoint |
| `PORT` | listen port locally or on Fly (Fly default 8080) |
| `SESSION_SECRET` | signs `splashboard_session`; required on Fly |
| `GOOGLE_CLIENT_ID` | Google OAuth client id |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `AUTH_BOOTSTRAP_ADMINS` | comma-separated extra permanent admins |
| `PUBLIC_BASE_URL` | `http://localhost:8050` locally, `https://splashboard.fly.dev` on Fly |
| `AUTH_DB_PATH` | optional sqlite path; default off Fly is `.auth/auth.db` |

Hosts, organization ids, and both season tables live in `synergy_inbounder/settings.py`. They are tracked. Do **not** put credentials in `fly.toml` `[env]`.

Locally, use a gitignored `.env` (`python-dotenv` loads it when settings is imported). On Fly, use `fly secrets`.

## Deploy

```bash
fly secrets set SYNERGY_PLG_CREDENTIAL_ID='...' SYNERGY_PLG_CREDENTIAL_SECRET='...' SYNERGY_EASL_CREDENTIAL_ID='...' SYNERGY_EASL_CREDENTIAL_SECRET='...' -a splashboard
fly deploy
```

Set secrets before the first deploy that no longer bakes credentials into the image. Later `fly deploy` runs keep the existing secrets.

Dash links each file in `assets/` with `?m=` set to a content hash (`asset_url.py`), not the file mtime. The Paketo buildpack freezes mtimes at 1980-01-01, so a mtime query never changes and a phone keeps the previous CSS and JS. The Report font fetch reads that same hash from `#report-font-url`. The name stored inside the PDF stays `NotoSansTC-Regular.ttf`.

## Architecture

- `inbound/`: Synergy HTTP wave, repository (`inbound/repository.py`), and 3-module cache (`inbound/cache/catalog_cache.py`, `inbound/cache/frame_store.py`, `inbound/cache/live_cache.py`) with shared `SingleflightGroup` coalescing (`inbound/cache/singleflight.py`). `synergy_inbounder/` re-exports compatible entrypoints.
- `domain/`: Pure basketball calculation and domain rules (`clocks.py`, `periods.py`, `rates.py`, `ids.py`, `schedule_filters.py`, `shot_zones.py`). `synergy_reporter/` orchestrates post-game reports, rotation timelines, and season aggregations over `domain/`.
- `ui/`: Design tokens (`ui/tokens.py`), shared DMC components (`ui/components.py`), shared 4-card DMC and AG-Grid table builders (`ui/tables/stat_cards.py`, `ui/tables/ag_grid.py`), Plotly/SVG chart renderers (`ui/charts/rotation_fig.py`, `ui/charts/shot_svg.py`), and Game tab controllers (`ui/game_tabs/`).
- `pages/`: Dash `use_pages` route entrypoints (`pages/home.py`, `pages/game.py`, `pages/team_stats.py`, `pages/admin.py`).
- `auth/`: login policy, sqlite allowlist, Google OIDC, and the ASGI gate. It does not import `domain/`, `inbound/`, `synergy_inbounder/`, `synergy_reporter/`, or `pages/`.

Product behavior: `docs/spec.md`. Synergy contract: `docs/synergy.md`. Agent entry: `AGENTS.md`.
