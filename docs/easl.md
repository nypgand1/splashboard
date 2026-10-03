# EASL (East Asia Super League) API contract

Product behavior is in `docs/spec.md`. The official Synergy / DataCore contract is in `docs/synergy.md`. This file documents the EASL external REST endpoints provided by the EASL sync server (`https://easl.joshricha.com/api/v1`), their underlying vendor data models, and how they correspond to the Synergy / Sportradar DataCore architecture.

---

## 1. Architecture & Hosts

- **Host Base URL**: `https://easl.joshricha.com/api/v1`
- **Underlying Data Vendor**: **Sportradar** (specifically Sportradar Basketball API / DataCore Connect).
  - Organization ID: `b1e0z`
  - Asset CDN: `https://images.dc.connect.sportradar.com/b1e0z/...`
  - Upstream Data Feeds: Sportradar Basketball REST feeds stored in a local SQLite database and synchronized to Webflow CMS.
- **Authentication**:
  - **Public Read Routes**: Completely open without API keys or OAuth tokens (`GET /matches`, `GET /boxscore`, `GET /playbyplay`, `GET /teams`, `GET /players`, `GET /standings`, `GET /leaders`).
  - **Internal Admin Routes**: Protected by session JWT (`POST /api/v1/auth/login`, `GET /api/v1/auth/verify`, `POST /api/v1/sync-webflow/*`, `POST /api/v1/metadata/sync`).
- **Rate Limits & Headers**:
  - Response header: `RateLimit: "100-in-1sec"; q=100; w=1`
  - Safe client concurrency: Up to 10–20 requests per second.
  - Express.js backend behind Nginx reverse proxy.

---

## 2. Seasons & Competitions

All seasons can be queried via `GET /metadata/seasons`.

| Season Label | Season ID (`seasonId`) | Competition ID (`competitionId`) | Status | Year | Dates (Local) |
|---|---|---|---|---|---|
| **2026-27** | `1409787d-a683-11f1-aea7-b596f55be5ed` | `77a790d8-ad01-11ed-8355-01b87a3904c0` | `ACTIVE` | 2026 | 2026-10-03 ~ 2027-03-28 |
| **2025-26** | `77441bb3-9759-11f0-b659-0561c09a0222` | `77a790d8-ad01-11ed-8355-01b87a3904c0` | `COMPLETE` | 2025 | 2025-10-08 ~ 2026-03-31 |
| **2024-25** | `57cefc32-5ace-11ef-81a0-3d1f6018efb7` | `77a790d8-ad01-11ed-8355-01b87a3904c0` | `COMPLETE` | 2024 | 2024-10-02 ~ 2025-03-09 |
| **2023-24** | `c24ce68a-6420-11ee-9daf-6b6188281bd0` | `77a790d8-ad01-11ed-8355-01b87a3904c0` | `COMPLETE` | 2023 | 2023-10-11 ~ 2024-03-11 |

*Note: In `easl_inbounder/settings.py`, `EASL_SEASON_ID` defaults to the active `2026-27` season.*

---

## 3. Synergy / DataCore vs. EASL Comparison

Because EASL's backend directly ingests Sportradar DataCore feeds, the schema and statistics vocabulary are largely identical to Synergy, with several architectural simplifications:

