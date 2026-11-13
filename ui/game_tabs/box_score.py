# -*- coding: utf-8 -*-
import io

from dash import html, no_update
import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd

from synergy_inbounder.logs import data as log_data
from synergy_reporter.report_components import read_split_frame
from synergy_reporter.team_order import (
    order_named_items,
    order_team_frame,
    section_dot,
    side_names,
)
from ui.components import loading_skeleton
from ui.game_tabs.common import (
    _empty_view,
    _error_view,
    _last_update_span,
    safe_loads,
)
from ui.tables.ag_grid import _ag_grid_from_df
from ui.tables.stat_cards import (
    ADVANCED_CARD_TITLE,
    KEY_CARD_TITLE,
    PACE_CARD_TITLE,
    dmc_table_from_df as _dmc_table_from_df,
    scroll_card_paper as _bs_scroll_card,
)
from ui.tokens import AWAY_DOT, HOME_DOT


def _bs_player_block(index, dot_color):
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.Box(style={
                        'width': '8px',
                        'height': '8px',
                        'borderRadius': '50%',
                        'backgroundColor': dot_color,
                    }),
                    dmc.Text('', id=f'bs-player-title-{index}', fw=800, fz='16px'),
                ],
                gap=8,
                align='center',
                mt='md',
                mb=10,
            ),
            dmc.Paper(
                dag.AgGrid(
                    id=f'bs-player-grid-{index}',
                    rowData=[],
                    columnDefs=[],
                    defaultColDef={
                        'sortable': True,
                        'filter': False,
                        'resizable': True,
                        'suppressMovable': True,
                        'cellClassRules': {'ag-sorted-col-bg': 'params.column.isSortActive()'},
                        'cellDataType': False,
                    },
                    dashGridOptions={
                        'domLayout': 'autoHeight',
                        'suppressHorizontalScroll': False,
                        'suppressMovableColumns': True,
                        'enableBrowserTooltips': True,
                        'tooltipShowDelay': 200,
                    },
                    className='ag-theme-alpine braves-clean-ag-grid',
                    style={'width': '100%'},
                    getRowId='params.data._row',
                ),
                id=f'bs-player-wrap-{index}',
                withBorder=True,
                radius='md',
                shadow='xs',
                mb='md',
                className='braves-grid-wrap',
                style={'overflowX': 'auto'},
            ),
        ],
        id=f'bs-player-block-{index}',
    )


def _box_score_wrap():
    matrix = html.Div(
        [
            html.Div(loading_skeleton('cards'), id='bs-skeleton'),
            html.Div(id='bs-status', style={'display': 'none'}),
            html.Div(
                [
                    html.Div(id='bs-last-update'),
                    dmc.SimpleGrid(
                        cols={'base': 1, 'lg': 3},
                        spacing='12px',
                        children=[
                            _bs_scroll_card('bs-score-scroll', 'Score'),
                            _bs_scroll_card('bs-fouls-scroll', 'Fouls'),
                            _bs_scroll_card('bs-tout-scroll', 'Timeouts'),
                        ],
                        style={'marginBottom': '12px'},
                    ),
                ],
                id='bs-matrix-body',
                style={'display': 'none'},
            ),
        ],
        id='bs-matrix',
    )
    bar = dmc.Group(
        [
            dmc.SegmentedControl(
                id='bs-period-control',
                data=[{'label': 'All', 'value': 'all'}],
                value='all',
                radius='md',
                size='xs',
            ),
        ],
        id='bs-period-bar',
        mb='sm',
        wrap='wrap',
        gap='sm',
        style={'display': 'none'},
    )
    detail = html.Div(
        html.Div(
            [
                dmc.SimpleGrid(
                    cols={'base': 1, 'lg': 2},
                    spacing='12px',
                    children=[
                        _bs_scroll_card('bs-pace-scroll', PACE_CARD_TITLE),
                        _bs_scroll_card('bs-advanced-scroll', ADVANCED_CARD_TITLE),
                    ],
                    style={'marginBottom': '12px'},
                ),
                dmc.Box(
                    _bs_scroll_card('bs-key-scroll', KEY_CARD_TITLE),
                    mb='sm',
                ),
                dmc.Box(_bs_scroll_card('bs-team-scroll'), mb='sm'),
                _bs_player_block(0, AWAY_DOT),
                _bs_player_block(1, HOME_DOT),
            ],
            id='bs-detail-body',
            style={'display': 'none'},
        ),
        id='bs-detail',
    )
    body = html.Div(id='pane-bs', children=[matrix, bar, detail])
    return html.Div(body, id='wrap-bs')


