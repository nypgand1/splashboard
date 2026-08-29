# Agent entry

Read the matching spec before changing behavior or fixing a bug.

- Product behavior (pages, tabs, finished vs live, Rotation, English UI, Report canvas): `docs/spec.md`
- Report canvas decisions (GridStack, `dmc.Table`, localStorage, glass chrome, JS paint): `docs/adr/0001-report-canvas.md`
- Report v2 unit cases: `docs/report-tests.md`
- Synergy hosts, official vs `/live`, token, roster, periodId, rate limits: `docs/synergy.md`
- Local run, tests, deploy, environment variables: `README.md`

## Daily

- Unit command: `python3 -m unittest discover -s tests -v`
- Browser smoke: `python3 -m pytest tests/e2e -q` (needs Chromium once: `python3 -m playwright install chromium`)
- Tests use mocks and small fixtures. They do not call live Synergy.
- Credentials travel only as `SYNERGY_CREDENTIAL_ID` / `SYNERGY_CREDENTIAL_SECRET`. Do not commit them. Do not put them in `fly.toml` `[env]`.
- Do not `git push` or `fly deploy` unless asked.
- UI strings are English.
- Resume unfinished work from `git diff` / `git status` and the matching spec. Do not reread whole page modules (`pages/game.py`, `pages/home.py`) when the diff already names the change.
- Grill or lock product decisions before editing. Implementation is cheap; a second full-page browser pass is not.
- When changing user-visible UI (layout, tabs, routing, rendered data), walk the related pages in a browser. A single static screenshot is not enough.

## Verification cadence

1. After every code change, run the full unit suite (`python3 -m unittest discover -s tests -v`).
2. Run Playwright smoke (`python3 -m pytest tests/e2e -q`) before `git commit`, or when the user says the UI work is done, whichever comes first. Skip a second smoke if this round already ran one. Non-UI changes (parser, cache, status helpers with no layout change) skip browser smoke.
3. `scripts/cdp_verify_report.py` only when Report canvas or PDF changes. Do not fold Report/GridStack/Tiptap/PDF into the Playwright smoke.
4. Repair failures in this same session. Use the pytest short traceback and assertion message. Do not dump the page accessibility tree, inner HTML, or a screenshot into the transcript. Screenshots may be written under `scratch/` and left unread.

Acceptance for browser checks is the Playwright process exit code. Interactive browser-protocol stepping (page snapshots, per-click dumps, live `evaluate` in the session) is not the acceptance path.

## UI & AG-Grid contracts

- Custom cell formatting and dynamic styles must use `window.dashAgGridComponentFunctions` in `assets/report_canvas.js` (never uncompiled inline Python JS strings).
- Unit tests cover Python contracts: per-column center alignment on `headerClass` / `cellClass` / `textAlign`, DMC component types (`AppShell`, `Skeleton`, `Alert`), Python `style` colors (winner cells, team stripe, player dots), empty/error copy, and fixture-status buckets (`synergy_inbounder/game_status.py`).
- Playwright smoke covers Home hero/filters/row links, Game non-Report tabs, Rotation Paper width, 375px and 1280px Home, and table-pan hosts (hidden scrollbar; overflow when the host has layout). Sampled AG Grid paint (`+/-` color, starter marker, `text-align`) is asserted in-test when those cells mount; Python contracts stay in the unit suite.

## Do not

- Do not add `basketball_rest.json` or `token_openapi.yml` to git.
- Do not write tests for 429 Retry-After, serialized live bundle, Shot Chart, play-type tables, or manual cell styling.
