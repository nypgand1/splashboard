import io
import json

import pandas as pd
from dash import Patch, dcc, html, no_update
import dash_mantine_components as dmc

from ui_kit import icon as dmc_icon

from synergy_reporter.report_layout import (
    TABLE_TITLES,
    empty_page,
    normalize_layout,
    pdf_filename,
)


def lineup_tables_for_size(lineup_store_data, lineup_size=5):
    """Pick one lineup-size table map from store data.

    New store shape: {"5": {team: json}, "4": ...}.
    Old store shape: {team: json}.
    """
    if not lineup_store_data:
        return {}
    if isinstance(lineup_store_data, str):
        try:
            lineup_dict = json.loads(lineup_store_data)
        except Exception:
            return {}
    else:
        lineup_dict = lineup_store_data
    if not isinstance(lineup_dict, dict) or not lineup_dict:
        return {}
    inner = lineup_dict.get(str(lineup_size))
    if isinstance(inner, dict):
        return inner
    if all(not str(key).isdigit() for key in lineup_dict):
        return lineup_dict
    return {}


def _df_from_split(payload):
    if payload is None:
        return None
    if isinstance(payload, pd.DataFrame):
        return payload if not payload.empty else None
    if not isinstance(payload, str) or not payload.strip():
        return None
    try:
        df = pd.read_json(io.StringIO(payload), orient='split')
    except Exception:
        return None
    if df is None or df.empty:
        return None
    return df


def sort_player_stats_for_report(df):
    if df is None or df.empty or '+/-' not in df.columns:
        return df
    res = df.copy()
    res['_is_dnp'] = res['Min'].apply(lambda m: 1 if str(m) == 'DNP' else 0) if 'Min' in res.columns else 0
    res['_pm_num'] = pd.to_numeric(res['+/-'], errors='coerce').fillna(-9999)
    if 'PTS' in res.columns:
        res['_pts_num'] = pd.to_numeric(res['PTS'], errors='coerce').fillna(-9999)
    else:
        res['_pts_num'] = 0
    if '#' in res.columns:
        res['_shirt_num'] = res['#'].apply(
            lambda s: int(s) if str(s).strip().isdigit() else 999
        )
    else:
        res['_shirt_num'] = 0
    res = res.sort_values(
        by=['_is_dnp', '_pm_num', '_pts_num', '_shirt_num'],
        ascending=[True, False, False, True],
        kind='mergesort',
    )
    res = res.drop(columns=['_is_dnp', '_pm_num', '_pts_num', '_shirt_num'])
    return res


CAPTIONED_TABLE_KEYS = ('p_df_home', 'p_df_away', 'lineup_home', 'lineup_away')


def _side_team_name(match_info, side):
    name_key = 'home_team' if side == 'home' else 'away_team'
    fallback = 'Home' if side == 'home' else 'Away'
    return ((match_info or {}).get(name_key) or fallback)


def _pick_team_payload(table_map, match_info, side):
    if not isinstance(table_map, dict) or not table_map:
        return None
    name = (match_info or {}).get('home_team' if side == 'home' else 'away_team')
    if name and name in table_map:
        return table_map[name]
    keys = list(table_map.keys())
    if side == 'home':
        return table_map[keys[0]]
    return table_map[keys[-1]]


def _player_table_json(bs_dict, match_info, side):
    return _pick_team_payload((bs_dict or {}).get('p_df_dict') or {}, match_info, side)


def _lineup_table_json(lineup_store_data, match_info, side):
    return _pick_team_payload(
        lineup_tables_for_size(lineup_store_data, lineup_size=5),
        match_info,
        side,
    )


def _sorted_player_split(bs_dict, match_info, side):
    payload = _player_table_json(bs_dict, match_info, side)
    df = sort_player_stats_for_report(_df_from_split(payload))
    if df is None:
        return payload
    return df.to_json(orient='split')