def _format_metric(value, digits):
    if value is None or value == '':
        return ''
    try:
        if pd.isna(value):
            return ''
    except TypeError:
        pass
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return ''


def period_bar_state(bs_store):
    payload = bs_store if isinstance(bs_store, dict) else safe_loads(bs_store)
    ready = isinstance(payload, dict) and payload.get('_ui') != 'error' and bool(payload.get('qt_pts_df'))
    chips = payload.get('period_chips') if isinstance(payload, dict) else None
    data = chips or [{'label': 'All', 'value': 'all'}]
    style = {'display': 'flex'} if ready else {'display': 'none'}
    return data, style


def _bs_frames(bs_dict, period='all', match_info=None):
    selected = str(period or 'all')
    slices = bs_dict.get('slices') if isinstance(bs_dict.get('slices'), dict) else {}
    view = slices.get(selected) if selected != 'all' and isinstance(slices.get(selected), dict) else bs_dict
    away_name, home_name = side_names(match_info)

    qt_pts_df = order_team_frame(pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split'), away_name, home_name)
    qt_foul_df = order_team_frame(pd.read_json(io.StringIO(bs_dict['qt_foul_df']), orient='split'), away_name, home_name)
    qt_tout_df = order_team_frame(pd.read_json(io.StringIO(bs_dict['qt_tout_df']), orient='split'), away_name, home_name)

    t_adv_df = order_team_frame(pd.read_json(io.StringIO(view['t_adv_df']), orient='split'), away_name, home_name)
    if 'Pace' in t_adv_df.columns:
        t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: _format_metric(x, 1))
    adv_raw = view.get('adv_df') if isinstance(view, dict) else None
    if isinstance(adv_raw, str) and adv_raw.strip():
        try:
            adv_df = order_team_frame(
                pd.read_json(io.StringIO(adv_raw), orient='split'), away_name, home_name,
            )
        except Exception as exc:
            log_data.debug('advanced frame parse failed: %s', exc)
            adv_df = pd.DataFrame()
    else:
        adv_df = pd.DataFrame()
    if 'PPP' in adv_df.columns:
        adv_df['PPP'] = adv_df['PPP'].apply(lambda x: _format_metric(x, 2))

    players = []
    p_dict = view.get('p_df_dict') if isinstance(view.get('p_df_dict'), dict) else {}
    p_summary = view.get('p_summary_dict') if isinstance(view.get('p_summary_dict'), dict) else {}
    for team_name, p_json in order_named_items(p_dict.items(), away_name, home_name):
        players.append((
            team_name,
            read_split_frame(p_json),
            p_summary.get(team_name),
        ))
    return {
        'qt_pts': qt_pts_df,
        'qt_foul': qt_foul_df,
        'qt_tout': qt_tout_df,
        't_adv': t_adv_df,
        'adv': adv_df,
        't_df': order_team_frame(read_split_frame(view['t_df']), away_name, home_name),
        'k_df': order_team_frame(pd.read_json(io.StringIO(view['k_df']), orient='split'), away_name, home_name),
        'players': players,
        'away_name': away_name,
        'home_name': home_name,
        'chips': bs_dict.get('period_chips') or [{'label': 'All', 'value': 'all'}],
    }


def _table_children(df, title=None, away_name=None, home_name=None):
    card = _dmc_table_from_df(
        df, is_team_summary=True, title=title, away_name=away_name, home_name=home_name,
    )
    if isinstance(card, dmc.Paper):
        for child in card.children:
            if getattr(child, 'className', None) == 'braves-table-scroll':
                return child.children
    return card


def _row_id_records(records, kind):
    if not isinstance(records, list):
        return []
    seen = {}
    rows = []
    for record in records:
        item = dict(record)
        if kind == 'pin':
            base = f"pin|{item.get('#', '')}|{item.get('Player', '')}"
        else:
            base = f"{item.get('Player', '')}|{item.get('#', '')}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        item['_row'] = base if count == 0 else f"{base}|{count}"
        rows.append(item)
    return rows


def _player_grid_options(pinned_rows):
    return {
        'domLayout': 'autoHeight',
        'suppressHorizontalScroll': False,
        'suppressMovableColumns': True,
        'pinnedBottomRowData': pinned_rows or [],
        'enableBrowserTooltips': True,
        'tooltipShowDelay': 200,
    }


