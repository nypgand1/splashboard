# Splashboard product spec

This file is the source of truth for product behavior. Tests and later feature work check against it.

## Scope

- Web dashboard for Taipei Fubon Braves schedule and single-game views.
- UI theme is **Braves Japanese Clean & Modern (日式簡約 Braves 青空藍)**, inspired by the official **Taipei Fubon Braves** visual identity:
  - `--bg`: `#f8fafc` (pure cool light white background)
  - `--navbar-bg`: `rgba(255, 255, 255, 0.9)` with `backdrop-filter: blur(16px)`
  - `--navbar-border`: `#00b4d8` (2px solid cyan bottom border)
  - `--brand`: `#0077b6` (Royal Blue) & `--brand-2`: `#00b4d8` (Braves Cyan)
  - `--thead-bg`: `#f1f5f9` (solid light gray-blue header with 2px `#00b4d8` bottom line)
  - `--thead-text`: `#0f172a` (deep slate header text)
  - `--row-alt`: `#fbfdff` (clean subtle zebra striping)
  - `--row-hover`: `#e0f2fe` (gentle cyan hover highlight)
  - `--card-bg`: `#ffffff` (white card containers with 10px radius & `#e2e8f0` border)
- Tabs: Top radius 10px, active tab filled with `linear-gradient(135deg, #0077b6, #00b4d8)` and pure white text.
- Page chrome is `dmc.AppShell` with `AppShellHeader` (navbar) and `AppShellMain` (pages). Theme tokens apply on the AppShell, not a separate Bootstrap frame. Navbar and main share one card: same width, fused corners. The header is **in document flow** (not `position: sticky` / `fixed`) so it never overlays the game banner or other content. Main padding is content padding only; do not rely on an AppShell header offset. `.app-shell` does not use `overflow: hidden` (that would become the sticky containing block and pin Report chrome inside the card instead of the viewport). Clip the card radius on the header (top) and `.app-main-content` (bottom) instead.
- Icons use `DashIconify` (Tabler). Bootstrap Icons is not loaded. Report page-delete is a DMC control on the paper shell Python renders, not a JS-inserted SVG.
- Tables & Alignment Rules (strictly unified across `dmc.Table` and `dag.AgGrid`):
  - Every header cell and data cell is **center-aligned**, including `Time`, `Player`, `Lineup`, `Lineups`, `Team`, and all numeric / time statistics.
  - Header cells and data cells must share the identical alignment for every column.
  - Team summary tables have a 3.5px left indicator bar (Home: `#0077b6`, Away: `#94a3b8`).
  - Player detail tables prefixed with 8px dot (Home: `#00b4d8`, Away: `#94a3b8`).
- Four states for every data view: loading (`dmc.Skeleton`), empty (English copy plus a next step), error (`dmc.Alert`, recoverable, no traceback), success (the table or chart).
- Responsive Layout (RWD):
  - **Mobile (≤ 768px)**: AppShell full bleed (`border-radius: 0; border: none; box-shadow: none;`), main `padding: 12px`, Tabs single-row smooth horizontal scrolling (`overflow-x: auto`).
  - Data tables (`dmc.Table` and `dag.AgGrid`) never clip columns. Box Score quarter and key-stat cards stack to one column below the `lg` breakpoint (~1200px). When a table is wider than its card, the first column stays sticky and the sheet pans horizontally: touch / trackpad native swipe, desktop mouse click-drag. `cursor: grab` / `grabbing` only if `scrollWidth > clientWidth`; tables that fit keep the default cursor. No overflow fade. Scrollbars are hidden (`scrollbar-width: none`). A drag that moved the sheet does not fire the following click (no sort, no score navigation). Do not hide columns to fit.
  - **Tablet (769px ~ 1024px)**: AppShell outer margin `12px`, `border-radius: 12px`.
  - **Desktop (> 1024px)**: AppShell outer margin `24px`, `max-width: 1440px`, `border-radius: 14px`, floating shadow `0 8px 30px rgba(15, 23, 42, 0.15)`.

## Pages

### Home `/`

- Show `dmc.Skeleton` while the current-season schedule loads.
- Layout, top to bottom: one hero `dmc.Paper` (the live-play game, else the next upcoming unplayed game; hidden if the season list is empty, or if there is no live and no upcoming game), quiet filters, then one list `dmc.Paper` of date-grouped compact rows. Theme Box Score Paper chrome (`withBorder`, `radius="md"`, `shadow="xs"`). Only the hero is banner-tall. Not an AG Grid. Not one Paper per game. Home has no `dcc.Interval`.
- The hero reuses `ui_kit.game_banner` and **shares the compact-row two-line composition** (full-width score line, then a tight centered meta cluster). Hero stays banner-tall via Paper padding and badge `size="md"` (list badges stay `size="xs"`). Do not put the badge in a right-hand column that steals width from the score well. Meta cluster is `date | time | venue` plus the badge (omit missing parts; no dangling `|`). Home hero date is `YYYY-MM-DD Day`; Game page banner date stays ISO `YYYY-MM-DD`. The hero ignores SHOW and GAME TYPE.
- **Filter controls**: Quiet `dmc.SegmentedControl` without verbose labels.
  - Game Type: Options are distinct `fixtureType` values this season (`Regular`, `Playoff`). Hidden when 0–1 distinct types.
  - Status: Chips ordered as `Upcoming` / `Finished` / `All`. Default **Upcoming**.
    - Upcoming = live-play ∪ unplayed (`SCHEDULED`, `IF_NEEDED`, `DRAFT`, `POSTPONED`, unknown/empty).
    - Finished = `FINISHED` / `CONFIRMED`.
    - All = everything, including void.