| Concept / Field | Official Synergy / Sportradar DataCore | EASL (`easl.joshricha.com`) |
|---|---|---|
| **Authentication** | OAuth2 Bearer token (`read:organization`) | Unauthenticated for public GET |
| **JSON Envelope** | Wrapped in `{ "data": ... }` | Direct JSON arrays/objects |
| **Schedule Endpoint** | `/fixtures?seasonId=...` | `/matches?seasonId=...` |
| **Match Details** | `/fixtures/{id}` | `/matches/{fixtureId}` |
| **Player Boxscore** | `.../statistics/for/person/in/fixtures/{id}` | `/matches/{fixtureId}/boxscore` |
| **Play-by-Play** | `.../playbyplay` | `/matches/{fixtureId}/playbyplay` |
| **Team Stats** | `.../statistics/for/entity/in/fixtures/{id}` | `/matches/{fixtureId}/teamstats` |
| **Team Period Stats** | `.../periods` (array of rows) | `/matches/{fixtureId}/teamstats/by/period` (dict keyed by `period_1`..`period_4`) |
| **Player Bio / Info** | `.../persons/{id}` | `/players/{playerId}` |
| **Player Season Stats** | `.../statistics/for/person/in/seasons/{id}` | `/players/{playerId}/stats?seasonId={id}` |
| **Team Season Stats** | `.../statistics/for/entity/in/seasons/{id}` | `/teams/{teamId}/stats?seasonId={id}` |
| **Standings** | `.../standings` | `/standings?seasonId={id}` |
| **Leaders** | `.../leaders` | `/leaders?seasonId={id}` |
| **Minutes Format** | ISO 8601 Duration (`PT29M45S`) | ISO 8601 Duration (`PT29M45S`) |
| **Identifiers** | UUIDs (`fixtureId`, `personId`, `entityId`) | UUIDs (`fixtureId`, `personId`, `entityId` / `teamId`) |
| **Starter indicator** | `starter: true / false` | `starter: true / false` |
| **Jersey number** | `shirtNumber` / `bib` | `bib` and `jerseyNumber` |

---

## 4. Match Lifecycle & Status Codes

- `CONFIRMED`: Game has completed and final boxscores/stats are verified. `/boxscore`, `/playbyplay`, and `/teamstats` return complete data.
- `SCHEDULED`: Game is scheduled in the future. `/boxscore`, `/teamstats`, and `/playbyplay` return empty payloads (`[]` or `{ boxScore: [], teams: [] }`).
- `DRAFT`: Preliminary fixture configuration before public confirmation.

---

## 5. Endpoints Reference

### 5.1 System & Seasons

#### `GET /health`
Returns health check status and timestamp.
```json
{
  "status": "OK",
  "message": "EASL Basketball API is running",
  "timestamp": "2026-10-03T06:40:24.995Z"
}
```

#### `GET /metadata/seasons`
Returns the metadata list of all configured EASL seasons.
- **Response**: Array of Season objects:
```json
[
  {
    "id": 4,
    "seasonId": "1409787d-a683-11f1-aea7-b596f55be5ed",
    "competitionId": "77a790d8-ad01-11ed-8355-01b87a3904c0",
    "organizationId": "b1e0z",
    "year": 2026,
    "nameLocal": "EASL 26-27",
    "nameLatin": null,
    "status": "ACTIVE",
    "startDate": "2026-10-03",
    "endDate": "2027-03-28",
    "createdAt": "2026-10-01 03:57:39",
    "updatedAt": "2026-10-01 03:57:39"
  }
]
```

---

### 5.2 Matches & Schedules

#### `GET /matches`
Query matches for a season.
- **Query Parameters**:
  - `seasonId` *(optional, string UUID)*: Season filter. Defaults to active season (`2026-27`).
- **Response**: Array of Match objects.
```json
[
  {
    "fixtureId": "c48aa245-a6d0-11f1-9bdb-a325a9e4d80c",
    "fixtureNumber": 2627001,
    "fixtureType": "REGULAR",
    "status": "SCHEDULED",
    "startTimeLocal": "2026-10-03T16:10:00",
    "startTimeUTC": "2026-10-03T08:10:00",
    "startTimeActualUTC": null,
    "endTimeActualUTC": null,
    "nameLocal": "EASL Tip-Off 2026 Cebu",
    "poolCode": "6dc7cf4556af4e6db2585027805ba9",
    "pool": {
      "id": "6dc7cf4556af4e6db2585027805ba9",
      "name": "Group A",
      "abb": "A"
    },
    "venue": {
      "nameLocal": "SM Seaside Cebu Arena",
      "nameLatin": "SM Seaside Cebu Arena",
      "countryCode": "PHL",
      "address": {
        "city": "Cebu City",
        "state": "Cebu"
      }
    },
    "competitors": [
      {
        "teamId": "6c173781-a6bf-11f1-a95a-31326737faaf",
        "entityId": "6c173781-a6bf-11f1-a95a-31326737faaf",
        "nameFullLocal": "Macau Hou Chon",
        "nameFullLatin": "Macau Hou Chon",
        "codeLocal": "MHC",
        "codeLatin": "MHC",
        "isHome": true,
        "score": "0",
        "logo": "https://images.dc.connect.sportradar.com/b1e0z/ea7a20753e974139aef468db58926811?size=RAW",
        "primaryColor": "000000"
      },
      {
        "teamId": "86515908-b0f5-11ed-ac6b-c199a9dea184",
        "entityId": "86515908-b0f5-11ed-ac6b-c199a9dea184",
        "nameFullLocal": "Taipei Fubon Braves",
        "nameFullLatin": null,
        "codeLocal": "富邦勇士",
        "codeLatin": "TFB",
        "isHome": false,
        "score": "0",
        "logo": "https://images.dc.connect.sportradar.com/b1e0z/5a015b28e60544af8c882fb3b78fe7d6?size=RAW",
        "primaryColor": "000080"
      }
    ]
  }
]
```