def report_table_payload(bs_dict, lineup_store_data, match_info):
    bs_dict = bs_dict or {}
    match_info = match_info or {}
    return {
        'score_group': bs_dict.get('qt_pts_df'),
        't_adv_df': bs_dict.get('t_adv_df'),
        't_df': bs_dict.get('t_df'),
        'k_df': bs_dict.get('k_df'),
        'p_df_home': _sorted_player_split(bs_dict, match_info, 'home'),
        'p_df_away': _sorted_player_split(bs_dict, match_info, 'away'),
        'lineup_home': _lineup_table_json(lineup_store_data, match_info, 'home'),
        'lineup_away': _lineup_table_json(lineup_store_data, match_info, 'away'),
        'match': match_info,
    }


def render_builtin_table(table_key, bs_dict, lineup_store_data, match_info, block_id):
    del bs_dict, lineup_store_data, match_info, block_id
    return html.Div(className="report-table-host", **{'data-table-host': table_key or ''})


def render_header(match_info):
    info = match_info or {}
    score_line = "{away} {away_score} @ {home_score} {home}".format(
        away=info.get('away_team') or 'Away',
        away_score=info.get('away_score') or '',
        home_score=info.get('home_score') or '',
        home=info.get('home_team') or 'Home',
    )
    meta_line = "  ".join(
        part for part in (info.get('date'), info.get('time'), info.get('venue')) if part
    )
    return html.Div([
        html.Div(score_line, className="report-header-title"),
        html.Div(meta_line, className="report-header-meta"),
    ], className="report-header")


def _block_body(block, bs_dict, lineup_store_data, match_info):
    b_type = block.get('type')
    b_id = block.get('id')
    if b_type == 'text':
        initial_html = block.get('content') or ''
        if initial_html and not initial_html.startswith('<'):
            initial_html = f"<p>{initial_html}</p>"
        return html.Div(
            dcc.Markdown(initial_html, dangerously_allow_html=True) if initial_html else '',
            className="report-text-block",
            **{
                'data-text-block': b_id,
                'contentEditable': 'true',
                'data-placeholder': 'Notes',
                'spellCheck': 'false',
            },
        )
    if b_type == 'image':
        src = block.get('src') or ''
        if src:
            return html.Img(src=src, className="report-image-block")
        return html.Div("Drop an image here from Add image", className="report-image-placeholder")
    if b_type == 'spacer':
        return html.Div(className="report-spacer")
    if b_type == 'builtin_table':
        return render_builtin_table(
            block.get('table_key'),
            bs_dict,
            lineup_store_data,
            match_info,
            b_id,
        )
    return html.Div("—")


def _table_heading(table_key, match_info):
    if table_key not in CAPTIONED_TABLE_KEYS:
        return TABLE_TITLES.get(table_key, '')
    side = 'home' if table_key.endswith('home') else 'away'
    kind = 'Player Stats' if table_key.startswith('p_df') else 'Lineup Stats'
    return '{name} | {kind}'.format(name=_side_team_name(match_info, side), kind=kind)


def _table_title_children(table_key, match_info):
    heading = _table_heading(table_key, match_info)
    if table_key not in CAPTIONED_TABLE_KEYS:
        return heading
    side = 'home' if table_key.endswith('home') else 'away'
    color = '#00b4d8' if side == 'home' else '#94a3b8'
    return [
        html.Span(className='report-block-title-dot', style={'backgroundColor': color}),
        html.Span(heading),
    ]


def render_grid_item(block, bs_dict, lineup_store_data, match_info, item_id=None, hidden=False):
    b_id = block['id']
    kwargs = {
        'data-gs-id': b_id,
        'data-x': str(block.get('x', 0)),
        'data-y': str(block.get('y', 0)),
        'data-w': str(block.get('w', 6)),
        'data-h': str(block.get('h', 3)),
        'data-block-type': block.get('type'),
        'data-table-key': block.get('table_key') or '',
    }
    class_name = "grid-stack-item"
    if hidden:
        kwargs['hidden'] = True
    handle = html.Div("⋮⋮", className="grid-stack-item-handle no-print", title="Drag")
    remove = html.Button(
        "×",
        className="report-block-remove no-print",
        **{'data-remove-block': b_id, 'type': 'button'},
    )
    body = html.Div(
        _block_body(block, bs_dict, lineup_store_data, match_info),
        className="report-block-body",
    )
    card_children = [remove]
    if block.get('type') == 'builtin_table':
        heading = _table_title_children(block.get('table_key'), match_info)
        card_children.append(html.Div([
            handle,
            html.Div(heading, className="report-block-title"),
        ], className="report-block-title-row"))
        card_class = "grid-stack-item-content report-block-card report-block-card-table"
    else:
        card_children.append(handle)
        card_class = "grid-stack-item-content report-block-card"
    card_children.append(body)
    return html.Div(
        html.Div(card_children, className=card_class),
        className=class_name,
        id=item_id or f"gs-item-{b_id}",
        **kwargs,
    )