- **Status badge** on each compact row: badge **color is the bucket**; **label is the raw API `status`** (strip, no rewrite). `IN_PROGRESS` stays `IN_PROGRESS` (not `LIVE`). Empty status shows `UNKNOWN`.
  - Unplayed (`SCHEDULED`, `IF_NEEDED`, `DRAFT`, `POSTPONED`, unknown/empty): cyan (`#e0f2fe` + `#0284c7`).
  - Live-play (`PENDING`, `ABOUT_TO_START`, `WARM_UP`, `ON_PITCH`, `IN_PROGRESS`): coral (`#fee2e2` + `#dc2626`).
  - Finished (`FINISHED`, `CONFIRMED`): gray (`#f1f5f9` + `#475569`).
  - Void (`CANCELLED`, `BYE`, `ABANDONED`): colder gray (`#e2e8f0` + `#334155`).
- **Score** on each compact row uses `format_score_display`:
  - Finished, live-play, and `ABANDONED`: numeric scores render `Away Score : Home Score` (e.g. `88 : 79`); missing scores render `@`. Never fabricate `- : -`.
  - Unplayed and void: display `@` (Away @ Home convention).
- Compact row scan (list, not a mini-hero; same skeleton at 375px and 1280px):
  - Score line: Away team (`16px`, `fw=800`, right, ellipsis), Score / `@` (`22px`, `fw=900`, `#0077b6`), Home team (`16px`, `fw=800`, left, ellipsis). No status badge on this line.
  - Score well: two `min-width: 3ch` slots with `font-variant-numeric: tabular-nums`; away score right-aligned, home score left-aligned, colon centered. `@` uses the same well (3ch spacers either side of `@`). Never shrink the well to fit names. Never fixed `w=68` on the well or `w=140` on team names. Team names `flex: 1; min-width: 0`; single-line ellipsis; no wrap; no abbreviation table.
  - Meta cluster under the score, centered as one nowrap group: `HH:MM | Venue` (omit missing parts; no dangling `|`; ellipsis) glued to the status badge `size="xs"`. The cluster is not `space-between`. Meta text truncates; the badge does not shrink. Date is shown once in the group header `YYYY-MM-DD Day` (e.g. `2026-05-30 Sat`).
- **Sorting**: Upcoming games sort chronologically nearest first (ascending); Finished games sort newest completed first (descending).
- **Navigation**: the whole compact row is the hit target. Clickable iff `score_is_clickable`: live-play (including `PENDING`), finished, `ABANDONED`. The row is an `html.A` / `dmc.Anchor` to `/game/<fixtureId>`. Pointer cursor and `--row-hover: #e0f2fe` on clickable rows only. Unplayed and `CANCELLED`/`BYE` are not links (default cursor, no hover). No per-row Dash `n_clicks`. No `ScheduleScoreLink`.
- Filters only change the list. Empty filtered list (season itself is not empty): `No games in this view.` Next step: `Switch Game Type or Show.` Keep hero + filters; do not replace the page with the season-empty copy.
- On Synergy failure: `dmc.Alert` with `Failed to load games. Please try again later.` (HTTP 200, no unhandled exception).
- When the season list is empty: `No games available.` Next step: `Check back when the season schedule is published.`

### Game `/game/<game_id>`

Top tabs, left to right, rendered via `dmc.Tabs` with theme chrome (top radius 10px, active tab `linear-gradient(135deg, #0077b6, #00b4d8)` and white text). Tab icons use `DashIconify` (Tabler).

1. Box Score (tab_id: `tab-bs`)
2. Rotation (tab_id: `tab-rotation`)
3. Lineup Stats (tab_id: `tab-lineup`)
4. Play-By-Play (tab_id: `tab-pbp`)
5. Report (tab_id: `tab-report`) — **finished games only** (`FINISHED`, `CONFIRMED`) **and desktop** (`viewport >= 1280px`). Every other status, and any viewport under 1280px, hides the Report tab (`display: none`). If Report is active while hidden, switch to Box Score.

