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
- Page chrome is `dmc.AppShell` with `AppShellHeader` (navbar) and `AppShellMain` (pages). Theme tokens apply on the AppShell, not a separate Bootstrap frame. Navbar and main share one card: same width, fused corners. The header is **in document flow** (not `position: sticky` / `fixed`) so it never overlays the game banner or other content. Main padding is content padding only; do not rely on an AppShell header offset.
- Icons use `DashIconify` (Tabler). Bootstrap Icons is not loaded. Report page-delete buttons created in JS use an inline SVG.
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
5. Report (tab_id: `tab-report`) — **finished games only** (`FINISHED`, `CONFIRMED`). Every other status hides the Report tab (`display: none`). If Report is active while the status is not finished, switch to Box Score.

Box Score is the default (`value="tab-bs"`). Tab panes stay mounted. Hidden-tab render callbacks gate on `Input('tabs', 'value')`, return `no_update`, and do not rebuild children.
- Quarter tables (points, fouls, timeouts) and team summary tables (four factors, advanced stats, key stats) are rendered via DMC `dmc.Table` (with `dmc.SimpleGrid` for responsive quarter stats layout).
- Player Stats and Lineup Stats tables use `dag.AgGrid` with `domLayout="autoHeight"` and sortable/filterable columns for interactive exploration.
- Report canvas tables strictly use `dmc.Table` (per ADR 0001) for stable A4 rendering and PDF export. No `dbc.Table`, `dbc.Row`, or `dbc.Col` is used anywhere in the codebase.
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

## Deferred (later discussion)

- Report canvas DMC-ification beyond toolbar icons (`html.Th` / GridStack cloneNode).

## Background warmup and prefetch

- **Game page Tab warmup**: For finished games (`FINISHED`, `CONFIRMED`), after `game_id` load, a background daemon thread precomputes Lineup `(4, 3, 2)` combinations and Rotation payload into `PostGameReport` memoized caches so tab switching is instantaneous.
- **Font prefetch**: In Game pages, `NotoSansTC-Regular.ttf` (2.2MB) is preloaded asynchronously via JS upon initial render, eliminating download latency when clicking PDF export.
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

Decisions: `docs/adr/0001-report-canvas.md`. Tests: `tests/test_report_layout.py`.

Throw away the previous Report canvas (Sortable, `window.print()` as the primary PDF path, match-info as a draggable block). Keep `PostGameReport` as the data source. Box Score, Rotation, Play-By-Play, and Lineup Stats stay as they are.

### Paper and chrome

- Paper is A4 **landscape** (297mm × 210mm). Opaque white. No glass, no blur.
- Editor chrome (toolbar, page list, add-block palette, block handles, page-delete) uses Liquid glass. Other tabs and the navbar use the Japanese Clean & Modern theme inside `dmc.AppShell`.
- Toolbar has no "Report" title. Add note, Add image, Add table, and Reset layout are `DashIconify` Tabler icons (`tabler:notebook`, `tabler:photo`, `tabler:table`, `tabler:restore`) with `aria-label` `Add note` / `Add image` / `Add table` / `Reset layout`. Add table opens a Liquid-glass menu of builtin tables (Player Stats before Lineup Stats). PDF stays a text button.
- The toolbar is the same width as one A4 paper (297mm) and left-aligned with the papers. The page list sits to the right of that column; do not center the toolbar independently of the paper.
- Reset layout asks `Reset to the default layout? This cannot be undone.` with `Cancel` / `Reset`. Confirming replaces the canvas with `default_layout` and writes that JSON to `localStorage`. Stored layouts are not auto-discarded.
- Icons across the app use `DashIconify` (Tabler). The Report page-delete control that JS inserts uses an inline SVG. Bootstrap Icons is not loaded.
- Toolbar and page list are `position: sticky` so they stay visible while the papers scroll. The Add table menu stacks above the paper (`z-index`).
- Every page has a **header template** that is not a block and cannot be dragged. The header is compact (small type, little padding) so the grid gets the rest of the 210mm:
  1. Away name, away score, `@`, home score, home name
  2. Date, time, and venue on **one** line (venue after time), with a slightly larger gap under the score line