def _player_model(df, pinned):
    pin_rows = _row_id_records(pinned, 'pin') if isinstance(pinned, list) else []
    if df is None or df.empty:
        return {
            'records': [],
            'options': _player_grid_options(pin_rows),
            'column_defs': [],
            'columns': [],
        }
    card = _ag_grid_from_df(df, pinned_bottom_data=pinned)
    column_defs = []
    if isinstance(card, dmc.Paper):
        column_defs = list(getattr(card.children, 'columnDefs', None) or [])
    return {
        'records': _row_id_records(df.to_dict('records'), 'row'),
        'options': _player_grid_options(pin_rows),
        'column_defs': column_defs,
        'columns': [str(column) for column in df.columns],
    }


def render_bs_sections(bs_store, period='all', match_info=None):
    bs_dict = safe_loads(bs_store)
    if bs_dict.get('_ui') == 'error':
        return [_error_view(bs_dict)], []
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_empty_view()], []

    frames = _bs_frames(bs_dict, period, match_info)
    away_name = frames.get('away_name')
    home_name = frames.get('home_name')
    row1 = dmc.SimpleGrid(
        cols={"base": 1, "lg": 3},
        spacing="12px",
        children=[
            _dmc_table_from_df(frames['qt_pts'], is_team_summary=True, title="Score", away_name=away_name, home_name=home_name),
            _dmc_table_from_df(frames['qt_foul'], is_team_summary=True, title="Fouls", away_name=away_name, home_name=home_name),
            _dmc_table_from_df(frames['qt_tout'], is_team_summary=True, title="Timeouts", away_name=away_name, home_name=home_name),
        ],
        style={"marginBottom": "12px"},
    )
    row2 = dmc.SimpleGrid(
        cols={"base": 1, "lg": 2},
        spacing="12px",
        children=[
            _dmc_table_from_df(frames['t_adv'], is_team_summary=True, title=PACE_CARD_TITLE, away_name=away_name, home_name=home_name),
            _dmc_table_from_df(frames['adv'], is_team_summary=True, title=ADVANCED_CARD_TITLE, away_name=away_name, home_name=home_name),
        ],
        style={"marginBottom": "12px"},
    )
    row_key = dmc.Box(
        _dmc_table_from_df(
            frames['k_df'],
            is_team_summary=True,
            title=KEY_CARD_TITLE,
            away_name=away_name,
            home_name=home_name,
        ),
        mb="sm",
    )
    row3 = dmc.Box(
        _dmc_table_from_df(frames['t_df'], is_team_summary=True, away_name=away_name, home_name=home_name),
        mb="sm",
    )
    info = match_info if isinstance(match_info, dict) else safe_loads(match_info)
    matrix = [_last_update_span(
        bs_dict.get('game_id'),
        info.get('organization_id'),
        box=True,
    ), row1]
    detail = [row2, row_key, row3]
    for idx, (team_name, p_df, summary_rows) in enumerate(frames['players']):
        dot_color = section_dot(team_name, away_name, home_name, idx)
        detail.append(dmc.Group(
            [
                dmc.Box(style={
                    "width": "8px",
                    "height": "8px",
                    "borderRadius": "50%",
                    "backgroundColor": dot_color,
                }),
                dmc.Text(team_name, fw=800, fz="16px"),
            ],
            gap=8,
            align="center",
            mt="md",
            mb=10,
        ))
        detail.append(_ag_grid_from_df(p_df, page_size=None, pinned_bottom_data=summary_rows))
    return matrix, detail


def render_bs_children(bs_store, period='all', match_info=None):
    matrix, detail = render_bs_sections(bs_store, period, match_info)
    return [*matrix, *detail]


_BS_SHOW = {'display': 'block'}
_BS_HIDE = {'display': 'none'}
_BS_BAR = {'display': 'flex'}

BS_SYNC_KEYS = (
    'skeleton_style',
    'matrix_body_style',
    'detail_body_style',
    'status_style',
    'status_children',
    'bar_style',
    'chip_data',
    'last_update',
    'score',
    'fouls',
    'tout',
    'pace',
    'advanced',
    'key',
    'team',
    'title0',
    'title1',
    'block0_style',
    'block1_style',
    'rows0',
    'rows1',
    'options0',
    'options1',
    'defs0',
    'defs1',
    'columns',
)


def _bs_blank(fill):
    return {key: fill for key in BS_SYNC_KEYS}


def box_score_screen(bs_store, period='all', game_id=None, match_info=None):
    payload = bs_store if isinstance(bs_store, dict) else safe_loads(bs_store)
    if not isinstance(payload, dict):
        payload = {}
    if payload.get('_ui') == 'waiting':
        return {'mode': 'skeleton'}
    if game_id and payload.get('game_id') != game_id:
        return {'mode': 'skeleton'}
    if payload.get('_ui') == 'error':
        return {'mode': 'error', 'payload': payload}
    if not payload or not payload.get('qt_pts_df'):
        return {'mode': 'empty'}
    return {'mode': 'ready', 'frames': _bs_frames(payload, period, match_info)}


