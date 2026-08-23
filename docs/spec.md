# Splashboard product spec

This file is the source of truth for product behavior. Tests and later feature work check against it.

## Scope

- Web dashboard for Taipei Fubon Braves schedule and single-game views.
- UI strings are English, including loading, empty, and error copy.
- Rotation is Plotly only, with no separate dark mode.
- Report is a multi-page A4 landscape canvas. PDF export is in scope (browser-side).
- DBC theme is **LITERA**. Notes use a JS-side Tiptap editor (not a Dash/React component) so GridStack `cloneNode` works.

## Pages

### Home `/`

- Show `Loading...`, then load the current-season schedule asynchronously.
- Columns: Time, Game Type, Venue, Home Team, Score, Away Team.
- For `PENDING` / `IN_PROGRESS` / `FINISHED` / `CONFIRMED`, the score is a link to `/game/<fixtureId>`.
- On Synergy failure: `Failed to load games. Please try again later.` (HTTP 200, no unhandled exception).
- When the season list is empty: `No games available.`

### Game `/game/<game_id>`

Top tabs, left to right:

1. Box Score
2. Rotation
3. Play-By-Play
4. Lineup Stats
5. Report — **finished games only**. Live games (`IN_PROGRESS`, `PENDING`, unknown, empty) do not show the Report tab. If the status is live while Report is active, switch to Box Score.

Box Score is the default. Tab panes stay mounted. Hidden-tab render callbacks return `no_update` and do not rebuild children.

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
