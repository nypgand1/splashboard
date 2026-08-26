# Splashboard product spec

This file is the source of truth for product behavior. Tests and later feature work check against it.

## Scope

- Web dashboard for Taipei Fubon Braves schedule and single-game views.
- UI theme is **Scheme A: Braves Japanese Clean & Modern (日式簡約・青空水無月 Light Mode)**, inspired by the official **Taipei Fubon Braves** visual identity:
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
- Tables & Alignment Rules (strictly unified across `dmc.Table` and `dag.AgGrid`):
  - **Left Align (靠左對齊)**: `Player`, `Lineup`, `Lineups`, `Team` (single team name in Box Score).
  - **Center Align (置中對齊)**: `Home Team`, `Away Team`, `Venue`, `Game Type`, `Status`, `Score`.
  - **Right Align (靠右對齊)**: `Time`, `Min`, `+/-`, `PM`, `PTS`, `REB`, `AST`, `TOV`, `STL`, `BLK`, `PF`, `OR`, `DR`, `2PM-A (%)`, `3PM-A (%)`, `FTM-A (%)`, `eFG%`, `USG%`, `Poss`, `Pace`, `PPP`, `ORB%`, `TOV%`, `FT-R`, `PIPM-A`, `PIP`, `SCPM-A`, `SCP`, `FBP`, `POT`, `BP` and all numeric/time statistics.
  - Header cells and data cells must strictly share the identical alignment for every column.
  - Team summary tables have a 3.5px left indicator bar (Home: `#0077b6`, Away: `#94a3b8`).
  - Player detail tables prefixed with 8px dot (Home: `#00b4d8`, Away: `#94a3b8`).
- Responsive Layout (RWD):
  - **Mobile (≤ 768px)**: Canvas `padding: 0`, Device Frame full bleed (`border-radius: 0; border: none; box-shadow: none;`), content `padding: 12px`, Tabs single-row smooth horizontal scrolling (`overflow-x: auto`), data tables support horizontal swipe with sticky first column.
  - **Tablet (769px ~ 1024px)**: Canvas `padding: 12px`, Device Frame `border-radius: 12px`.
  - **Desktop (> 1024px)**: Canvas `padding: 24px`, Device Frame `max-width: 1440px`, `border-radius: 14px`, floating shadow `0 8px 30px rgba(15, 23, 42, 0.15)`.

## Pages

### Home `/`

- Show `Loading...`, then load the current-season schedule asynchronously.
- Rendered via `dag.AgGrid` (`ag-theme-alpine braves-clean-ag-grid`) with `domLayout="autoHeight"` (no pagination), sortable and filterable columns.
- Columns: Time, Status, Game Type, Venue, Home Team, Score, Away Team.
- **Status 欄位**：
  - `FINISHED` / `CONFIRMED`: 沉穩淡灰徽章 (`#f1f5f9` + `#475569`)。
  - `IN_PROGRESS`: 高亮珊瑚紅徽章 (`#fee2e2` + `#dc2626`)。
  - `PENDING`: 醒目青藍光環徽章 (`#e0f2fe` + `#0284c7`)。
- **Score 欄位**：
  - 完賽/進行中：顯示實時比分 `[88 : 79](/game/<fixtureId>)`。
  - 未開賽 (`PENDING`)：顯示 `[- : -](/game/<fixtureId>)`。
- **互動導航**：點擊賽程列任一處或比分連結，均可直達該場賽事頁面 `/game/<fixtureId>`。
- On Synergy failure: `Failed to load games. Please try again later.` (HTTP 200, no unhandled exception).
- When the season list is empty: `No games available.`

### Game `/game/<game_id>`

Top tabs, left to right (rendered via DMC `dmc.Tabs` with `variant="pills"` and Dark Liquid Glass container):

1. Box Score (tab_id: `tab-bs`)
2. Rotation (tab_id: `tab-rotation`)
3. Play-By-Play (tab_id: `tab-pbp`)
4. Lineup Stats (tab_id: `tab-lineup`)
5. Report (tab_id: `tab-report`) — **finished games only**. Live games (`IN_PROGRESS`, `PENDING`, unknown, empty) do not show the Report tab (`display: none`). If the status is live while Report is active, switch to Box Score.

Box Score is the default (`value="tab-bs"`). Tab panes stay mounted. Hidden-tab render callbacks gate on `Input('tabs', 'value')`, return `no_update`, and do not rebuild children.
- Quarter tables (points, fouls, timeouts) and team summary tables (four factors, advanced stats, key stats) are rendered via DMC `dmc.Table` (with `dmc.SimpleGrid` for responsive quarter stats layout).
- Player Stats and Lineup Stats tables use `dag.AgGrid` with `domLayout="autoHeight"` and sortable/filterable columns for interactive exploration.
- Report canvas tables strictly use `dmc.Table` (per ADR 0001) for stable A4 rendering and PDF export. No `dbc.Table`, `dbc.Row`, or `dbc.Col` is used anywhere in the codebase.

A `dcc.Store` that is `None` or invalid JSON is treated as an empty object. Callbacks must not crash.

## Finished vs live