Box Score is the default (`value="tab-bs"`). Tab panes stay mounted. Hidden-tab render callbacks gate on `Input('tabs', 'value')`, return `no_update`, and do not rebuild children. Report also returns `no_update` on later Report tab selects while `report-pane-ready` is `1` (empty/error may rebuild).
- Quarter tables (points, fouls, timeouts) and team summary tables (four factors, advanced stats, key stats) are rendered via DMC `dmc.Table` (with `dmc.SimpleGrid` for responsive quarter stats layout).
- Player Stats and Lineup Stats tables use `dag.AgGrid` with `domLayout="autoHeight"` and sortable/filterable columns for interactive exploration.
- Report canvas tables are native HTML `<table>` painted in JS from `bs_store` / `lineup_store` (per ADR 0001). Box Score quarter and team summary tables stay `dmc.Table`. No `dbc.Table`, `dbc.Row`, or `dbc.Col` is used anywhere in the codebase. Do not put AG Grid inside Report blocks.
- Box Score quarter and team summary tables use `dmc.TableThead` / `dmc.TableTh` / `dmc.TableTd` (not raw `html.Th`).
- Loading uses `dmc.Skeleton`. Empty copy is `No data available.` Next step: `Open another game from Home.` Error uses `dmc.Alert` with `Failed to load this view. Please try again later.` (no traceback).
- The game banner date is ISO `YYYY-MM-DD`. It uses the same two-line `game_banner` composition as Home (score line, then `date | time | venue` plus badge `size="md"`). The banner status badge uses the same bucket colors and raw `status` label as Home (not `● LIVE`).

A `dcc.Store` that is `None` or invalid JSON is treated as an empty object. Callbacks must not crash.

## Fixture status buckets

Source enum: DataCore `FixturesModel.status` (14 values). Compare after strip. Unknown/empty is **unplayed**.

| Bucket | Statuses | `/live` | Game interval | Report tab | Home score |
|---|---|---|---|---|---|
| Unplayed | `SCHEDULED`, `IF_NEEDED`, `DRAFT`, `POSTPONED`, unknown, empty | no | off | hidden | `@`, not a link |
| Live-play | `PENDING`, `ABOUT_TO_START`, `WARM_UP`, `ON_PITCH`, `IN_PROGRESS` | yes | 30s | hidden | link: `A : H` or `@` |
| Finished | `FINISHED`, `CONFIRMED` | no | off | shown | link: `A : H` or `@` |
| Void | `CANCELLED`, `BYE` | no | off | hidden | `@`, not a link |
| Void (`ABANDONED`) | `ABANDONED` | no | off | hidden | link: `A : H` or `@` |

- Finished games freeze the report cache (no TTL rebuild).
- Live-play games: `/live` routes (except fixture roster and org persons/entities/venues); PBP HTTP cache and live report cache = 25 seconds; Play-By-Play and Rotation share that cadence.
- Unplayed and void use official routes and do not poll.

## Background warmup and prefetch

- **Game page Tab warmup**: For finished games (`FINISHED`, `CONFIRMED`), after `game_id` load, a background daemon thread precomputes Lineup `(4, 3, 2)` combinations and Rotation payload into `PostGameReport` memoized caches so tab switching is instantaneous.
- **Font load**: `NotoSansTC-Regular.ttf` (2.2MB) loads when the user exports PDF, not on every Game page render.
- **Home page 2-game prefetch**: Upon loading the Home schedule list, a background sequential worker pre-fetches and memoizes `PostGameReport` for up to the latest 2 games (safely limited to avoid live API rate limits). Any direct user page request preempts background warmup.

## Rotation

One Plotly object does both jobs: game flow (margin + runs) and simultaneous home/away lineups. Tablet/desktop is the primary canvas. Phone uses the same 3-panel chart (pan on X only). Do not split by team or period on a small screen.

Wrap chrome, top to bottom, all outside the graph Paper:

1. `Last Update` (first child of `#wrap-rotation`).
2. Controls: **Live** chip to the left of the period `dmc.SegmentedControl`, then **Show DNP** (default off).
3. Run chips (in `#pane-rotation` when any run exists).
4. Graph `dmc.Paper` (`withBorder`, `radius="md"`, `shadow="xs"`, `className="braves-card-wrapper"`, `overflow: hidden`).

Live chip: hidden when the game is not live-play. Filled = follow now; light = unfollowed. Clicking the chart unfollows. Clicking Live reattaches follow and snaps the playhead to now. The live-play 30s interval updates the playhead only while following.

Period chips: `All` plus each period label. `All` shows the full game (`x` from 0 to `game_end`). A period chip zooms the camera to that period's seconds, then the user can pan a fixed-width window across the game. Clamp the window to `[0, game_end]`. After pan, the selected chip follows the period with majority overlap (> 50%); otherwise keep the current chip.

Run chips: `1Q 08:24–05:10  10–2` (same-period labels omit the repeated quarter; color = side, home blue / away gray). Click always returns the camera to `All` and sets the playhead to the run start.