#### `GET /matches/{fixtureId}`
Get details for a single match.
- **Path Parameters**:
  - `fixtureId` *(string UUID)*: Unique match ID.
- **Response**: Single Match object (same structure as element in `/matches`).

---

### 5.3 Match Play-by-Play & Statistics

#### `GET /matches/{fixtureId}/playbyplay`
Chronological event stream for the match.
- **Path Parameters**:
  - `fixtureId` *(string UUID)*: Unique match ID.
- **Response**:
```json
{
  "teams": [
    {
      "teamId": "864e1998-b0f5-11ed-bb08-c199a9dea184",
      "nameFullLocal": "Seoul SK Knights",
      "nameFullLatin": null,
      "logo": "https://images.dc.connect.sportradar.com/b1e0z/0a1ffcdce4274cb2aac79bf152a35557?size=RAW"
    }
  ],
  "playbyplay": [
    {
      "periodId": 1,
      "sequence": 5,
      "description": "Jump ball lost",
      "receivedTime": 1710068432073,
      "eventTime": "2024-03-10T11:00:31.558",
      "teamId": "864e1998-b0f5-11ed-bb08-c199a9dea184",
      "player": {
        "playerId": "8824aa50-b0f5-11ed-bbc7-c199a9dea184",
        "nameFullLocal": "Jameel WARNEY",
        "nameFullLatin": "Jameel WARNEY",
        "jerseyNumber": "34"
      },
      "scores": {
        "864e1998-b0f5-11ed-bb08-c199a9dea184": 0,
        "99d719e1-64c1-11ee-b1bd-27129dd6c255": 0
      }
    }
  ]
}
```

#### `GET /matches/{fixtureId}/boxscore`
Player individual statistics for both competitors.
- **Path Parameters**:
  - `fixtureId` *(string UUID)*: Unique match ID.