- Finished statuses: `FINISHED`, `CONFIRMED` (compared after strip).
- Every other status (`IN_PROGRESS`, `PENDING`, unknown, empty) is live.
- Finished games:
  - use official routes (URL has **no** `/live` suffix)
  - freeze the report cache (no TTL rebuild)
  - disable the Game-page interval
- Live games:
  - use `/live` routes (except fixture roster and org persons/entities/venues)
  - UI interval = 30 seconds
  - PBP HTTP cache and live report cache = 25 seconds
  - Play-By-Play and Rotation share that cadence

## Background warmup and prefetch

- **Game page Tab warmup**: For finished games (`FINISHED`, `CONFIRMED`), after `game_id` load, a background daemon thread precomputes Lineup `(4, 3, 2)` combinations and Rotation payload into `PostGameReport` memoized caches so tab switching is instantaneous.
- **Font prefetch**: In Game pages, `NotoSansTC-Regular.ttf` (2.2MB) is preloaded asynchronously via JS upon initial render, eliminating download latency when clicking PDF export.
- **Home page 2-game prefetch**: Upon loading the Home schedule list, a background sequential worker pre-fetches and memoizes `PostGameReport` for up to the latest 2 games (safely limited to avoid live API rate limits). Any direct user page request preempts background warmup.

## Rotation

- Plotly heatmap, colorscale `PuBu`.
- Fixed width 1220px, not 100%.
- Margin ticks in steps of 5.
- Player rows sort by first time on court, then jersey; DNP rows last.
- Scoring heatmap accumulates team points per minute bucket.
- Period labels: 1–4 → `1Q`–`4Q`; official OT `periodId` 11 → `OT`, 12 → `2OT`; legacy `periodId` 5 still reads as `OT`.

## Report

Decisions: `docs/adr/0001-report-canvas.md`. Cases: `docs/report-tests.md`.

Throw away the previous Report canvas (Sortable, `window.print()` as the primary PDF path, match-info as a draggable block). Keep `PostGameReport` as the data source. Box Score, Rotation, Play-By-Play, and Lineup Stats stay as they are.

### Paper and chrome

- Paper is A4 **landscape** (297mm × 210mm). Opaque white. No glass, no blur.
- Editor chrome (toolbar, page list, add-block palette, block handles, page-delete) uses Liquid glass. Other tabs and the navbar stay LITERA.
- Toolbar has no "Report" title. Add note, Add image, Add table, and Reset layout are Bootstrap Icons (`bi-journal-text`, `bi-image`, `bi-table`, `bi-arrow-counterclockwise`) with `aria-label` `Add note` / `Add image` / `Add table` / `Reset layout`. Add table opens a Liquid-glass menu of builtin tables (Player Stats before Lineup Stats). PDF stays a text button.
- The toolbar is the same width as one A4 paper (297mm) and left-aligned with the papers. The page list sits to the right of that column; do not center the toolbar independently of the paper.
- Reset layout asks `Reset to the default layout? This cannot be undone.` with `Cancel` / `Reset`. Confirming replaces the canvas with `default_layout` and writes that JSON to `localStorage`. Stored layouts are not auto-discarded.
- Bootstrap Icons load for the app but are **used only on Report editor chrome** (toolbar and the page-delete control). Do not put icons on other tabs.
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
- There is no `spacer` on any default page.

### Block types

| `type` | Role |
|---|---|
| `builtin_table` | Read-only table from another tab's computed data |
| `text` | Editable notes |
| `image` | User-uploaded raster, stored as a data URL |
| `spacer` | Unused in the default layout |

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
- Add table clones a hidden `dbc.Table` template for that `table_key`. Do not mount a new AG Grid.
- `fitAllTableBlocks` batches DOM measurements: all `scrollHeight` reads run first, then all `grid.update` writes run, to avoid interleaved layout reflows.
- Reset layout is clientside (default JSON kept in the pane; no Python rebuild).

### PDF

- Primary: jsPDF walks each paper's DOM (header, `dbc.Table` cells, notes, images) and writes **selectable text**, one PDF page per canvas page, landscape A4. Layout is close to the screen, not pixel-identical. Notes are parsed via a Rich Text DOM Walker:
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

- Report builtin tables are `dbc.Table` (same family as Box Score / Lineup / Home): striped, bordered, `text-nowrap`, read-only.
- Play-By-Play keeps AG Grid. Do not put AG Grid inside Report blocks.
- Tighter font and padding than Box Score so a table can sit in an A4 block. Overflowing rows are clipped by the paper, not scrolled inside the block.
- Team Stats and Player Stats `Min` values are `MM:SS` (converted from Synergy `PT` at the data layer). Box Score uses the same values.
- Report Player Stats (`p_df_home`, `p_df_away`) sort by `+/-` descending. Box Score Player Stats keep their existing PTS-first sort.

## Lineup Stats

- Lineup size is selectable from 5 down to 2.
- New store shape is nested by size. The old shape (team name as top-level key) still reads as the 5-player tables.

## Config and deploy

- Public hosts, org id, and season ids live in git (`synergy_inbounder/settings.py`).
- Credentials come only from `SYNERGY_CREDENTIAL_ID` and `SYNERGY_CREDENTIAL_SECRET`.
- Missing credentials must fail clearly at token fetch. Do not POST empty strings.
- Default tests do not call live Synergy.