Playhead `T`: not a draggable object. Chart pan moves the camera, not `T`. Any click on the chart sets `T` to that clock time. Other `T` movers are labels only (period start, Run start, Live now). Finished games default `T` to game end. Live-play defaults to follow now.

On-court names stay on the Gantt Y axis (`#jersey full name`). At `T`, on-court rows get a `●` prefix; bench bars dim. There is no second 5v5 list. Minutes and `+/-` are hover-only.

Run detection: net margin delta ≥ 8, opponent scored ≤ 4 in the interval, wave breaks when the opponent scores 4 consecutive unanswered points. The end is the max-delta instant (not trailing opponent points). The start trims to the first scorer of the tightest qualifying suffix.

Chart:

- Shared X (game elapsed seconds) with 3 subplots: home Gantt (`#0077b6`), margin step-line (`hv`) with dual-color fill (home lead `rgba(0, 119, 182, 0.20)`, away lead `rgba(148, 163, 184, 0.25)`) plus full-height run `vrect` bands and score annotations, away Gantt (`#94a3b8`).
- Width 100%. `fig.layout.autosize = True`; do not set `layout.width`. Graph style width `100%`. `config`: `displayModeBar=False`, `responsive=True`, `scrollZoom=False`, `doubleClick=False`. `layout.dragmode='pan'`. X bounded (`minallowed=0`, `maxallowed=game_end`). Y-axes `fixedrange=True`.
- Margin ticks in steps of 5.
- Player rows sort by first time on court, then jersey; DNP rows last (hidden unless Show DNP).
- Period labels: 1–4 → `1Q`–`4Q`; official OT `periodId` 11 → `OT`, 12 → `2OT`; legacy `periodId` 5 still reads as `OT`.
- Stint hover: `#12 林志傑 (+7)` / `1Q 08:24 – 02:15 (06:09)`. Margin hover only on score-change events.

## Report

Tests: `tests/test_report_layout.py` (Python contracts). Browser: `tests/e2e` (Home, Game tabs, Report first-paint, leave/return, delete page, notes, PDF, sticky). One Playwright path; do not keep a second Report-only tree.

The Report tab is a multi-page A4 portrait canvas. Keep `PostGameReport` as the data source. Box Score, Rotation, Play-By-Play, and Lineup Stats stay as they are. Desktop only: hide the tab when `viewport < 1280px`. Default page 1 places a note beside the tables (right half). Other default notes sit below tables. Users may drag a note beside a table on any page.

### Paper and chrome

- Paper is A4 **portrait** (210mm × 297mm). Opaque white. No glass, no blur. Paper shadow is close to AppShell (`0 8px 24px rgba(15, 23, 42, 0.12)`), not a heavy drop shadow.
- Editor chrome (toolbar, page list, add-table menu, dialogs, page-delete) uses the same **Braves Japanese Clean & Modern** tokens as Home and Box Score. It is DMC (`dmc.ActionIcon`, `dmc.Button`, `dmc.Menu`, `dmc.Modal`). The A4 sheet stays print-white. There is no second “liquid glass” theme and no “Scheme A” name. Toolbar and page-list **rails** are solid `--thead-bg` `#f1f5f9` (no blur, no translucent white) with paper-matching shadow `0 8px 24px rgba(15, 23, 42, 0.12)`. Toolbar has a 2px `#00b4d8` bottom edge; page list has a 2px `#00b4d8` left edge. Quiet controls are white `#ffffff` with `#e2e8f0` border and `#1e293b` icons. Page-list idle buttons are that same white, not `#f1f5f9`.
- Report workspace background is `--bg` `#f8fafc` only (no radial wash).
- Toolbar has no "Report" title. Add note, Add image, Add table, and Reset layout are `DashIconify` Tabler icons (`tabler:notebook`, `tabler:photo`, `tabler:table`, `tabler:restore`) with `aria-label` `Add note` / `Add image` / `Add table` / `Reset layout`. Controls are 8px radius (same as the navbar Menu button), not pills. Add table opens a `dmc.Menu` of builtin tables (Player Stats before Lineup Stats). **PDF is the only filled primary** (`#0077b6`, white label). Hover on quiet controls: `#e0f2fe` / border `#00b4d8` / text `#0077b6`.
- The toolbar is the same width as one A4 paper (210mm) and left-aligned with the papers. The page list sits to the right of that column; do not center the toolbar independently of the paper. Page-list **top** aligns with the first paper top (toolbar height plus the gap under the toolbar), not with the toolbar top.
- Reset layout asks `Reset to the default layout? This cannot be undone.` with `Cancel` / `Reset` in `dmc.Modal`. Confirming restores `default_layout` (paper shells may remount; this action is destructive) and writes that JSON to `localStorage`. Stored layouts are not auto-discarded. Do not bump `LAYOUT_VERSION` to wipe them.
- Toolbar is `position: sticky; top: 8px`. Page list is sticky with `top = 8px + toolbar height + gap(toolbar bottom → first paper top)` (measure both; the toolbar’s `margin-bottom` does not stick as a viewport spacer). They stay on the **viewport** while the papers scroll. Navbar and game tabs stay in document flow and scroll away. Do not reserve a ~118px offset for a sticky header. The Add table menu stacks above the paper (`z-index`).
- Page list buttons match tabs: idle `#0f172a` on white `#ffffff` / `#e2e8f0`; current page `linear-gradient(135deg, #0077b6, #00b4d8)` and white text. No neon glow. `+` uses the same language. An overflowing page adds a 2px `#e63946` border on that button; the active fill stays the blue gradient.
- Every page has a **header template** that is not a block and cannot be dragged. The header is compact (small type, little padding) so the grid gets the rest of the 297mm:
  1. Away name, away score, `@`, home score, home name
  2. Date, time, and venue on **one** line (venue after time), with a slightly larger gap under the score line
