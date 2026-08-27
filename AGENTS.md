# Agent entry

Read the matching spec before changing behavior or fixing a bug.

- Product behavior (pages, tabs, finished vs live, Rotation, English UI, Report canvas): `docs/spec.md`
- Report canvas decisions (GridStack, `dmc.Table`, localStorage, glass chrome, JS paint): `docs/adr/0001-report-canvas.md`
- Report v2 unit cases: `docs/report-tests.md`
- Synergy hosts, official vs `/live`, token, roster, periodId, rate limits: `docs/synergy.md`
- Local run, tests, deploy, environment variables: `README.md`

## Daily

- Test command: `python3 -m unittest discover -s tests -v`
- Tests use mocks and small fixtures. They do not call live Synergy.
- Credentials travel only as `SYNERGY_CREDENTIAL_ID` / `SYNERGY_CREDENTIAL_SECRET`. Do not commit them. Do not put them in `fly.toml` `[env]`.
- Do not `git push` or `fly deploy` unless asked.
- UI strings are English.
- Resume unfinished work from `git diff` / `git status` and the matching spec. Do not reread whole page modules (`pages/game.py`, `pages/home.py`) when the diff already names the change.
- Grill or lock product decisions before editing. Implementation is cheap; a second CDP pass on a full schedule grid is not.
- When changing user-visible UI (layout, tabs, routing, rendered data), walk the related pages in a browser. A single static screenshot is not enough.
- Verification cadence:
  - After every code change, run the full unit suite (`python3 -m unittest discover -s tests -v`).
  - CDP for that change covers only the surface that changed (compact `evaluate_script` JSON).
  - A sampled full CDP smoke runs before `git commit`, or when the user says the UI work is done, whichever comes first. Skip a second smoke if this round already ran one. Smoke is Home one row of badges/score, Game non-Report tabs switch, 900px and 1280px table pan with no visible scrollbar. `scripts/cdp_verify_report.py` only when Report canvas or PDF changes.
- UI & AG-Grid Verification SOP:
  - Custom cell formatting and dynamic styles must use `window.dashAgGridComponentFunctions` in `assets/report_canvas.js` (never uncompiled inline Python JS strings).
  - Unit tests cover Python contracts: per-column center alignment on `headerClass` / `cellClass` / `textAlign`, DMC component types (`AppShell`, `Skeleton`, `Alert`), Python `style` colors (winner cells, team stripe, player dots), empty/error copy, and fixture-status buckets (`synergy_inbounder/game_status.py`).
  - Browser CDP covers painted AG Grid `text-align` / `color`, JS cell renderers (`PlusMinusCell`, status badges, starter marker), DNP `colSpan`, RWD, and table pan. Sample rows and columns; do not dump every schedule or box-score row into the transcript.
  - Assert paint with `evaluate_script` that returns compact JSON. Poll load with `document.querySelectorAll('.ag-cell').length > 50`, then `getComputedStyle(el).color` / `textAlign` against expected RGB. Do not `wait_for` visible grid text and do not `take_snapshot` a Home or Box Score grid — those a11y trees are tens of kilobytes per call and stay in later turns.
  - Take a snapshot only to obtain a `uid` for a control you must click (tab, menu, score link). After CDP, edit in a fresh turn or session so grid dumps are not still in context.

## Do not

- Do not add `basketball_rest.json` or `token_openapi.yml` to git.
- Do not write tests for 429 Retry-After, serialized live bundle, Shot Chart, play-type tables, or manual cell styling.