def render_paper(page, page_index, bs_dict, lineup_store_data, match_info, page_count):
    del bs_dict, lineup_store_data
    delete_hidden = page_count <= 1
    page_id = page.get('id', page_index)
    return html.Div([
        html.Div(
            dmc.ActionIcon(
                dmc_icon("tabler:x", width=16),
                variant="subtle",
                radius="xl",
                size="sm",
                disabled=delete_hidden,
                **{'aria-label': 'Delete page'},
            ),
            className="report-page-delete no-print" + (" is-disabled" if delete_hidden else ""),
            **{'data-delete-page': str(page_index)},
        ),
        render_header(match_info),
        html.Div([], className="grid-stack report-grid", id=f"report-grid-{page_id}"),
    ], className="report-paper", id=f"report-paper-{page_id}", **{
        'data-page-index': str(page_index),
        'data-hydrated': '0',
    })


def page_list_buttons(page_count, active=0):
    buttons = []
    for index in range(page_count):
        class_name = "report-page-btn is-active" if index == active else "report-page-btn"
        buttons.append(dmc.Button(
            str(index + 1),
            className=class_name,
            variant="default",
            size="compact-md",
            radius="sm",
            **{'data-page-index': str(index)},
        ))
    buttons.append(dmc.ActionIcon(
        "+",
        id="report-add-page",
        className="report-page-btn report-page-add",
        variant="default",
        radius="sm",
        size="lg",
        style={'width': 36, 'height': 36, 'minWidth': 36},
        **{'aria-label': 'Add page'},
    ))
    return buttons


def render_page_list(page_count, active=0):
    return dmc.Stack(
        page_list_buttons(page_count, active),
        id="report-page-list",
        className="report-page-list no-print",
        gap=8,
        align="center",
    )


def _chrome_icon(icon_name, ident, label, extra_class=''):
    return dmc.ActionIcon(
        dmc_icon(icon_name, width=18),
        id=ident,
        variant="default",
        radius="sm",
        size="lg",
        className=("report-chrome-btn report-chrome-btn-icon " + extra_class).strip(),
        style={'width': 36, 'height': 36, 'minWidth': 36},
        **{'aria-label': label},
    )