- There is no page-number footer.
- Page list: add and switch only. There is **no** minus control on the page list. Delete a page with × at that paper's top-right: the × belongs to that A4 sheet, so that sheet is the one removed (not the scroll-spy page). Confirm with `dmc.Modal` (`keepMounted`) `Delete this page?` (`Cancel` / `Delete`). Do not use `window.confirm`. The last remaining page cannot be deleted (`min_pages` = 1). Default is **4 pages**. Users may add more.
- The current page is the paper with the highest intersection in the scroll viewport (scroll-spy). Add note, Add image, and Add table insert onto that current page: auto-place into empty grid cells that fit the block's `w`×`h` **inside the full paper grid** (the grid is stretched to the leftover paper height, not shrunk to existing widgets). If that paper has no such slot, request a **blank** page through the page-id store, then place there.
- New pages from the page-list `+` are also blank (no default notes block).
- Layout engine: GridStack (12 columns). Blocks drag and resize. Resize handle is **SE only** (GridStack `handles: 'se'`). Table drag handles sit to the left of the block title (in the same row, sized to max height). Note/image handles stay overlaid at the top-left and do not consume a grid row. Table and note SE resize change `w` / `h` independently. Image SE resize keeps the photo’s aspect ratio (`w` and `h` coupled). A fitting block (`h` ≤ leftover paper rows) cannot be dragged or resized so that its box leaves the A4 sheet (`maxW` / `maxH` = remaining cells; drop position clamped). Content is never shrunk to fit: `minH` / `minW` stay at content size. First paint / Add table may still overflow when content is taller than the sheet (red ring); those oversized blocks may only move on X, with `y` pinned to 0, and cannot be resized smaller than content. Default layout is compacted on first paint and after Reset; later user moves are left alone. Stored layouts are kept as saved (no auto-replace).
- Block bodies do not scroll. `overflow` is `hidden`. Builtin table blocks size their grid `h` to `ceil((title row + table + 4px inset) / cell)` with **no extra fudge**. Every `table_key` uses this hug-content rule. Do not stretch body rows to fill leftover snap (0–41px). Paper leftover below the stack stays whitespace. Height measurement clones the card off-DOM with `report-block-card` (plus `report-block-card-table` for tables) and `inset: auto`. Do not copy `grid-stack-item-content` onto that clone (`inset: 0` would stretch it to the viewport). Tables paint **all** rows (no `maxLineupRows` slice). Note blocks use `contenteditable` with `document.execCommand` (not Tiptap): empty placeholder `Notes`, default 2 grid rows (page 1 default note is taller: `h` matches the left stack), grow or shrink with content (Enter grows, deleting lines shrinks, **minimum 1**). Typing changes **height only**; `w` stays at the layout value or the user's last SE resize. persist must not fall back to `w=6` while `gs-w` or `data-w` is set. Enter, paste, or wrap that would make the note taller than leftover paper is **rejected** (no newline / the edit does not apply). Images place at natural CSS pixel size if that grid-snapped box fits the remaining empty cells; otherwise the largest proportional size in remaining cells. New page only if the current paper already overflows A4 or no remaining cell fits the min proportional box. The **sheet** stays 297mm. If any `.grid-stack-item` border-box sits outside the paper border-box (any edge, 4px tolerance), that paper and its page-list button get a 2px `#e63946` ring (`no-print`; current page keeps the blue gradient). Internal nowrap clip inside a block that is still on the sheet is not paper overflow. Full lineup combinations also live on the Lineup Stats tab.
- Note text-formatting toolbar lives in the **Report toolbar area** (not inside each Note block). It appears when a Note is focused and controls Bold, Italic, Underline, Strikethrough, Bullet List, Ordered List, Text Color, and Highlight. Active format buttons use `#0077b6`, not indigo. Text Color and Highlight are button menus: clicking opens a dropdown popup containing a single row of 8 Flat Design preset colors with tight spacing (Red `#e74c3c`, Orange `#e67e22`, Yellow `#f1c40f`, Green `#2ecc71`, Blue `#3498db`, Purple `#9b59b6`, White `#ffffff`, Reset Black `#000000`) plus a custom color picker input. Those eight colors are annotation, not brand tokens. The toolbar is hidden when no Note is focused.
- Bullet List and Ordered List support multi-level nested lists. Pressing `Tab` indents the current item into a sub-list; pressing `Shift + Tab` outdents back to the parent list. Bullet List markers cascade as `disc` (Level 1) → `circle` (Level 2) → `square` (Level 3+). Ordered List numbers cascade as `decimal` (1, 2, 3) → `lower-alpha` (a, b, c) → `lower-roman` (i, ii, iii).
- Note `content` is stored as **HTML**. Old plain-text content from previous versions is wrapped in `<p>` when painted.
- There is no `spacer` on any page.

