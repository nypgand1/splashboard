# ADR 0001: Report canvas

Status: accepted (grill 2026-08-22)

The Report tab is a multi-page A4 canvas, not a sortable list of table cards printed via `window.print()`.

## Landscape paper

Paper is A4 landscape (297mm × 210mm) so a table and notes can sit side by side. Portrait was rejected.

## GridStack, not Sortable

The old Report only reordered a 1-D flex list. The PDF needs 2-D placement (table left, notes right, spacer below). GridStack owns position and size. It does not style tables.

## `dmc.Table` in Report, AG Grid in Home/Player/Lineup/Play-By-Play

AG Grid inside GridStack showed inner scrollbars, clipped headers, and could not be cloned without a full pane rebuild. Report therefore uses `dmc.Table` (migrated from `dbc.Table`). Home schedule, Play-By-Play, Player Stats, and Lineup Stats use AG Grid for interactive sorting and filtering. Box Score quarter and team summary tables use `dmc.Table`. Rotation stays Plotly. Do not introduce Tabulator.

Icons use `DashIconify` (Tabler) in Python layouts, including Report toolbar buttons. The Report page-delete button created in JS uses an inline SVG. Bootstrap Icons is not a dependency.

## JS owns layout after the first paint

Python renders papers, header, and hidden table templates when the Report tab opens. `lineup_store` (size 5 only) is precomputed at page load (triggered by `game_id`), so it is available as a `State` when the Report tab renders—no second render is needed. The Report callback fires **once** on tab switch. Add/remove/upload/clone then run in GridStack JS and `localStorage`. Writing `report_layout_store` must not rebuild `pane-report`. Image MIME/size checks run in the browser; the Python validator is the unit-test contract.

`fitAllTableBlocks` batches DOM measurements: all `scrollHeight` reads run in a first pass, then all `grid.update` writes run in a second pass. This avoids interleaved forced layout reflows.

Add note / Add image / Add table insert onto the **current** page, which is the paper with the highest intersection in the scroll viewport. New blocks auto-place into a slot that fits; if none, JS adds a page and places there. Page delete is an × on that paper's top-right after a confirm dialog, not a minus on the page list. The last remaining page cannot be deleted.

A Reset layout toolbar button restores `default_layout` after confirm. Old `localStorage` is kept until the user resets; version is not auto-bumped.

Table drag handles sit to the left of the block title so they do not steal a row of A4 height. Note and image handles stay overlaid at the top-left. Builtin table blocks fit their grid height to the table; the paper still clips at 210mm.

Default layout is compacted on first paint and after Reset. Later user moves are left alone. Old `localStorage` is not auto-replaced.

## Notes use JS-side Tiptap (not `dmc.RichTextEditor`)

Notes need rich text formatting (bold, italic, underline, strikethrough, lists, text color, highlight) for game-report annotations.

`dmc.RichTextEditor` (a Dash/React component backed by Tiptap) was tried first but rejected: GridStack's `cloneNode(true)` copies DOM only — React state and the Tiptap editor instance are lost. JS-dynamically-added notes (via `widgetFromBlock`) would have no working editor. `document.execCommand` does not interact with Tiptap's ProseMirror model. Wrapping in `MantineProvider` added an extra DOM layer that conflicted with layout CSS.

Instead, Tiptap and its extensions load via CDN `<script>` tags. Python renders plain `contenteditable` divs with `data-text-block` attributes. After GridStack init, JS calls `new Editor({ element })` to mount Tiptap on each note. Toolbar formatting uses the Tiptap chain API (`editor.chain().focus().toggleBold().run()`). `readLayoutFromDom` calls `editor.getHTML()`. This approach works with `cloneNode` because JS re-mounts Tiptap on cloned nodes via `bindTextBlocks`.

The text-formatting toolbar lives in the **Report toolbar area** (sticky, above the paper), not inside each Note block, so it does not consume grid rows on the A4 sheet. It appears when a Note is focused and hides otherwise.

Note `content` is stored as HTML (Tiptap native output). Old plain-text `content` values are forward-compatible: Tiptap wraps plain text in `<p>` tags automatically.

Available formatting colors are 8 flat-design presets (red `#e74c3c`, orange `#e67e22`, yellow `#f1c40f`, green `#2ecc71`, blue `#3498db`, purple `#9b59b6`, white `#ffffff`, reset black `#000000`) plus a custom color picker.

## Client layout, client images, client PDF

There is no Fly volume and machines auto-stop. Layout and images therefore live in `localStorage` as JSON + data URLs. The Fly machine does not write the filesystem.

PDF is jsPDF drawing the paper DOM as **selectable text** (header, table cells, notes) plus PNG for user images. A whole-page html2canvas raster was rejected: Chinese and numbers must remain real PDF text. Noto Sans TC is bundled at `assets/NotoSansTC-Regular.ttf` (SIL OFL, Traditional Chinese subset) so export works without a CDN. The reconstruction is close to the screen, not pixel-identical. Tables keep on-screen striped/bordered styling. The filename is `{YYYYMMDD}.pdf` from the game date. The PDF button is disabled with `aria-busy` while export runs. Browser print is the fallback if the font or jsPDF fails. Server-side WeasyPrint/Playwright is out of scope.

Report is a post-game canvas. Only finished statuses (`FINISHED`, `CONFIRMED`) show the Report tab. Live-play, unplayed, void, and unknown hide it.

Table grid height includes the title row and drag handle, not only the table body, so the block does not grow an inner scrollbar.

The GridStack container uses `minRow` equal to the leftover A4 height so empty paper below widgets stays addressable grid cells. Auto-place must not treat a content-sized grid as "full".

## Glass on chrome only

Liquid glass is the editor shell. The A4 sheet is opaque white so the PDF stays print-white. Other tabs and the navbar use Scheme A inside `dmc.AppShell`.

## Default five pages, empty notes, no Shot Chart

Note slots start as empty `text` blocks at 2 grid rows and resize with content. There is no default `spacer` and no play-type page; Splashboard does not compute Shot Chart or play-type tables.

Page 1 is Score + empty notes + Four Factors.
Page 2 is Team Stats + Key Stats + empty notes. Leftover paper stays whitespace; do not stretch those blocks to fill the sheet.
Page 3 is home Player Stats + away Player Stats + empty notes.
Page 4 is home Lineup Stats (`lineup_home`) + empty notes.
Page 5 is away Lineup Stats (`lineup_away`) + empty notes. There is no combined `lineup_dict` block.

The header is a two-line template (away, away score, `@`, home score, home; then date, time, and venue on one line), compact type with a slightly larger gap under the score line. It is not a GridStack block.

Player box tables are titled **Player Stats**. The Add table menu lists them before Lineup Stats. The toolbar is 297mm, aligned with the paper, not with the page-list column.

## Builtin tables are read-only

Values come from `PostGameReport`. Report does not edit cells. Automatic red/green thresholds are deferred.

## No scrollbars in blocks

Block overflow is `hidden`. A4 paper is the clip. Do not grow the sheet past 210mm.