def render_toolbar():
    menu_items = []
    for key, title in TABLE_TITLES.items():
        menu_items.append(html.Button(
            title,
            className="report-table-menu-item",
            type="button",
            **{'data-add-table': key, 'role': 'menuitem'},
        ))
    
    flat_colors = [
        ('#e74c3c', 'Red'),
        ('#e67e22', 'Orange'),
        ('#f1c40f', 'Yellow'),
        ('#2ecc71', 'Green'),
        ('#3498db', 'Blue'),
        ('#9b59b6', 'Purple'),
        ('#ffffff', 'White'),
        ('#000000', 'Black (Reset)'),
    ]
    
    def _render_color_menu(mode):
        dots = []
        for hex_color, name in flat_colors:
            dots.append(html.Button(
                className="report-rte-color-dot",
                style={'backgroundColor': hex_color},
                title=f"{name}",
                type="button",
                **{f'data-rte-{mode}': hex_color, 'aria-label': f"{name}"}
            ))
        custom_input = html.Label([
            dmc_icon("tabler:color-picker", width=14),
            html.Span("Custom", className="report-rte-custom-label"),
            dmc.ColorInput(
                id=f"report-custom-{mode}",
                className="report-rte-custom-input",
                value="#3498db" if mode == "color" else "#f1c40f",
            )
        ], className="report-rte-custom-btn", title="Custom color")
        return html.Div([
            html.Div(dots, className="report-rte-palette-grid"),
            custom_input,
        ], id=f"report-rte-{mode}-menu", className="report-table-menu report-rte-color-menu", hidden=True)

    rte_btn = lambda icon_name, cmd, label: dmc.ActionIcon(
        dmc_icon(icon_name, width=18),
        variant="default",
        radius="sm",
        size="lg",
        className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
        style={'width': 36, 'height': 36, 'minWidth': 36},
        **{'data-rte-cmd': cmd, 'aria-label': label},
    )

    return dmc.Group([
        _chrome_icon("tabler:notebook", "report-add-text", "Add note"),
        dcc.Upload(
            [
                dmc_icon("tabler:photo", width=18),
                html.Span("Add image", className="visually-hidden"),
            ],
            id="report-image-upload",
            accept="image/jpeg,image/png,image/webp",
            multiple=False,
            className="report-chrome-btn report-chrome-btn-icon report-image-upload",
        ),
        html.Div(
            dmc.Menu([
                dmc.MenuTarget(_chrome_icon(
                    "tabler:table",
                    "report-add-table",
                    "Add table",
                )),
                dmc.MenuDropdown(
                    menu_items,
                    id="report-table-menu",
                    className="report-table-menu",
                    **{'aria-label': 'Add table'},
                ),
            ], position="bottom-start"),
            className="report-table-picker",
        ),
        
        # Note formatting toolbar (visible when a note is focused)
        html.Div([
            html.Div(className="report-toolbar-divider"),
            rte_btn("tabler:bold", "bold", "Bold"),
            rte_btn("tabler:italic", "italic", "Italic"),
            rte_btn("tabler:underline", "underline", "Underline"),
            rte_btn("tabler:strikethrough", "strikethrough", "Strikethrough"),
            rte_btn("tabler:list", "bulletList", "Bullet List"),
            rte_btn("tabler:list-numbers", "orderedList", "Ordered List"),
            
            # Text Color Dropdown Button
            html.Div([
                dmc.ActionIcon(
                    [
                        dmc_icon("tabler:letter-case", width=18),
                        html.Span(className="report-rte-color-indicator", id="report-rte-color-indicator"),
                    ],
                    id="report-btn-color-picker",
                    variant="default",
                    radius="sm",
                    size="lg",
                    className="report-chrome-btn report-chrome-btn-icon report-rte-btn report-rte-picker-btn",
                    style={'width': 36, 'height': 36, 'minWidth': 36},
                    **{'data-rte-toggle-menu': 'color', 'aria-label': 'Text Color'},
                ),
                _render_color_menu('color'),
            ], className="report-rte-dropdown-wrap"),
            html.Div([
                dmc.ActionIcon(
                    [
                        dmc_icon("tabler:highlight", width=18),
                        html.Span(className="report-rte-color-indicator", id="report-rte-highlight-indicator"),
                    ],
                    id="report-btn-highlight-picker",
                    variant="default",
                    radius="sm",
                    size="lg",
                    className="report-chrome-btn report-chrome-btn-icon report-rte-btn report-rte-picker-btn",
                    style={'width': 36, 'height': 36, 'minWidth': 36},
                    **{'data-rte-toggle-menu': 'highlight', 'aria-label': 'Highlight'},
                ),
                _render_color_menu('highlight'),
            ], className="report-rte-dropdown-wrap"),
        ], id="report-note-toolbar", className="report-note-toolbar", style={'display': 'none'}),

        html.Div([
            _chrome_icon("tabler:restore", "report-reset-layout", "Reset layout"),
            dmc.Button(
                "PDF",
                id="btn-export-pdf",
                className="report-chrome-btn-pdf",
                color="blue",
                variant="filled",
                radius="sm",
                size="sm",
                style={"backgroundColor": "#0077b6", "fontWeight": 700, "height": 36},
            ),
        ], className="report-toolbar-end"),
    ], id="report-toolbar", className="report-toolbar no-print", gap="xs", wrap="wrap")


