# Splashboard

A game dashboard for Taipei Fubon Braves. It reads Sportradar DataCore / Synergy basketball REST, lists the season on Home, and shows Box Score, Rotation, Lineup Stats, Play-By-Play, and Report on the Game page.

## Requirements

- Python 3.10+
- Synergy credentials (see environment variables below)

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
# fill SYNERGY_CREDENTIAL_ID and SYNERGY_CREDENTIAL_SECRET
```

## Local run

```bash
uvicorn app:server --host 127.0.0.1 --port 8050
```

Open `http://127.0.0.1:8050`.

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
| `SYNERGY_CREDENTIAL_ID` | credential id for the token endpoint |
| `SYNERGY_CREDENTIAL_SECRET` | credential secret for the token endpoint |
| `PORT` | listen port locally or on Fly (Fly default 8080) |

Hosts, organization id, and season ids live in `synergy_inbounder/settings.py` and are tracked. Do **not** put credentials in `fly.toml` `[env]`.

Locally, use a gitignored `.env` (`python-dotenv` loads it when settings is imported). On Fly, use `fly secrets`.

## Deploy

```bash
fly secrets set SYNERGY_CREDENTIAL_ID='...' SYNERGY_CREDENTIAL_SECRET='...' -a splashboard
fly deploy
```

Set secrets before the first deploy that no longer bakes credentials into the image. Later `fly deploy` runs keep the existing secrets.

Product behavior: `docs/spec.md`. Synergy contract: `docs/synergy.md`. Agent entry: `AGENTS.md`.