- **Response**:
```json
{
  "teams": [
    {
      "teamId": "99d719e1-64c1-11ee-b1bd-27129dd6c255",
      "nameFullLocal": "Chiba Jets",
      "nameFullLatin": null,
      "logo": "https://images.dc.connect.sportradar.com/b1e0z/3c26786c12144b25916ca11f787ea232?size=RAW"
    }
  ],
  "boxScore": [
    {
      "personId": "0969bb3d-88f8-11ee-83b0-c9a2aae4daaa",
      "entityId": "99d719e1-64c1-11ee-b1bd-27129dd6c255",
      "fixtureId": "6e3c321b-d078-11ee-bd9b-cfe0b28e3077",
      "bib": "10",
      "position": "F",
      "starter": true,
      "isPlayer": true,
      "isTeamOfficial": false,
      "didNotPlayReason": null,
      "player": {
        "playerId": "0969bb3d-88f8-11ee-83b0-c9a2aae4daaa",
        "nameFullLocal": "Xavier COOKS",
        "nameFullLatin": null,
        "headshot": "https://images.dc.connect.sportradar.com/b1e0z/7efe9d7279874251b9fd80b27e7afcfd?size=800"
      },
      "statistics": {
        "minutes": "PT29M45S",
        "points": 6,
        "plusMinus": 6,
        "plus": 53,
        "minus": 47,
        "pir": 12,
        "efficiency": 10,
        "fieldGoalsMade": 3,
        "fieldGoalsAttempted": 6,
        "fieldGoalsPercentage": 50,
        "fieldGoalsEffectivePercentage": 50,
        "pointsTwoMade": 3,
        "pointsTwoAttempted": 6,
        "pointsTwoPercentage": 50,
        "pointsThreeMade": 0,
        "pointsThreeAttempted": 0,
        "pointsThreePercentage": null,
        "freeThrowsMade": 0,
        "freeThrowsAttempted": 0,
        "freeThrowsPercentage": null,
        "rebounds": 7,
        "reboundsOffensive": 2,
        "reboundsDefensive": 5,
        "assists": 2,
        "steals": 0,
        "turnovers": 3,
        "blocks": 1,
        "blocksReceived": 0,
        "foulsPersonal": 3,
        "foulsDrawn": 5,
        "pointsInThePaint": 6,
        "pointsSecondChance": 2,
        "pointsFastBreak": 0,
        "pointsFromTurnover": 0,
        "usageRate": 15.0508
      }
    }
  ]
}
```

#### `GET /matches/{fixtureId}/teamstats`
Full-game aggregate advanced statistics comparing both teams.
- **Path Parameters**:
  - `fixtureId` *(string UUID)*
- **Response**: Array of 2 Team Stats objects:
```json
[
  {
    "entityId": "864e1998-b0f5-11ed-bb08-c199a9dea184",
    "fixtureId": "6e3c321b-d078-11ee-bd9b-cfe0b28e3077",
    "team": {
      "teamId": "864e1998-b0f5-11ed-bb08-c199a9dea184",
      "nameFullLocal": "Seoul SK Knights"
    },
    "statistics": {
      "points": 69,
      "efficiency": 71,
      "assists": 12,
      "assistsTurnoverRatio": 1.09091,
      "biggestLead": 5,
      "biggestScoringRun": 6,
      "fieldGoalsMade": 26,
      "fieldGoalsAttempted": 71,
      "fieldGoalsPercentage": 36.61972,
      "fieldGoalsEffectivePercentage": 40.14085,
      "pointsTwoMade": 21,
      "pointsTwoAttempted": 47,
      "pointsTwoPercentage": 44.68085,
      "pointsThreeMade": 5,
      "pointsThreeAttempted": 24,
      "pointsThreePercentage": 20.83333,
      "freeThrowsMade": 12,
      "freeThrowsAttempted": 14,
      "freeThrowsPercentage": 85.71429,
      "rebounds": 39,
      "reboundsOffensive": 12,
      "reboundsDefensive": 27,
      "reboundsTeamTotal": 4,
      "steals": 4,
      "turnovers": 11,
      "turnoversTeam": 0,
      "blocks": 1,
      "blocksReceived": 2,
      "foulsPersonal": 20,
      "foulsDrawn": 13,
      "pointsInThePaint": 38,
      "pointsSecondChance": 13,
      "pointsFastBreak": 12,
      "pointsFromTurnover": 10,
      "pointsFromBench": 15
    }
  }
]
```

#### `GET /matches/{fixtureId}/teamstats/by/period`
Team statistics broken down per quarter / period.
- **Path Parameters**:
  - `fixtureId` *(string UUID)*
- **Response**: Array of 2 Team Period Stats objects, with keys `period_1`, `period_2`, `period_3`, `period_4` (and `period_5`+ / overtime if played):
```json
[
  {
    "team": {
      "teamId": "864e1998-b0f5-11ed-bb08-c199a9dea184",
      "nameFullLocal": "Seoul SK Knights"
    },
    "period_1": {
      "points": 16,
      "assists": 4,
      "efficiency": 14,
      "fieldGoalsMade": 5,
      "fieldGoalsAttempted": 16,
      "fieldGoalsPercentage": 31.25,
      "rebounds": 9
    },
    "period_2": { "points": 21 },
    "period_3": { "points": 17 },
    "period_4": { "points": 15 }
  }
]
```