def render_dialog():
    return dmc.Modal(
        [
            dmc.Text("", id="report-dialog-message", className="report-dialog-message"),
            dmc.Group(
                [
                    dmc.Button("Cancel", id="report-dialog-cancel", variant="default", radius="sm"),
                    dmc.Button("OK", id="report-dialog-ok", className="report-dialog-ok", radius="sm"),
                ],
                justify="flex-end",
                mt="md",
                className="report-dialog-actions",
            ),
        ],
        id="report-dialog",
        opened=False,
        keepMounted=True,
        className="report-dialog no-print",
        title="Confirm",
        centered=True,
        radius="md",
    )


def render_report_workspace(layout, bs_dict, lineup_store_data, match_info, game_id):
    layout = normalize_layout(layout)
    pages = layout.get('pages') or []
    papers = []
    page_count = max(1, len(pages))
    table_json = json.dumps(
        report_table_payload(bs_dict, lineup_store_data, match_info),
        ensure_ascii=False,
    )
    for index, page in enumerate(pages):
        papers.append(render_paper(page, index, bs_dict, lineup_store_data, match_info, page_count))
    default_json = json.dumps(layout, ensure_ascii=False)
    workspace = html.Div([
        html.Div(default_json, id="report-layout-json", hidden=True),
        html.Div(default_json, id="report-default-layout-json", hidden=True),
        html.Div(game_id or '', id="report-game-id", hidden=True),
        html.Div(pdf_filename(match_info), id="report-pdf-filename", hidden=True),
        html.Div(table_json, id="report-table-data", hidden=True),
        dcc.Store(id="report-page-ids", data=[page.get('id') or f'page-{i+1}' for i, page in enumerate(pages)]),
        dcc.Store(id="report-page-cmd", data=None),
        dcc.Store(id="report-dialog-opened", data=False),
        html.Div([
            html.Div([
                render_toolbar(),
                html.Div(papers, className="report-papers", id="report-papers"),
            ], className="report-main"),
            render_page_list(page_count),
        ], className="report-workspace-row"),
        render_dialog(),
    ], className="report-workspace", id="report-workspace")
    return workspace


def _child_component_id(child):
    if child is None:
        return None
    if isinstance(child, dict):
        return (child.get('props') or {}).get('id')
    return getattr(child, 'id', None)


def _child_children(child):
    if child is None or isinstance(child, (str, bytes, int, float, bool)):
        return None
    if isinstance(child, dict):
        return (child.get('props') or {}).get('children')
    return getattr(child, 'children', None)


def report_workspace_mounted(children):
    items = children if isinstance(children, (list, tuple)) else ([children] if children else [])
    for item in items:
        if _child_component_id(item) == 'report-workspace':
            return True
        nested = _child_children(item)
        if nested and report_workspace_mounted(nested):
            return True
    return False


def existing_paper_ids(children):
    ids = []
    prefix = 'report-paper-'
    for child in children or []:
        cid = _child_component_id(child)
        if isinstance(cid, str) and cid.startswith(prefix):
            ids.append(cid[len(prefix):])
    return ids


def paper_shells(page_ids, match_info):
    ids = list(page_ids or ['page-1'])
    if not ids:
        ids = ['page-1']
    n = len(ids)
    return [
        render_paper(empty_page(pid), index, {}, {}, match_info or {}, n)
        for index, pid in enumerate(ids)
    ]


def apply_page_cmd(cmd, match_info):
    if not isinstance(cmd, dict) or not cmd.get('op'):
        return no_update, no_update
    ids = list(cmd.get('ids') or [])
    if not ids:
        ids = ['page-1']
    n = len(ids)
    buttons = page_list_buttons(n)
    op = cmd.get('op')
    if op == 'add':
        patched = Patch()
        new_id = cmd.get('id') or ids[-1]
        patched.append(render_paper(empty_page(new_id), n - 1, {}, {}, match_info or {}, n))
        return patched, buttons
    if op == 'delete':
        try:
            index = int(cmd.get('index'))
        except (TypeError, ValueError):
            return no_update, buttons
        if index < 0:
            return no_update, buttons
        patched = Patch()
        del patched[index]
        return patched, buttons
    if op == 'reset':
        return paper_shells(ids, match_info), buttons
    return no_update, buttons
