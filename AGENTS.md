# Agent entry

Read the matching spec before changing behavior or fixing a bug.

- Product behavior (pages, tabs, finished vs live, Rotation, English UI, Report canvas): `docs/spec.md`
- Report canvas decisions (GridStack, `dbc.Table`, localStorage, glass chrome, JS paint): `docs/adr/0001-report-canvas.md`
- Report v2 unit cases: `docs/report-tests.md`
- Synergy hosts, official vs `/live`, token, roster, periodId, rate limits: `docs/synergy.md`
- Local run, tests, deploy, environment variables: `README.md`

## Daily

- Test command: `python3 -m unittest discover -s tests -v`
- Tests use mocks and small fixtures. They do not call live Synergy.
- Credentials travel only as `SYNERGY_CREDENTIAL_ID` / `SYNERGY_CREDENTIAL_SECRET`. Do not commit them. Do not put them in `fly.toml` `[env]`.
- Do not `git push` or `fly deploy` unless asked.
- UI strings are English.
- When changing user-visible UI (layout, tabs, routing, rendered data), walk the related pages in a browser. A single static screenshot is not enough.
- UI & AG-Grid Verification SOP:
  - Custom cell formatting and dynamic styles must use `window.dashAgGridComponentFunctions` in `assets/report_canvas.js` (never uncompiled inline Python JS strings).
  - Headless browser CDP inspections must include hard assertions: assert `document.querySelectorAll('.ag-cell').length > 50` before validating cell contents, and assert `window.getComputedStyle(el).color` directly against expected RGB values.

## Do not

- Do not add `basketball_rest.json` or `token_openapi.yml` to git.
- Do not write tests for 429 Retry-After, serialized live bundle, Shot Chart, play-type tables, or manual cell styling.
