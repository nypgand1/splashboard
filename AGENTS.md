# Agent entry

Read the matching spec before changing behavior or fixing a bug.

- Product behavior (pages, tabs, finished vs live, Rotation, English UI, Report canvas including GridStack / JS tables / DMC chrome / localStorage): `docs/spec.md`
- Synergy hosts, PLG and EASL organizations, official vs `/live`, token, roster, periodId, rate limits: `docs/synergy.md`
- Local run, tests, deploy, environment variables: `README.md`

## Daily

- Unit command: `python3 -m unittest discover -s tests -v`
- Browser smoke: `python3 -m pytest tests/e2e -q` (needs Chromium once: `python3 -m playwright install chromium`)
- Report PDF text extract (when `assets/report_canvas.js` PDF/font draw, `NotoSansTC-Regular.ttf`, or pdf spec change): `python3 -m pytest tests/e2e -q -m pdf_text -o addopts='-q --tb=short'`. Assert table-cell tokens (`PT` or `Min`, plus `20:00` or `Lin`). Score titles, page-header names, and notes do not count.
- Tests use mocks and small fixtures. They do not call live Synergy.
- Credentials travel only as `SYNERGY_PLG_CREDENTIAL_ID`, `SYNERGY_PLG_CREDENTIAL_SECRET`, `SYNERGY_EASL_CREDENTIAL_ID`, and `SYNERGY_EASL_CREDENTIAL_SECRET`. Do not commit them. Do not put them in `fly.toml` `[env]`.
- Do not `git push` or `fly deploy` unless asked.
- Git commit messages MUST be exactly a single line (one line only). Never use multi-line commit logs.
- UI strings are English.

- Resume unfinished work by querying `codebase-memory` MCP first and checking `git status -s` for modified file names. NEVER run bare `git diff` across the entire workspace. Inspect specific files (`git diff path/to/file.py`) only when strictly necessary. Do not reread whole page modules (`pages/game.py`, `pages/home.py`) when the targeted diff or graph already names the change.
- Save product decisions to `codebase-memory` by updating the ADR before ending the turn. Keep the test ladder in this file, out of the ADR.
- Grill or lock product decisions before editing. Implementation is cheap; a second Playwright run is not.
- When changing user-visible UI (layout, tabs, routing, rendered data), run the Playwright command in Verification cadence. A single static screenshot is not enough.

## Verification cadence

When the diff only changes `AGENTS.md`, skip the unit suite and Playwright.

1. After every code change, run the full unit suite (`python3 -m unittest discover -s tests -v`).
2. Run Playwright (`python3 -m pytest tests/e2e -q`) before `git commit`, or when the user says the UI work is done, whichever comes first. Skip a second run if this round already ran one. Non-UI changes (parser, cache, status helpers with no layout change) skip browser tests. Report first-paint, delete page, notes, PDF, and sticky live in `tests/e2e` with Home and Game.
3. Repair failures in this same session. Use the pytest short traceback and assertion message. Do not dump the page accessibility tree, inner HTML, or a screenshot into the transcript. Screenshots may be written under `scratch/` and left unread.

Acceptance for browser checks is the Playwright process exit code. That command is how this repo satisfies a generic instruction to verify in the browser. If the pytest traceback is not enough to fix the failure and a developer decision is required, ask the developer and wait. Leave chrome-devtools, Playwright MCP, and interactive browser-protocol sessions (page snapshots, per-click dumps, live `evaluate`) closed until that reply explicitly allows one.

## UI, DMC & AG-Grid contracts

- **Skill & Spec Reference**: When designing a new page/tab or performing major layout refactoring, read `.agents/skills/dash-dmc-design/SKILL.md` and `dash-dmc-ui/SKILL.md`. For specific color tokens (日式簡約 Braves 青空藍), typography, badge mappings, and page layouts, strictly follow `docs/spec.md`.
- **DMC Primitives & No DBC**: Use `dash_mantine_components as dmc` exclusively (`dmc.AppShell`, `dmc.Stack` for vertical rhythm, `dmc.Group` for inline actions, `dmc.SimpleGrid` for cards). Never import or use Dash Bootstrap Components (DBC), raw HTML container soup, or React hook patterns (`@mantine/*`).
- **Four States for Every View**: Every data view must explicitly handle: `Loading` (`dmc.Skeleton`), `Empty` (English copy + next step), `Error` (`dmc.Alert`, recoverable, no traceback), and `Success`.
- **Custom Cell Rendering**: Custom AG-Grid cell formatters and renderers reside in `assets/ag_grid_cells.js` via `window.dashAgGridComponentFunctions` (never uncompiled inline Python JS strings).
- **Unit Test Contracts**: Unit tests cover Python contracts: per-column center alignment on `headerClass` / `cellClass` / `textAlign`, DMC component types (`AppShell`, `Skeleton`, `Alert`), Python `style` colors (winner cells, team stripe, player dots), empty/error copy, and fixture-status buckets (`synergy_inbounder/game_status.py`).
- **Playwright Contracts**: `tests/e2e` covers Home filters, Last Update, and row links, Game tabs including Report visibility at 1280px and hide under 1280px, Report first-paint table, leave Report and return with tables still on the first paper, delete page (remaining papers keep tables; page list is one stack), toolbar width ≤ paper width, 36px toolbar icons, Report thead without a 2px brand rule, notes, PDF, sticky toolbar, Rotation Paper width, Rotation right lane at 1280px (`margin.r` 112, `margin.l` 112, full names, `3+ STOPS`), under 768px (`margin.r` 24, `margin.l` 56, right labels hidden, left ticks jersey-only, left tag `STOPS`) including after a period change, and restored at 768px, Game tabs at 375px as a 3-column button grid with 13px labels, 375px and 1280px Home, and table-pan hosts. Sampled AG Grid paint (`+/-` color, starter marker, `text-align`) is asserted in-test when those cells mount; Python contracts stay in the unit suite.
