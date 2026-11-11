# -*- coding: utf-8 -*-
import os

from dash import dcc, html, no_update
import dash_mantine_components as dmc

from synergy_inbounder.logs import data as log_data
from synergy_reporter.report_components import (
    lineup_tables_for_size,
    read_split_frame,
)
from synergy_reporter.team_order import (
    order_named_items,
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
from ui.tables.ag_grid import (
    _ag_grid_from_df,
    _lineup_pair_records,
    _lineup_visible_columns,
    _matchup_grid,
)


def _lineup_controls():
    return dmc.Group(
        [
            dmc.SegmentedControl(
                id='lineup_size_dropdown',
                data=[
                    {'label': '5 Players', 'value': '5'},
                    {'label': '4 Players', 'value': '4'},
                    {'label': '3 Players', 'value': '3'},
                    {'label': '2 Players', 'value': '2'},
                ],
                value='5',
                radius='md',
                size='xs',
            ),
            dmc.Switch(
                id='lineup-show-opp',
                label='Show Opp',
                checked=False,
                size='sm',
                color='gray',
                ms='auto',
            ),
        ],
        justify='flex-start',
        align='center',
        wrap='wrap',
        gap='sm',
        mb='sm',
        w='100%',
    )


def _lineup_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    pane = html.Div(id='pane-lineup', children=loading_skeleton('table'))
    if os.environ.get('SPLASHBOARD_E2E'):
        body = pane
    else:
        body = dcc.Loading(
            delay_show=1000,
            custom_spinner=loading_skeleton('table'),
            children=pane,
        )
    return html.Div(
        [
            html.Div(id='lineup-last-update', children=_last_update_span()),
            _lineup_controls(),
            body,
        ],
        id='wrap-lineup',
        style=style,
    )


def _matchup_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    return html.Div(
        [
            html.Div(id='matchup-last-update', children=_last_update_span()),
            dmc.Group(
                [
                    dmc.SegmentedControl(
                        id='matchup-team',
                        data=[],
                        value=None,
                        radius='md',
                        size='xs',
                    ),
                ],
                justify='flex-start',
                align='center',
                gap='sm',
                mb='sm',
                w='100%',
            ),
            html.Div(id='matchup-status', children=loading_skeleton('table')),
            html.Div(
                dmc.Paper(
                    _matchup_grid(),
                    withBorder=True,
                    radius='md',
                    shadow='xs',
                    mb='md',
                    className='braves-grid-wrap',
                    style={'overflowX': 'auto'},
                ),
                id='matchup-grid-wrap',
                style={'display': 'none'},
            ),
        ],
        id='wrap-matchups',
        style=style,
    )


def matchup_team_value(current, away_id, home_id, triggered_id):
    valid = set()
    if away_id:
        valid.add(str(away_id))
    if home_id:
        valid.add(str(home_id))
    default = str(away_id) if away_id else (str(home_id) if home_id else None)
    if default is None:
        return None
    if triggered_id == 'game_id' or str(current) not in valid:
        return default
    return no_update


def render_lineup_children(lineup_store, lineup_size=5, show_opp=False, match_info=None):
    try:
        size_int = int(lineup_size)
    except Exception as exc:
        log_data.debug('lineup size parse failed: %s', exc)
        size_int = 5
    payload = safe_loads(lineup_store)
    if payload.get('_ui') == 'waiting':
        return [loading_skeleton('table')]
    if payload.get('_ui') == 'error':
        return [_error_view(payload)]
    lineup_dict = lineup_tables_for_size(lineup_store, size_int)
    if not lineup_dict:
        return [_empty_view()]
    children = []
    show_opp = bool(show_opp)
    page_size = (40 if show_opp else 20) if size_int < 5 else None
    away_name, home_name = side_names(match_info)
    ordered = order_named_items(lineup_dict.items(), away_name, home_name)
    for idx, (team_name, l_json) in enumerate(ordered):
        dot_color = section_dot(team_name, away_name, home_name, idx)
        title_section = dmc.Group(
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
        )
        children.append(title_section)
        l_df = read_split_frame(l_json)
        visible = l_df.loc[:, _lineup_visible_columns(l_df)]
        children.append(_ag_grid_from_df(
            visible,
            page_size=page_size,
            filterable_cols=['Lineup', 'Lineups'],
            lineup_size=size_int,
            row_records=_lineup_pair_records(l_df),
            pair_rows=True,
            show_opp=show_opp,
            grid_id=f'lineup-grid-{idx}',
        ))
    return children
