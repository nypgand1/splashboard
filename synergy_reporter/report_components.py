import io
import json

import pandas as pd
from dash import dcc, html
import dash_mantine_components as dmc

from ui_kit import icon as dmc_icon, loading_skeleton

from synergy_reporter.report_layout import (
    ALLOWED_TABLE_KEYS,
    TABLE_TITLES,
    default_layout,
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


def create_report_table(df):
    if df is None or df.empty:
        return html.Div("—", className="text-muted fst-italic text-center p-2")
    
    header = [html.Tr([html.Th(col) for col in df.columns])]
    body = [
        html.Tr([html.Td(str(df.iloc[row_idx][col])) for col in df.columns])
        for row_idx in range(len(df))
    ]
    return dmc.Table(
        [html.Thead(header), html.Tbody(body)],
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        withColumnBorders=True,
        className="text-nowrap report-dmc-table",
    )


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
    is_dnp = res['Min'].apply(lambda m: 1 if str(m) == 'DNP' else 0) if 'Min' in res.columns else 0
    numeric_pm = pd.to_numeric(res['+/-'], errors='coerce').fillna(-9999)
    res['_is_dnp'] = is_dnp
    res['_pm_num'] = numeric_pm
    res = res.sort_values(by=['_is_dnp', '_pm_num'], ascending=[True, False], kind='mergesort')
    res = res.drop(columns=['_is_dnp', '_pm_num'])
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


def render_builtin_table(table_key, bs_dict, lineup_store_data, match_info, block_id):
    del block_id
    if table_key == 'score_group':
        df = _df_from_split((bs_dict or {}).get('qt_pts_df'))
        return create_report_table(df)
    if table_key in ('t_adv_df', 't_df', 'k_df'):
        df = _df_from_split((bs_dict or {}).get(table_key))
        return create_report_table(df)
    if table_key in ('lineup_home', 'lineup_away'):
        side = 'home' if table_key.endswith('home') else 'away'
        if not lineup_tables_for_size(lineup_store_data, lineup_size=5):
            return loading_skeleton()
        payload = _lineup_table_json(lineup_store_data, match_info, side)
        df = _df_from_split(payload)
        return create_report_table(df)
    if table_key in ('p_df_home', 'p_df_away'):
        side = 'home' if table_key.endswith('home') else 'away'
        payload = _player_table_json(bs_dict, match_info, side)
        df = sort_player_stats_for_report(_df_from_split(payload))
        return create_report_table(df)
    return html.Div("—", className="text-muted")


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
    if table_key in CAPTIONED_TABLE_KEYS:
        side = 'home' if table_key.endswith('home') else 'away'
        return _side_team_name(match_info, side)
    return TABLE_TITLES.get(table_key, '')


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
        class_name += " report-item-template"
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
        heading = _table_heading(block.get('table_key'), match_info)
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
    items = [
        render_grid_item(block, bs_dict, lineup_store_data, match_info)
        for block in page.get('blocks') or []
    ]
    delete_hidden = page_count <= 1
    return html.Div([
        html.Button(
            dmc_icon("tabler:x", width=16),
            className="report-page-delete no-print" + (" is-disabled" if delete_hidden else ""),
            type="button",
            title="Delete page",
            disabled=delete_hidden,
            **{
                'data-delete-page': str(page_index),
                'aria-label': 'Delete page',
            },
        ),
        render_header(match_info),
        html.Div(items, className="grid-stack report-grid", id=f"report-grid-{page.get('id', page_index)}"),
    ], className="report-paper", id=f"report-paper-{page.get('id', page_index)}", **{'data-page-index': str(page_index)})


def render_page_list(page_count):
    buttons = []
    for index in range(page_count):
        class_name = "report-page-btn is-active" if index == 0 else "report-page-btn"
        buttons.append(html.Button(
            str(index + 1),
            className=class_name,
            **{'data-page-index': str(index), 'type': 'button'},
        ))
    buttons.append(html.Button("+", id="report-add-page", className="report-page-btn report-page-add", type="button"))
    return html.Div(buttons, id="report-page-list", className="report-page-list no-print")


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

    return html.Div([
        html.Button(
            dmc_icon("tabler:notebook", width=16),
            id="report-add-text",
            className="report-chrome-btn report-chrome-btn-icon",
            type="button",
            title="Add note",
            **{'aria-label': 'Add note'},
        ),
        dcc.Upload(
            [
                dmc_icon("tabler:photo", width=16),
                html.Span("Add image", className="visually-hidden"),
            ],
            id="report-image-upload",
            accept="image/jpeg,image/png,image/webp",
            multiple=False,
            className="report-chrome-btn report-chrome-btn-icon report-image-upload",
        ),
        html.Div([
            html.Button(
                dmc_icon("tabler:table", width=16),
                id="report-add-table",
                className="report-chrome-btn report-chrome-btn-icon",
                type="button",
                title="Add table",
                **{'aria-label': 'Add table', 'aria-expanded': 'false', 'aria-haspopup': 'true'},
            ),
            html.Div(
                menu_items,
                id="report-table-menu",
                className="report-table-menu",
                **{'role': 'menu', 'aria-label': 'Add table'},
            ),
        ], className="report-table-picker"),
        
        # Note formatting toolbar (visible when a note is focused)
        html.Div([
            html.Div(className="report-toolbar-divider"),
            html.Button(
                dmc_icon("tabler:bold", width=16),
                className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
                title="Bold",
                type="button",
                **{'data-rte-cmd': 'bold', 'aria-label': 'Bold'}
            ),
            html.Button(
                dmc_icon("tabler:italic", width=16),
                className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
                title="Italic",
                type="button",
                **{'data-rte-cmd': 'italic', 'aria-label': 'Italic'}
            ),
            html.Button(
                dmc_icon("tabler:underline", width=16),
                className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
                title="Underline",
                type="button",
                **{'data-rte-cmd': 'underline', 'aria-label': 'Underline'}
            ),
            html.Button(
                dmc_icon("tabler:strikethrough", width=16),
                className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
                title="Strikethrough",
                type="button",
                **{'data-rte-cmd': 'strikethrough', 'aria-label': 'Strikethrough'}
            ),
            html.Button(
                dmc_icon("tabler:list", width=16),
                className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
                title="Bullet List",
                type="button",
                **{'data-rte-cmd': 'bulletList', 'aria-label': 'Bullet List'}
            ),
            html.Button(
                dmc_icon("tabler:list-numbers", width=16),
                className="report-chrome-btn report-chrome-btn-icon report-rte-btn",
                title="Ordered List",
                type="button",
                **{'data-rte-cmd': 'orderedList', 'aria-label': 'Ordered List'}
            ),
            
            # Text Color Dropdown Button
            html.Div([
                html.Button(
                    [
                        dmc_icon("tabler:letter-case", width=16),
                        html.Span(className="report-rte-color-indicator", id="report-rte-color-indicator"),
                    ],
                    id="report-btn-color-picker",
                    className="report-chrome-btn report-chrome-btn-icon report-rte-btn report-rte-picker-btn",
                    title="Text Color",
                    type="button",
                    **{'data-rte-toggle-menu': 'color', 'aria-label': 'Text Color', 'aria-expanded': 'false'}
                ),
                _render_color_menu('color'),
            ], className="report-rte-dropdown-wrap"),
            
            # Highlight Dropdown Button
            html.Div([
                html.Button(
                    [
                        dmc_icon("tabler:highlight", width=16),
                        html.Span(className="report-rte-color-indicator", id="report-rte-highlight-indicator"),
                    ],
                    id="report-btn-highlight-picker",
                    className="report-chrome-btn report-chrome-btn-icon report-rte-btn report-rte-picker-btn",
                    title="Highlight",
                    type="button",
                    **{'data-rte-toggle-menu': 'highlight', 'aria-label': 'Highlight', 'aria-expanded': 'false'}
                ),
                _render_color_menu('highlight'),
            ], className="report-rte-dropdown-wrap"),
        ], id="report-note-toolbar", className="report-note-toolbar", style={'display': 'none'}),

        html.Div([
            html.Button(
                dmc_icon("tabler:restore", width=16),
                id="report-reset-layout",
                className="report-chrome-btn report-chrome-btn-icon",
                type="button",
                title="Reset layout",
                **{'aria-label': 'Reset layout'},
            ),
            html.Button("PDF", id="btn-export-pdf", className="report-chrome-btn report-chrome-btn-pdf", type="button"),
        ], className="report-toolbar-end"),
    ], id="report-toolbar", className="report-toolbar no-print")


def render_dialog():
    return html.Div([
        html.Div([
            html.P("", id="report-dialog-message", className="report-dialog-message"),
            html.Div([
                html.Button("Cancel", id="report-dialog-cancel", className="report-chrome-btn", type="button"),
                html.Button("OK", id="report-dialog-ok", className="report-chrome-btn report-dialog-ok", type="button"),
            ], className="report-dialog-actions"),
        ], className="report-dialog-card"),
    ], id="report-dialog", className="report-dialog no-print", hidden=True)


def render_item_templates(bs_dict, lineup_store_data, match_info):
    templates = [
        render_grid_item(
            {'id': 'tpl-text', 'type': 'text', 'content': '', 'x': 0, 'y': 0, 'w': 5, 'h': 2},
            bs_dict, lineup_store_data, match_info,
            item_id='report-tpl-item-text', hidden=True,
        ),
        render_grid_item(
            {'id': 'tpl-image', 'type': 'image', 'src': '', 'x': 0, 'y': 0, 'w': 6, 'h': 5},
            bs_dict, lineup_store_data, match_info,
            item_id='report-tpl-item-image', hidden=True,
        ),
        render_grid_item(
            {'id': 'tpl-spacer', 'type': 'spacer', 'x': 0, 'y': 0, 'w': 12, 'h': 4},
            bs_dict, lineup_store_data, match_info,
            item_id='report-tpl-item-spacer', hidden=True,
        ),
    ]
    for key in ALLOWED_TABLE_KEYS:
        templates.append(render_grid_item(
            {'id': 'tpl-{0}'.format(key), 'type': 'builtin_table', 'table_key': key, 'x': 0, 'y': 0, 'w': 12, 'h': 4},
            bs_dict, lineup_store_data, match_info,
            item_id='report-tpl-item-table-{0}'.format(key), hidden=True,
        ))
    return html.Div(templates, id="report-templates", hidden=True)


def render_report_workspace(layout, bs_dict, lineup_store_data, match_info, game_id):
    layout = normalize_layout(layout)
    pages = layout.get('pages') or []
    papers = []
    page_count = max(1, len(pages))
    for index, page in enumerate(pages):
        papers.append(render_paper(page, index, bs_dict, lineup_store_data, match_info, page_count))
    default_json = json.dumps(layout, ensure_ascii=False)
    workspace = html.Div([
        html.Div(default_json, id="report-layout-json", hidden=True),
        html.Div(default_json, id="report-default-layout-json", hidden=True),
        html.Div(game_id or '', id="report-game-id", hidden=True),
        html.Div(pdf_filename(match_info), id="report-pdf-filename", hidden=True),
        render_item_templates(bs_dict, lineup_store_data, match_info),
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