- There is no page-number footer.
- Page list: add and switch only. There is **no** minus control on the page list. Delete a page with × at that paper's top-right, after `Delete this page?` (`Cancel` / `Delete`). The last remaining page cannot be deleted (`min_pages` = 1). Default is **5 pages**. Users may add more.
- The current page is the paper with the highest intersection in the scroll viewport (scroll-spy). Add note, Add image, and Add table insert onto that current page: auto-place into empty grid cells that fit the block's `w`×`h` **inside the full paper grid** (the grid is stretched to the leftover paper height, not shrunk to existing widgets). If that paper has no such slot, add a **blank** page and place there.
- New pages from the page-list `+` are also blank (no default notes block).
- Layout engine: GridStack (12 columns). Blocks drag and resize. Table drag handles sit to the left of the block title (in the same row, sized to max height). Note/image handles stay overlaid at the top-left and do not consume a grid row. Default layout is compacted on first paint and after Reset; later user moves are left alone. Stored layouts are kept as saved (no auto-replace).
- Block bodies do not scroll. `overflow` is `hidden`. Builtin table blocks size their grid `h` to the title row (title and drag handle on the same row) plus the table. Note blocks use a JS-side Tiptap editor (`contenteditable` div with Tiptap mounted in JS): empty placeholder `Notes`, default 2 grid rows, grow or shrink with content (Enter grows, deleting lines shrinks, minimum 2). Rows that still do not fit the A4 sheet are clipped by the paper. The sheet stays 210mm.
- Note text-formatting toolbar lives in the **Report toolbar area** (not inside each Note block). It appears when a Note is focused and controls Bold, Italic, Underline, Strikethrough, Bullet List, Ordered List, Text Color, and Highlight. Text Color and Highlight are button menus: clicking opens a dropdown popup containing a single row of 8 Flat Design preset colors with tight spacing (Red `#e74c3c`, Orange `#e67e22`, Yellow `#f1c40f`, Green `#2ecc71`, Blue `#3498db`, Purple `#9b59b6`, White `#ffffff`, Reset Black `#000000`) plus a custom color picker input. The toolbar is hidden when no Note is focused.
- Bullet List and Ordered List support multi-level nested lists. Pressing `Tab` indents the current item into a sub-list; pressing `Shift + Tab` outdents back to the parent list. Bullet List markers cascade as `disc` (Level 1) → `circle` (Level 2) → `square` (Level 3+). Ordered List numbers cascade as `decimal` (1, 2, 3) → `lower-alpha` (a, b, c) → `lower-roman` (i, ii, iii).
- Note `content` is stored as **HTML** (Tiptap native output). Old plain-text content from previous versions is forward-compatible: Tiptap renders plain text as a `<p>` paragraph.
- Tiptap and its extensions load via CDN `<script>` tags. Python renders `contenteditable` divs; JS mounts Tiptap editors on them after GridStack init. This avoids React component lifecycle conflicts with GridStack `cloneNode`. All Notes—including those added dynamically via JS—get a Tiptap editor mounted in JS.
- There is no `spacer` on any page.

### Block types

| `type` | Role |
|---|---|
| `builtin_table` | Read-only table from another tab's computed data |
| `text` | Editable notes |
| `image` | User-uploaded raster, stored as a data URL |

Allowed `table_key` values: `score_group`, `t_adv_df`, `t_df`, `k_df`, `lineup_home`, `lineup_away`, `p_df_home`, `p_df_away`.

There is no combined `lineup_dict` table_key. Home and away lineup tables are separate blocks on separate default pages.

Out of v1: Shot Chart, play-type tables, manual cell fill/bold, auto red/green thresholds, editing builtin values.

### Default layout

Note slots start as **empty** `text` blocks.

1. Header + Score + empty text + Four Factors. No spacer.
2. Header + Team Stats + Key Stats + empty text. Leftover paper stays **whitespace**. Do not stretch those tables (or the notes) to fill the sheet. Lineup is not on this page.
3. Header + home Player Stats + away Player Stats + empty text
4. Header + home Lineup Stats + empty text
5. Header + away Lineup Stats + empty text

### Persistence and images

- Layout JSON lives in `localStorage` under `splashboard.report.layout.{game_id}`.
- Images: the browser validates MIME and decoded size, then inserts a data URL into that JSON. The Fly machine does not write files. Python `validate_image_upload` stays as the unit-test contract for the same rules.
- Accept JPEG, PNG, WebP. Reject when decoded bytes exceed 1_000_000. Reject empty, SVG, GIF.

### Paint ownership

- `lineup_store` (size 5 only) is precomputed at page load (triggered by `game_id`, not by tab switch). Report only uses 5-player lineups; the Lineup tab computes other sizes (4/3/2) on demand via its own callback.
- Python paints the Report pane **once** when the tab opens. `lineup_store` is a `State` (not an `Input`), so updating it does **not** rebuild `pane-report`. It does **not** rebuild `pane-report` when `report_layout_store` changes either.
- After that single paint, add note, add page, remove page, remove block, add table, and add image mutate GridStack in JS and write `localStorage` only.
- Add note, Add image, and Add table insert onto the current page (scroll-spy), auto-placed; a full page adds a new page first.
- Add table clones a hidden `dmc.Table` template for that `table_key`. Do not mount a new AG Grid.
- `fitAllTableBlocks` batches DOM measurements: all `scrollHeight` reads run first, then all `grid.update` writes run, to avoid interleaved layout reflows.
- Reset layout is clientside (default JSON kept in the pane; no Python rebuild).

### PDF