def _bs_shell(mode, status=None):
    patch = _bs_blank(no_update)
    if mode == 'ready':
        patch.update({
            'skeleton_style': _BS_HIDE,
            'matrix_body_style': _BS_SHOW,
            'detail_body_style': _BS_SHOW,
            'status_style': _BS_HIDE,
            'bar_style': _BS_BAR,
        })
        return patch
    patch.update({
        'skeleton_style': _BS_SHOW if mode == 'skeleton' else _BS_HIDE,
        'matrix_body_style': _BS_HIDE,
        'detail_body_style': _BS_HIDE,
        'status_style': _BS_HIDE if mode == 'skeleton' else _BS_SHOW,
        'bar_style': _BS_HIDE,
    })
    if status is not None:
        patch['status_children'] = status
    return patch


def _bs_player_outputs(models, names, column_state):
    old = column_state if isinstance(column_state, dict) else {}
    old_columns = old.get('columns') if isinstance(old.get('columns'), dict) else {}
    new_columns = {}
    defs = []
    changed = False
    for index, model in enumerate(models):
        key = str(index)
        new_columns[key] = model['columns']
        if old_columns.get(key) == model['columns']:
            defs.append(no_update)
        else:
            defs.append(model['column_defs'])
            changed = True
    titles = [(names[index] if index < len(names) else '') for index in range(2)]
    shown = [len(names) > index for index in range(2)]
    return {
        'title0': titles[0],
        'title1': titles[1],
        'block0_style': _BS_SHOW if shown[0] else _BS_HIDE,
        'block1_style': _BS_SHOW if shown[1] else _BS_HIDE,
        'rows0': models[0]['records'],
        'rows1': models[1]['records'],
        'options0': models[0]['options'],
        'options1': models[1]['options'],
        'defs0': defs[0],
        'defs1': defs[1],
        'columns': {'columns': new_columns} if changed else no_update,
    }


def box_score_sync_values(bs_store, period, game_id, active_tab, column_state, triggered_id, match_info=None):
    if active_tab != 'tab-bs' and triggered_id != 'game_id':
        return tuple(no_update for _ in BS_SYNC_KEYS)
    screen = box_score_screen(bs_store, period, game_id, match_info)
    if screen['mode'] == 'skeleton':
        return tuple(_bs_shell('skeleton')[key] for key in BS_SYNC_KEYS)
    if active_tab != 'tab-bs':
        return tuple(no_update for _ in BS_SYNC_KEYS)
    if screen['mode'] == 'error':
        patch = _bs_shell('error', _error_view(screen.get('payload')))
        return tuple(patch[key] for key in BS_SYNC_KEYS)
    if screen['mode'] == 'empty':
        patch = _bs_shell('empty', _empty_view())
        return tuple(patch[key] for key in BS_SYNC_KEYS)

    frames = screen['frames']
    patch = _bs_shell('ready')
    models = []
    names = []
    for team_name, frame, pinned in frames['players'][:2]:
        names.append(team_name)
        models.append(_player_model(frame, pinned))
    while len(models) < 2:
        models.append(_player_model(pd.DataFrame(), None))
    patch.update(_bs_player_outputs(models, names, column_state))
    away_name = frames.get('away_name')
    home_name = frames.get('home_name')
    patch['pace'] = _table_children(frames['t_adv'], PACE_CARD_TITLE, away_name, home_name)
    patch['advanced'] = _table_children(frames['adv'], ADVANCED_CARD_TITLE, away_name, home_name)
    patch['key'] = _table_children(frames['k_df'], KEY_CARD_TITLE, away_name, home_name)
    patch['team'] = _table_children(frames['t_df'], away_name=away_name, home_name=home_name)
    if triggered_id != 'bs-period':
        patch['chip_data'] = frames['chips']
        info = match_info if isinstance(match_info, dict) else safe_loads(match_info)
        patch['last_update'] = _last_update_span(
            game_id, (info or {}).get('organization_id'), box=True,
        )
        patch['score'] = _table_children(frames['qt_pts'], 'Score', away_name, home_name)
        patch['fouls'] = _table_children(frames['qt_foul'], 'Fouls', away_name, home_name)
        patch['tout'] = _table_children(frames['qt_tout'], 'Timeouts', away_name, home_name)
    return tuple(patch[key] for key in BS_SYNC_KEYS)


def resolve_bs_period(triggered_id, control_value):
    if triggered_id == 'game_id':
        return 'all'
    if control_value in (None, ''):
        return 'all'
    return str(control_value)