---

### 5.4 Standings & Leaders

#### `GET /standings`
Standings grouped by tournament group pools.
- **Query Parameters**:
  - `seasonId` *(optional, string UUID)*
- **Response**: Array of Standings items:
```json
[
  {
    "id": "a9b34e16-9d18-11f0-887d-85105bf9984f",
    "position": 1,
    "team": {
      "id": "d042f639-5ad9-11ef-9305-6523ca47a22e",
      "name": "Hiroshima Dragonflies",
      "code": "HDF",
      "logo": "https://images.dc.connect.sportradar.com/b1e0z/34be0fafbe3a4049bd3c3eb4e4bcfce7?size=RAW"
    },
    "pool": {
      "id": "6a5477234bcd4fd69dd3810052fd5a",
      "name": "Group A",
      "abb": "A"
    },
    "stats": {
      "gamePlayed": 6,
      "wins": 5,
      "losses": 1,
      "draws": 0,
      "winPercentage": 0.83,
      "pointDifference": 67,
      "pointsFor": 517,
      "pointsAgainst": 450,
      "steak": 3
    },
    "lastFiveMatches": [
      {
        "result": "W",
        "scoreFor": "72",
        "scoreAgainst": "68",
        "isHome": true,
        "startTimeUTC": "2025-03-09T11:10:00",
        "opponent": {
          "id": "f170040e-5ad9-11ef-b4d4-070129f618c6",
          "name": "Taoyuan Pauian Pilots"
        }
      }
    ]
  }
]
```

#### `GET /leaders`
Tournament-wide individual statistical leaders.
- **Query Parameters**:
  - `seasonId` *(optional, string UUID)*
- **Response**: Object mapping stat categories to top 5 player arrays:
  - `pointsPerGame`
  - `reboundsPerGame`
  - `assistsPerGame`
  - `stealsPerGame`
  - `blocksPerGame`
  - `fieldGoalsPercentage`
  - `freeThrowsPercentage`
  - `pointsThreePercentage`
  - `pointsThreeMade`

---

### 5.5 Teams

- `GET /teams`: Full list of all registered EASL teams.
- `GET /teams/{teamId}`: Detail info for a specific team.
- `GET /teams/{teamId}/matches?seasonId={seasonId}`: All matches played by this team in a season.
- `GET /teams/{teamId}/stats?seasonId={seasonId}`: 144 cumulative team metrics for the season.
- `GET /teams/{teamId}/leaders?seasonId={seasonId}`: Within-team player statistical leaderboards.

---

### 5.6 Players

- `GET /players`: Full directory of players. Supports `?seasonId={seasonId}&teamId={teamId}` to retrieve a team's roster for that season.
- `GET /players/{playerId}`: Comprehensive biographical data (birth date, height, weight, dominant hand, nationality, headshot, social handles).
- `GET /players/{playerId}/stats?seasonId={seasonId}`: 103 season-long statistics for a player.

---

## 6. Parsing Guidelines for Splashboard

1. **Roster & Starters**:
   - In EASL, starters are explicitly flagged inside `/matches/{fixtureId}/boxscore` (`starter: true`).
   - Jersey number is in `bib`.
   - Players who did not play have non-null `didNotPlayReason` (e.g. `DNP`, `COACH_DECISION`, `INJURY`).
2. **Minutes Played**:
   - `minutes` uses standard ISO 8601 duration (`PT29M45S`). A regex like `(?:PT)?(?:(\d+)M)?(?:(\d+)S)?` reliably converts to MM:SS or integer seconds.
3. **Pace & Possessions**:
   - Same as Synergy: Team statistics do not pre-calculate pace. Compute possessions from play-by-play events or via standard basketball formula `FGA + 0.4*FTA + TO - ORB`.
4. **Error Handling**:
   - Unplayed games (`SCHEDULED`) will return 200 with empty boxscore arrays. Check `status == 'CONFIRMED'` before attempting to render box scores.