### Block types

| `type` | Role |
|---|---|
| `builtin_table` | Read-only table from another tab's computed data |
| `text` | Editable notes |
| `image` | User-uploaded raster, stored as a data URL |

Allowed `table_key` values: `score_group`, `t_adv_df`, `t_df`, `k_df`, `lineup_home`, `lineup_away`, `p_df_home`, `p_df_away`.

There is no combined `lineup_dict` table_key. Home and away Player Stats are separate blocks on the same default page. Home and away Lineup Stats are separate blocks on the same default page.

Out of v1: Shot Chart, play-type tables, manual cell fill/bold, auto red/green thresholds, editing builtin values.

### Default layout

Note slots start as **empty** `text` blocks. Home tables come before away.

1. Header + Score and Four Factors stacked in the left 6 columns (`w=6`); one empty note in the right 6 columns (`x=6`, `w=6`, `y=0`) with `h` matching the left stack. No spacer. Score nowrap may clip at the half-width block edge.
2. Header + Team Stats + Key Stats + empty text below. Leftover paper stays **whitespace**. Do not stretch those tables (or the notes) to fill the sheet.
3. Header + home Player Stats + away Player Stats (home above away, full width). No default note. If the stack exceeds A4, the overflow ring lights. Do not shrink type or drop rows.
4. Header + home Lineup Stats + away Lineup Stats (home above away, full width). No default note. Same overflow contract. Paint every lineup row.

### Persistence and images

- Layout JSON lives in `localStorage` under `splashboard.report.layout.{game_id}`.
- Images: the browser validates MIME and decoded size, then inserts a data URL into that JSON. The Fly machine does not write files. Python `validate_image_upload` stays as the unit-test contract for the same rules.
- Accept JPEG, PNG, WebP. Reject when decoded bytes exceed 1_000_000. Reject empty, SVG, GIF.

### Paint ownership

Ownership is split so each layer does what the other cannot. This is not leftover JS.

- **Python / DMC** owns editor chrome and **paper shells**: toolbar, page list, dialogs, page-delete, each paper’s header + empty grid host. JS `document.createElement('button')` cannot mount DMC. `lineup_store` (size 5 only) is precomputed at page load (triggered by `game_id`, not by tab switch). Report only uses 5-player lineups; the Lineup tab computes other sizes (4/3/2) on demand via its own callback.
- **JS** owns **paper interiors**: GridStack, native HTML tables, notes, images, PDF, `localStorage` block layout. Hydrate **the current page only**, looking up blocks by **page id** (not array index). Scroll or page-list click hydrates the next paper. Unhydrated papers keep 297mm height and header only.
- `Output('pane-report', 'children')` runs on the **first** Report open for this game, and when `report-pane-ready` is not `1` (empty/error, so a later-ready store can paint). It does not run on later tab returns while that store is `1`, nor on drag, note edits, add block, add image, add page, or delete page. Replacing that tree remounts React: GridStack dies, notes lose focus, scroll resets, papers unhydrate. That is a remount, not a CSS flicker. DMC does not cause it; writing `pane-report` children does. Stored-layout boot waits for **new** paper nodes after `op: reset`, not the pre-reset count. `persistLocal` does not run while Report is `display: none`, and does not overwrite a non-empty `localStorage` layout when the DOM has no grid items. Showing Report again rehydrates the current paper if GridStack items were dropped while the pane was hidden, or if the workspace remounted.
- Page add/delete go through a `report-page-cmd` store (`add` / `delete` / `reset`). Add Patch-appends one shell. Delete Patch-removes one index. Reset may replace shells. The page-list Output is **button children only**, never a nested `dmc.Stack`. JS does not `createElement` paper shells or page buttons.
- Add note, Add image, and Add table stay JS: insert onto the current page (scroll-spy), auto-placed. If that paper has no slot, JS requests one new page through the page-id store, then places the block after the new shell exists. Add table paints from store JSON; there are no hidden table templates.
- Do not mount AG Grid in Report blocks. Do not clone Player / Lineup tab grids. Do not put `dmc.Table` inside GridStack. Do not DMC the toolbar and leave the page list as JS HTML.
- `fitAllTableBlocks` batches DOM measurements on the hydrated page: all `scrollHeight` reads run first, then all `grid.update` writes run.
- Reset may remount paper shells (user confirmed destructive). It restores `default_layout` and writes `localStorage`. Stored layouts are not auto-replaced.
- GridStack and jsPDF load when Report hydrates, not on Home. AG Grid cell renderers live in `assets/ag_grid_cells.js`.
- There is no Fly volume; machines auto-stop. Layout and images live in `localStorage` as JSON + data URLs. PDF is jsPDF selectable text (not a whole-page html2canvas raster). Noto Sans TC loads on export.

