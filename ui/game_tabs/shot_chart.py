# -*- coding: utf-8 -*-
import os

from dash import dcc, html
import dash_mantine_components as dmc

from synergy_reporter.shot_chart import (
    COURT_IMAGE_STYLE,
    court_data_uri,
    court_zones,
    period_chips as shot_period_chips,
    player_options,
)
from ui.components import (
    ERROR_GAME,
    loading_skeleton,
    shot_chart_paper,
    shot_court_column,
)
from ui.game_tabs.common import (
    _empty_view,
    _error_view,
    _game_module,
    _last_update_span,
    _pbp_frame,
    safe_loads,
)


def _shot_chart_court(side):
    return shot_court_column([
        dmc.Text(id=f'shot-chart-name-{side}', fw=700, ta='center', size='sm'),
        dmc.Select(
            id=f'shot-chart-player-{side}',
            data=[{'label': 'All', 'value': 'all'}],
            value='all',
            allowDeselect=False,
            clearable=False,
            size='xs',
            radius='md',
            w='100%',
            comboboxProps={'withinPortal': True},
        ),
        html.Div(
            id=f'shot-chart-court-{side}',
            style={'width': '100%'},
        ),
    ])


def _shot_chart_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    pane = html.Div(id='pane-shot-chart', children=loading_skeleton('chart'))
    if not os.environ.get('SPLASHBOARD_E2E'):
        pane = dcc.Loading(custom_spinner=loading_skeleton('chart'), children=pane)
    return html.Div(
        [
            html.Div(id='shot-chart-last-update', children=_last_update_span()),
            shot_chart_paper(
                [
                    dmc.Box(
                        dmc.SegmentedControl(
                            id='shot-chart-period',
                            data=[{'label': 'All', 'value': 'all'}],
                            value='all',
                            radius='md',
                            size='xs',
                        ),
                        id='shot-chart-period-bar',
                        mb='sm',
                        style={'display': 'none'},
                    ),
                    dmc.SimpleGrid(
                        id='shot-chart-courts',
                        cols={'base': 1, 'sm': 2},
                        spacing='16px',
                        style={'display': 'none'},
                        children=[_shot_chart_court('away'), _shot_chart_court('home')],
                    ),
                    pane,
                ],
                card_id='shot-chart-card',
            ),
        ],
        id='wrap-shot-chart',
        style=style,
    )


def shot_chart_period_state(pbp_store):
    status, frame = _pbp_frame(pbp_store)
    if status != 'ready' or 'periodId' not in getattr(frame, 'columns', []):
        return [{'label': 'All', 'value': 'all'}], {'display': 'none'}
    return shot_period_chips(frame['periodId'].tolist()), {'display': 'flex'}


def shot_chart_player_state(pbp_store, match_info):
    blank = [{'label': 'All', 'value': 'all'}]
    status, frame = _pbp_frame(pbp_store)
    if status != 'ready':
        return blank, blank
    info = safe_loads(match_info)
    return (
        player_options(frame, info.get('away_team_id')),
        player_options(frame, info.get('home_team_id')),
    )


def resolve_shot_chart_filters(triggered_id, period, away_player, home_player):
    if triggered_id == 'game_id':
        return 'all', 'all', 'all'
    return period or 'all', away_player or 'all', home_player or 'all'


def shot_chart_panel(pbp_store, match_info, period, away_player, home_player, fixture_id=None):
    status, frame = _pbp_frame(pbp_store)
    info = safe_loads(match_info)
    if status == 'loading':
        return {'status': 'loading'}
    if status == 'error':
        return {'status': 'error', 'message': ERROR_GAME}
    if status != 'ready':
        return {'status': 'empty'}
    mod = _game_module()
    zones_fn = getattr(mod, 'court_zones', court_zones)
    uri_fn = getattr(mod, 'court_data_uri', court_data_uri)
    return {
        'status': 'ready',
        'away_name': info.get('away_team') or 'Away',
        'home_name': info.get('home_team') or 'Home',
        'away_src': uri_fn(zones_fn(
            frame, info.get('away_team_id'), period=period or 'all',
            player_id=away_player or 'all', fixture_id=fixture_id,
        )),
        'home_src': uri_fn(zones_fn(
            frame, info.get('home_team_id'), period=period or 'all',
            player_id=home_player or 'all', fixture_id=fixture_id,
        )),
    }


def _court_image(src, alt):
    return html.Img(
        src=src,
        alt=alt,
        style=dict(COURT_IMAGE_STYLE),
    )


def shot_chart_outputs(panel):
    hide = {'display': 'none'}
    if panel.get('status') == 'loading':
        return loading_skeleton('chart'), {}, hide, '', '', None, None
    if panel.get('status') == 'error':
        view = [_error_view({'message': panel.get('message') or ERROR_GAME})]
        return view, {}, hide, '', '', None, None
    if panel.get('status') != 'ready':
        return [_empty_view()], {}, hide, '', '', None, None
    return (
        [],
        hide,
        {},
        panel['away_name'],
        panel['home_name'],
        _court_image(panel['away_src'], f"{panel['away_name']} shot chart"),
        _court_image(panel['home_src'], f"{panel['home_name']} shot chart"),
    )
