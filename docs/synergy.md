# Synergy / DataCore contract

Product behavior is in `docs/spec.md`. This file covers the external API and how we call it.

## Hosts

- Token: `https://token.connect.sportradar.com/v1/oauth2/rest/token`
- REST: `https://api.dc.connect.sportradar.com/v1/basketball/...`
- Do not use `api.dc.prod.cloud.atriumsports.com` (HTTP 500 `AuthorizerConfigurationException`).

Organization id and the current season id live in `synergy_inbounder/settings.py`.

## Token

- POST JSON: `credentialId`, `credentialSecret`, `sport=basketball`, `organization.id`, scopes `read:organization` and `read:organization_live`.
- Success envelope has `data.token`. If `data.expiresIn` (seconds) is present, refresh 60 seconds before expiry.
- Both 401 and 403 trigger one refresh-and-retry.
- Concurrent first hits and concurrent 401/403 refresh once (process-local lock).
- Credentials come from the environment. They are not in git and not baked into the image.

## Official vs live

Finished-game detection is in `docs/spec.md`. `Parser.parse_game_bundle` uses one `live` flag:

| Resource | Finished | Live |
|---|---|---|
| play-by-play | `.../playbyplay` | `.../playbyplay/live` |
| team stats | `.../statistics/for/entity/in/fixtures/{id}` | same + `/live` |
| team period stats | `.../periods` | same + `/live` |
| player stats | `.../statistics/for/person/in/fixtures/{id}` | same + `/live` |
| fixture roster | always official `.../roster` | same |
| org persons / entities / venues | always official, HTTP cache 8 hours | same |
| season fixtures | always official, process cache 60 seconds | same |

Official live routes are marked **2 requests per minute** per route. The 30 / 25 / 25 cadence sits on that cap, assuming one live game at a time. This spec does not require 429 `Retry-After` or serializing the live bundle.

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

## Rate limits and cache

- Live PBP `requests_cache` TTL = 25 seconds (key `*/playbyplay/live`).
- Live `PostGameReport` process cache = 25 seconds. After the game is finished, the same process does not rebuild it.
- Concurrent lookups for the same `game_id` build the report once (singleflight).
- Caches are process-local. A Fly `auto_stop` wake is a cold cache.
