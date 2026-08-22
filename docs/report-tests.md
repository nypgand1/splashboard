# Report v2 test cases

Source of truth for behavior: `docs/spec.md`. These cases are encoded in `tests/test_report_layout.py`.

Do not call live Synergy. Do not drive a browser in this file.

## Layout model

| ID | Case |
|---|---|
| L1 | `default_layout` returns `version` and exactly 5 pages |
| L2 | Header is not a block on any page |
| L3 | Every default page has at least one `text` block whose `content` is empty and default `h` is 2 |
| L4 | Default layout has no `spacer` on any page |
| L5 | No default block has type `shot_chart` or table_key `play_type` |
| L6 | Builtin `table_key` values are only the allowlist in the spec (`lineup_home` / `lineup_away`; no `lineup_dict`) |
| L7 | Default page 1 has `score_group`, `t_adv_df`, and one empty `text` block |
| L8 | Default page 2 has `t_df` and `k_df` only (no lineup) |
| L9 | Default page 3 has `p_df_home` and `p_df_away` |
| L10 | Paper size is A4 landscape (297mm × 210mm), not portrait |
| L11 | Grid is 12 columns |
| L12 | `layout_storage_key('abc')` is `splashboard.report.layout.abc` |
| L13 | Empty or missing `game_id` does not yield a storage key that collides with another game |
| L14 | Default page 4 has `lineup_home` and empty `text` |
| L15 | Page 2 occupied grid height is less than a full sheet; leftover is whitespace (no spacer, tables not stretched) |
| L16 | Default page 5 has `lineup_away` and empty `text` |

## Images

| ID | Case |
|---|---|
| I1 | JPEG / PNG / WebP at 1_000_000 bytes or less is accepted |
| I2 | 1_000_001 bytes is rejected |
| I3 | `image/svg+xml` and `image/gif` are rejected |
| I4 | Empty content is rejected |
| I5 | Validator is pure Python (no Fly path, no disk write) |

## Read-only tables and chrome contracts

| ID | Case |
|---|---|
| R1 | Builtin blocks have no `content` field that overrides cell values |
| R2 | There is no API to set cell bold or background on a builtin table |
| R3 | Report table engine is `dbc.Table`; Play-By-Play stays `ag_grid` |
| R4 | Block overflow is `hidden` (not `auto` or `scroll`) |
| R5 | Toolbar has no title string |
| R6 | Icon set is `bootstrap-icons`, scoped to Report editor chrome |
| R7 | Add note / Add image / Add table / Reset layout accessible names stay those English strings |
| R8 | Python paint triggers are tab open and `lineup_store`, not `report_layout_store` |
| R9 | Layout mutations after first paint are clientside; add table clones a template |
| R10 | Image validation for the editor is clientside; Python `validate_image_upload` remains the unit contract |
| R11 | Add table is `bi-table` plus a glass menu (`icon_menu`), not a native `<select>` |
| R12 | Page delete is × on the paper top-right; the page list has no minus |
| R13 | `min_pages` is 1 (the last remaining page cannot be deleted) |
| R14 | Add note / image / table target the current page from scroll-spy; auto-place; overflow adds a page |
| R15 | Reset layout is a toolbar icon; confirm copy is `Reset to the default layout? This cannot be undone.` |
| R16 | Delete page confirm copy is `Delete this page?` |
| R17 | Toolbar aligns to the paper (`toolbar_align` = `paper`) |
| R18 | Table drag handle sits left of the title (`title_left`); note/image handles stay `overlay` |
| R19 | Builtin table grid height fits title row (drag handle) plus table; paper still clips |
| R20 | Add table menu lists Player Stats keys before Lineup Stats keys |
| R21 | Compact only on first paint of the default layout and on Reset |
| R22 | Notes editor is `contenteditable` (not dmc); placeholder is `Notes` |
| R23 | Report tab is visible only for finished statuses (`FINISHED`, `CONFIRMED`) |
| R24 | Report Player Stats sort by `+/-` descending |
| R25 | Team Stats and Player Stats `Min` is `MM:SS`, not Synergy `PT` |
| H1 | Header is two lines: away score `@` home score, then date + time + venue on one line |

## PDF contract (unit, not a rendered file)

| ID | Case |
|---|---|
| P1 | Export config is landscape A4 |
| P2 | Export walks `pages` in order (one PDF page per canvas page) |
| P3 | Chrome selectors are listed as `no-print` (toolbar, page list, handles, page-delete, dialog) |
| P4 | Filename is `{YYYYMMDD}.pdf` from match date; missing date falls back to `splashboard-report.pdf` |
| P5 | PDF table style is `as_on_screen` |
| P6 | Uploaded images in the PDF are `png` |
| P7 | Engine is `jspdf_dom` with selectable text (not html2canvas page raster) |
| P8 | Fallback is browser `print` |
| P9 | Font is same-origin `/assets/NotoSansTC-Regular.ttf` |
| P10 | PDF button is `aria-busy` while export runs |

## Out of scope (must not appear)

| ID | Case |
|---|---|
| X1 | Default layout does not include a play-type page |
| X2 | Default layout does not include a Shot Chart widget |