**Rejected (do not revive):** Sortable instead of GridStack; AG Grid or `dmc.Table` inside GridStack; Tabulator; cloning Player/Lineup AG Grid; Tiptap CDN or `dmc.RichTextEditor` for notes; a second liquid-glass editor theme; `Output('pane-report', 'children')` on layout mutations; JS-created page buttons or paper shells; Python owning GridStack / table cells / notes.

### PDF

- Primary: jsPDF walks each paper's DOM (header, table cells, notes, images) and writes **selectable text**, one PDF page per canvas page, portrait A4. Export hydrates one paper at a time, draws it, then continues. Layout is close to the screen, not pixel-identical. Notes are parsed via a Rich Text DOM Walker:
  - Paragraphs and multi-level lists (`<ul>`, `<ol>`) maintain hierarchical indentation (approx. 5mm per level).
  - List markers are drawn according to hierarchy: Bullet lists render `disc`, `circle`, `square`; Ordered lists render formatted numbers (`1.`, `a.`, `i.`).
  - Formatting spans parse `color` (`<font color="...">` or CSS `color`), highlight background (`style="background-color: ..."` filled via `pdf.rect`), bold/italic font styles, and draw underlines or strikethrough lines.
  - Text segments are automatically word-wrapped. A line is drawn when its top is inside the note box (`cursorY < maxY`). `maxY` is the note box bottom, capped at the paper 297mm. Do not skip a line because less than 40% of a line-height remains. Lines whose top is past `maxY` are not drawn.
- CJK uses Noto Sans TC bundled at `/assets/NotoSansTC-Regular.ttf` (same-origin, no CDN). ASCII can share that font or Helvetica. Uploaded images are embedded as PNG. There is no Bold file: cells and titles with `font-weight >= 600` are drawn twice, offset 0.15mm. PDF maps the paper with separate `scaleX = 210/width` and `scaleY = 297/height`; table text is vertically centered in the cell (`baseline: middle`). Starter `S` is a stroked circle (not the `○` glyph). Captioned-block title dots are filled circles at `.report-block-title-dot`.
- Filename is `{YYYYMMDD}.pdf` from the game date. If the date is missing, `splashboard-report.pdf`.
- Tables keep the on-screen look (striped, bordered, 9px, `text-nowrap`). Do not restyle tables for a separate print theme. Wide tables may clip at the block edge.
- Do not rasterize the whole paper with html2canvas. Browser print is the fallback if the font or jsPDF fails.
- While export runs, the PDF button is disabled and `aria-busy` is true so a second click does not start another export. If any paper is overflowing A4, PDF opens `dmc.Modal` first: `This export will crop content that sits outside A4.` with `Cancel` / `Export`. Confirming still writes portrait A4 and clips at 297mm. The overflow ring is `no-print` and is not drawn in the PDF.
- Capture the paper only (`no-print` on chrome, handles, page-delete, dialogs).
- Gated `pdf_text` extract must find table-cell tokens: header `PTS` or `Min`, plus tbody `20:00` or player `Lin`. Block titles (`Score`), page-header team names, and notes do not count.

### Tables in Report

