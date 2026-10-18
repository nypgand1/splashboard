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
| org persons / entities / venues | always official, HTTP cache 2 hours | same |
| season fixtures | always official, process cache 30 seconds, and that process cache is the only season cache | same |

Official live routes are marked **2 requests per minute** per route. PLG and EASL are separate budgets. One live bundle is one generation of the five `/live` routes.

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

Two lifetimes. Short is 30 seconds: the five `/live` routes, the live report memo, season fixtures, roster, and pre-finish official stats. Long is 2 hours: persons, entities, venues, and the id table. The season URL is not also served from the HTTP cache. Token lifetime stays Synergy `expiresIn` (refresh 60 seconds early). A finished report memo stays for the life of the process.

- Live PBP `requests_cache` TTL = 30 seconds (key `*/playbyplay/live`). The other four `/live` routes use the same 30-second default.
- Live `PostGameReport` process cache = 30 seconds. The five routes are written and expire together. A failed round does not update the memo. Partial HTTP hits for that fixture are dropped so the next rebuild does not mix a newer play-by-play with older stats. After the game is finished, the same process does not rebuild it.
- Season fixture process cache = 30 seconds, with singleflight. The id table uses the same singleflight and the 2-hour lifetime. A failure is not stored. If a previous entry exists, it is served and marked delayed, except 401/403, which still fail.
- Home and Game poll every 35 seconds. One watched live game fetches about every 35 seconds. Two or more games watched within 70 seconds share one origin bundle per organization every 35 seconds, round-robin, so each game updates about every 70 seconds. A game leaves the rotation after 70 seconds with no poll.
- The first open of two games may both fetch immediately. That uses the minute's 2 calls. No live origin follows until 60 seconds after that burst. That quiet stretch is the schedule, not a failure.
- Each organization allows 2 origin calls per live route per rolling 60 seconds. Reserving a bundle takes one call on all five routes before `PostGameReport` runs. A 5xx retry is one extra call on that route and is not sent when the route is already at 2. A cache hit does not count.
- 429 pauses that organization's live calls until `Retry-After`, or 60 seconds when the header is missing or invalid. The page keeps the last success when one exists.
- Concurrent lookups for the same organization and `game_id` build the report once (singleflight). Sibling callbacks in the same tick do not start a second bundle. The memo key is that pair. Season and id-table misses share one fetch each.
- The budget, the singleflight, and the memos are process-local. Startup is one worker (`--workers 1`). A second process is outside this guarantee. A Fly `auto_stop` wake is a cold cache.