- Primary: jsPDF walks each paper's DOM (header, `dmc.Table` cells, notes, images) and writes **selectable text**, one PDF page per canvas page, landscape A4. Layout is close to the screen, not pixel-identical. Notes are parsed via a Rich Text DOM Walker:
  - Paragraphs and multi-level lists (`<ul>`, `<ol>`) maintain hierarchical indentation (approx. 5mm per level).
  - List markers are drawn according to hierarchy: Bullet lists render `disc`, `circle`, `square`; Ordered lists render formatted numbers (`1.`, `a.`, `i.`).
  - Formatting spans parse `color` (`<font color="...">` or CSS `color`), highlight background (`style="background-color: ..."` filled via `pdf.rect`), bold/italic font styles, and draw underlines or strikethrough lines.
  - Text segments are automatically word-wrapped and respect block boundaries (`maxY` clipping at paper bottom).
- CJK uses Noto Sans TC bundled at `/assets/NotoSansTC-Regular.ttf` (same-origin, no CDN). ASCII can share that font or Helvetica. Uploaded images are embedded as PNG.
- Filename is `{YYYYMMDD}.pdf` from the game date. If the date is missing, `splashboard-report.pdf`.
- Tables keep the on-screen look (striped, bordered, 11px, `text-nowrap`). Do not restyle tables for a separate print theme.
- Do not rasterize the whole paper with html2canvas. Browser print is the fallback if the font or jsPDF fails.
- While export runs, the PDF button is disabled and `aria-busy` is true so a second click does not start another export.
- Capture the paper only (`no-print` on chrome, handles, page-delete, dialogs).

### Tables in Report

- Report builtin tables are `dmc.Table` (`className="text-nowrap report-dmc-table"`): striped, bordered, `text-nowrap`, read-only.
- Play-By-Play keeps AG Grid. Do not put AG Grid inside Report blocks.
- Tighter font and padding than Box Score so a table can sit in an A4 block. Overflowing rows are clipped by the paper, not scrolled inside the block.
- Team Stats and Player Stats `Min` values are `M:SS` (e.g. `8:21`, `0:06`). Box Score uses the same values.
- Box Score, Report canvas, and PDF Player Stats share one sort: `+/-` descending, then PTS descending, then jersey `#` ascending. DNP rows last. The starter `S` marker stays on the row and does not pin starters to the top.

## Lineup Stats

- Wrap chrome, top to bottom: `Last Update`, then a quiet size `dmc.SegmentedControl` (no Combination label), then the pane. Options are `5 Players`, `4 Players`, `3 Players`, `2 Players`. Default `5`. The control is `fullWidth` and keeps id `lineup_size_dropdown`.
- `lineup_store` precomputes size 5 at page load. Sizes 4/3/2 compute on demand in the Lineup tab callback, then render through the same `render_lineup_children` path (home/away section dots, Lineup filter, size-based column widths, pagination). Do not paint a second Title-only table.
- 5-man lineups are displayed completely without pagination; 2/3/4-man lineups paginate with 20 rows per page.
- Lineup labels are player **names** from the id table, ordered by jersey shirt number (ascending), joined with hyphens (e.g. `林志傑-張宗憲`). Jersey is the sort key, not the displayed text.
- On the Game Lineup Stats AG Grid (not Report `dmc.Table`), the Lineup column is pinned left, `fw=700`, centered, no `flex: 1`. Width follows lineup size: 2 → min 140 / width 150; 3 → 180 / 190; 4 → 220 / 230; 5 → 260 / 270. Names wrap inside the cell (`wrapText` + row `autoHeight`); they do not ellipsis. At viewport `max-width: 768px` the pinned Lineup column caps at 160px so Min, `+/-`, and PTS stay on-screen; wrapped names grow the row height.
- Lineup table columns: `Lineup`, `Min`, `+/-`, `2M`, `2A`, `2FG%`, `3M`, `3A`, `3FG%`, `FTM`, `FTA`, `FT%`, `OR`, `DR`, `REB`, `AST`, `TO`, `ST`, `BL`, `PF`, `FD`, `PTS`, `eFG%`, `PM`.
- Zero-value noise reduction: Except for `+/-` (which shows neutral gray `0`), all 0 statistics are rendered blank `''`. `eFG%` is calculated for lineups and displays `''` when `FGA == 0` or `0.0%` when `FGA > 0` with 0 made.

## Box Score DNP & Zero-Value Rules

- DNP (Did Not Play) rostered players are included and sorted at the bottom of the bench.
- In AG-Grid, DNP player rows display `DNP` in the `MIN` column with a full-row span (`colSpan`) across subsequent stats columns.
- Numeric statistics with a value of 0 are left blank `''` (including PTS, REB, AST, shot breakdowns, and percentages).
- `eFG%` is blank when `FGA == 0` (or DNP) and `0.0%` when `FGA > 0` and 0 made.
- `USG%` is blank when unplayed/DNP and `0.0%` when played with 0 usage.
- `+/-` displays pure numbers without `+` prefix (positive in royal blue `#0077b6`, negative in coral red `#e63946`, zero in gray `#64748b`).

## Config and deploy

- Public hosts, org id, and season ids live in git (`synergy_inbounder/settings.py`).
- Credentials come only from `SYNERGY_CREDENTIAL_ID` and `SYNERGY_CREDENTIAL_SECRET`.
- Missing credentials must fail clearly at token fetch. Do not POST empty strings.
- Default tests do not call live Synergy.