- Report builtin tables are native HTML `<table>` (`className="text-nowrap report-js-table"`): striped, bordered, `text-nowrap`, read-only. Python does not emit per-cell Dash components.
- Semantic paint matches the other Game tabs at A4 density: grouped 2PT / 3PT / FT / REB headers. **4 FACTORS** grouped header is only on the team Four Factors table (`t_adv_df`). Player Stats and Lineup Stats paint `eFG%` as a standalone column (no 4 FACTORS band). Team winner cells bold `#0077b6`; team stripe on the name column; `+/-` positive `#0077b6`, negative `#e63946`, zero `#64748b`; **`PM` is a `12-10` string and is not color-coded** (Box Score already colors only `+/-`); starter `S` paints `○`; DNP `Min` spans remaining columns; player and lineup names `fw=700`; zero stats blank as on Box Score / Lineup. No pinned columns, sort, or filter on the paper.
- Report table `thead` uses `--thead-bg` `#f1f5f9` and the same 1px `#e2e8f0` border as body cells. Do not paint a 2px brand underline on paper tables. Box Score `dmc.Table` / AG Grid keep the 2px `#00b4d8` header edge. Cell padding and type stay A4-dense (9px / 2px).
- Captioned blocks (`p_df_home`, `p_df_away`, `lineup_home`, `lineup_away`) title as `[8px dot] {team} | Player Stats` or `| Lineup Stats`. Home dot `#00b4d8`, away `#94a3b8` (same as Box Score). Title color `#0f172a`, `fw=800`. Other tables keep generic titles (`Score`, `Team Stats`, …). The Add table menu still lists `Home Player Stats` / `Away Player Stats` / lineup labels.
- Play-By-Play keeps AG Grid. Do not put AG Grid inside Report blocks.
- Tighter font and padding than Box Score so a table can sit in an A4 block. Report lineup tables paint every row and size the block to that content; shrinking below that content is blocked. If the block then sticks out of A4, the paper overflow ring lights. The paper does not scroll inside a block.
- Team Stats and Player Stats `Min` values are `M:SS` (e.g. `8:21`, `0:06`). Box Score uses the same values.
- Box Score, Report canvas, and PDF Player Stats share one sort: `+/-` descending, then PTS descending, then jersey `#` ascending. DNP rows last. The starter `S` marker stays on the row and does not pin starters to the top.

## Lineup Stats

- Wrap chrome, top to bottom: `Last Update`, then a quiet size `dmc.SegmentedControl` (no Combination label), then the pane. Options are `5 Players`, `4 Players`, `3 Players`, `2 Players`. Default `5`. The control is `fullWidth` and keeps id `lineup_size_dropdown`.
- `lineup_store` precomputes size 5 at page load. Sizes 4/3/2 compute on demand in the Lineup tab callback, then render through the same `render_lineup_children` path (home/away section dots, Lineup filter, size-based column widths, pagination). Do not paint a second Title-only table.
- 5-man lineups are displayed completely without pagination; 2/3/4-man lineups paginate with 20 rows per page.
- Lineup labels are player **names** from the id table, ordered by jersey shirt number (ascending), joined with hyphens (e.g. `林志傑-張宗憲`). Jersey is the sort key, not the displayed text.
- On the Game Lineup Stats AG Grid (not Report JS tables), the Lineup column is pinned left, `fw=700`, centered, no `flex: 1`. Width follows lineup size: 2 → min 140 / width 150; 3 → 180 / 190; 4 → 220 / 230; 5 → 260 / 270. Names wrap inside the cell (`wrapText` + row `autoHeight`); they do not ellipsis. At viewport `max-width: 768px` the pinned Lineup column caps at 160px so Min, `+/-`, and PTS stay on-screen; wrapped names grow the row height.
- Lineup table columns: `Lineup`, `Min`, `+/-`, `2M`, `2A`, `2FG%`, `3M`, `3A`, `3FG%`, `FTM`, `FTA`, `FT%`, `OR`, `DR`, `REB`, `AST`, `TO`, `ST`, `BL`, `PF`, `FD`, `PTS`, `eFG%`, `PM`.
- Zero-value noise reduction: Except for `+/-` (which shows neutral gray `0`), numeric 0 statistics are rendered blank `''` (including shot `M` / `A`). Shot-group `%` columns (`2FG%`, `3FG%`, `FT%`) display `''` when that group has 0 attempts and `0.0%` when attempts `> 0` and made is 0. `eFG%` is `''` when `(2A+3A) == 0` and `0.0%` when `(2A+3A) > 0` and `(2M+3M) == 0`.

## Box Score DNP & Zero-Value Rules

- DNP (Did Not Play) rostered players are included and sorted at the bottom of the bench.
- In AG-Grid, DNP player rows display `DNP` in the `MIN` column with a full-row span (`colSpan`) across subsequent stats columns.
- Numeric statistics with a value of 0 are left blank `''` (including PTS, REB, AST, and shot `M` / `A`). Shot-group `%` (`2FG%`, `3FG%`, `FT%`) stay `''` when attempts are 0 and show `0.0%` when attempts `> 0` and made is 0. Game AG Grid, Report paper, and PDF share this Python value. Report JS must not treat a `%` string as a blank zero.
- `eFG%` is blank when `FGA == 0` (or DNP) and `0.0%` when `(2A+3A) > 0` and `(2M+3M) == 0`.
- `USG%` is blank when unplayed/DNP and `0.0%` when played with 0 usage.
- `+/-` displays pure numbers without `+` prefix (positive in royal blue `#0077b6`, negative in coral red `#e63946`, zero in gray `#64748b`).

## Config and deploy

- Public hosts, org id, and season ids live in git (`synergy_inbounder/settings.py`).
- Credentials come only from `SYNERGY_CREDENTIAL_ID` and `SYNERGY_CREDENTIAL_SECRET`.
- Missing credentials must fail clearly at token fetch. Do not POST empty strings.
- Default tests do not call live Synergy.
