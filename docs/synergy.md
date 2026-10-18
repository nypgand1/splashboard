# Synergy / DataCore contract

Product behavior is in `docs/spec.md`. This file covers the external API and how we call it.

## Hosts

- Token: `https://token.connect.sportradar.com/v1/oauth2/rest/token`
- REST: `https://api.dc.connect.sportradar.com/v1/basketball/...`
- Do not use `api.dc.prod.cloud.atriumsports.com` (HTTP 500 `AuthorizerConfigurationException`).

Organization ids and both season tables live in `synergy_inbounder/settings.py`.

- PLG is `b1vqz`. `SYNERGY_SEASON_ID` is the `2026-27` season. Home can select the other regular seasons in that table. Game status lookup searches the PLG default season first, then the rest of that table.
- EASL is `b1e0z`. `EASL_SEASON_ID` is the `2026-27` season. The menu is the four regular seasons in that table, newest first. Champions Week 2023 is not in the menu. Home does not call a seasons catalog. Game status lookup searches the EASL default season first, then the rest of that table.
- There is no cross-organization fallback.

## Token

- POST JSON: `credentialId`, `credentialSecret`, `sport=basketball`, `organization.id` as a one-id list of the organization being requested, scopes `read:organization` and `read:organization_live`.
- Each organization keeps its own bearer. A refresh for one organization does not replace the other.
- Success envelope has `data.token`. If `data.expiresIn` (seconds) is present, refresh 60 seconds before expiry.
- Both 401 and 403 trigger one refresh-and-retry.
- Concurrent first hits and concurrent 401/403 refresh once per organization (process-local lock).
- PLG credentials are `SYNERGY_PLG_CREDENTIAL_ID` and `SYNERGY_PLG_CREDENTIAL_SECRET`. EASL credentials are `SYNERGY_EASL_CREDENTIAL_ID` and `SYNERGY_EASL_CREDENTIAL_SECRET`. There is no fallback to `SYNERGY_CREDENTIAL_ID` or `SYNERGY_CREDENTIAL_SECRET`. A missing pair fails only that organization. They are not in git and not baked into the image.

## Official vs live

Finished-game detection is in `docs/spec.md`. `Parser.parse_game_bundle` uses one `live` flag:

| Resource | Finished | Live |
|---|---|---|
| play-by-play | `.../playbyplay` | `.../playbyplay/live` |
| team stats | `.../statistics/for/entity/in/fixtures/{id}` | same + `/live` |
| team period stats | `.../periods` | same + `/live` |
| player stats | `.../statistics/for/person/in/fixtures/{id}` | same + `/live` |
| player period stats | `.../periods` (`limit=1000`; no `isPlayer`) | same + `/live` |
| fixture roster | always official `.../roster` | same |
| org persons / entities / venues | always official, HTTP cache 8 hours | same |
| season fixtures | always official, process cache 25 seconds | same |

Official live routes are marked **2 requests per minute** per route. The 30 / 25 / 25 cadence sits on that cap, assuming one live game at a time. The live bundle adds one person-period request on that same cadence. This spec does not require 429 `Retry-After` or serializing the live bundle.

## Response envelope

- Success: JSON has `data`.
- HTTP 5xx, or 200 without `data`: treat as an error. UI shows the English failure copy. Callbacks must not raise unhandled.
- `payload_from_response` is the entry point for that rule.

## Roster and jersey

- Fixture roster `bib` wins over player-stats `shirtNumber`.
- Starters come from the fixture roster (fall back to stats when roster is missing).
- `participated` comes from stats. Roster-only rows default to participated.

## periodId

- Regulation: 1–4.
- Official OT: 11, 12, …
- Legacy data may use 5 as the first OT. The display layer reads both as `OT`.
- Team and person period statistics have no `pace` or `possessions` field. Pace possessions are counted from play-by-play in API `data` order (see `docs/spec.md`). A missing play-by-play falls back to `FGA + 0.4*FTA + TO − ORB`.
- Person `/periods` and `/periods/live` reject query `isPlayer` with HTTP 400. Person totals still accept `isPlayer=true`.

## Rate limits and cache

- Live PBP `requests_cache` TTL = 25 seconds (key `*/playbyplay/live`).
- Live `PostGameReport` process cache = 25 seconds. After the game is finished, the same process does not rebuild it.
- Season fixture process cache = 25 seconds. Home reloads that list every 30 seconds, so the next poll can see a score or status change.
- Concurrent lookups for the same organization and `game_id` build the report once (singleflight). The memo key is that pair.
- Caches are process-local. A Fly `auto_stop` wake is a cold cache.
