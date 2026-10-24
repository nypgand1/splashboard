# -*- coding: utf-8 -*-
import json

from dash import (
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
from dash.exceptions import PreventUpdate
from dash.development.base_component import Component
import dash_mantine_components as dmc

from synergy_inbounder.settings import (
    EASL_SEASON_ID,
    SYNERGY_SEASON_ID,
    selectable_seasons,
)
from synergy_reporter.team_season import team_stats_payload, type_needs_download
from ui_kit import (
    ERROR_GAME,
    empty_state,
    error_alert,
    filter_control,
    filter_pack,
    icon,
)

register_page(
    __name__,
    name='Splashboard TFB | Team Stats',
    top_nav=True,
    path='/team-stats',
)

LEAGUE_OPTIONS = [
    {'label': 'PLG', 'value': 'PLG'},
    {'label': 'EASL', 'value': 'EASL'},
]
_KEY_GROUPS = (
    ('Points in the Paint', (('PIPM', 'M'), ('PIPA', 'A'), ('PIP', 'PT'))),
    ('Second Chance Points', (
        ('SCP2M', '2M'), ('SCP2A', '2A'), ('SCP3M', '3M'), ('SCP3A', '3A'), ('SCP', 'PT'),
    )),
    ('Fast Break Points', (
        ('FBP2M', '2M'), ('FBP2A', '2A'), ('FBP3M', '3M'), ('FBP3A', '3A'), ('FBP', 'PT'),
    )),
    ('Points off Turnovers', (
        ('POT2M', '2M'), ('POT2A', '2A'), ('POT3M', '3M'), ('POT3A', '3A'), ('POT', 'PT'),
    )),
)
_SHOT_GROUPS = (
    ('2PT', ('2M', '2A', '2FG%'), ('M', 'A', '%')),
    ('3PT', ('3M', '3A', '3FG%'), ('M', 'A', '%')),
    ('FT', ('FTM', 'FTA', 'FT%'), ('M', 'A', '%')),
    ('REB', ('OR', 'DR', 'REB'), ('O', 'D', 'T')),
)
_COUNT_TAILS = ('AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS')
_TAIL_LABEL = {'AST': 'AS', 'PTS': 'PT'}


def _default_season(league):
    if str(league or '').strip().upper() == 'EASL':
        return EASL_SEASON_ID
    return SYNERGY_SEASON_ID


def _season_data(league):
    return [
        {'label': label, 'value': season_id}
        for label, season_id in selectable_seasons(league)
    ]


def _jsonable(node):
    if isinstance(node, Component):
        spec = node.to_plotly_json()
        spec['props'] = {
            key: _jsonable(value) for key, value in spec['props'].items()
        }
        return spec
    if isinstance(node, (list, tuple)):
        return [_jsonable(item) for item in node]
    if isinstance(node, dict):
        return {key: _jsonable(value) for key, value in node.items()}
    return node


def _loading_body():
    return dmc.Stack(
        [
            dmc.SimpleGrid(
                cols={'base': 1, 'lg': 2},
                spacing='12px',
                children=[dmc.Skeleton(height=160, radius='md') for _ in range(2)],
            ),
            dmc.Skeleton(height=180, radius='md'),
            dmc.Skeleton(height=220, radius='md'),
        ],
        gap='sm',
    )


def _stamp(text):
    return dmc.Text(text or 'Last Update: —', size='sm', c='dimmed', mb=8, className='no-print')


def _th(label, kind, span=None, cols=None):
    table_props = {}
    if span:
        table_props['rowSpan'] = span
    if cols:
        table_props['colSpan'] = cols
    props = {'className': kind}
    if table_props:
        props['tableProps'] = table_props
    return dmc.TableTh(label, **props)


def _span_labels(columns, names):
    present = set(columns)
    nodes = []
    for name in names:
        if name not in present:
            continue
        if name == 'Team':
            label = 'TEAM'
        elif name == 'GP':
            label = 'GP'
        else:
            label = name.upper()
        nodes.append(_th(label, 'braves-th-span', span=2))
    return nodes


def _header_rows(card_id, columns):
    present = set(columns)
    if card_id == 'advanced':
        labels = []
        for column in columns:
            if column == 'Team':
                labels.append('TEAM')
            elif column == 'GP':
                labels.append('GP')
            else:
                labels.append(column)
        return [dmc.TableTr([_th(label, 'braves-th-single') for label in labels])]

    top = []
    sub = []
    if card_id == 'team':
        top.extend(_span_labels(columns, ('Team', 'GP', 'Min')))
        for title, members, leaves in _SHOT_GROUPS:
            if any(column in present for column in members):
                top.append(_th(title, 'braves-th-group', cols=len(leaves)))
                sub.extend(_th(leaf, 'braves-th-sub') for leaf in leaves)
        for column in _COUNT_TAILS:
            if column in present:
                top.append(_th(_TAIL_LABEL.get(column, column), 'braves-th-span-tight', span=2))
    elif card_id == 'key':
        top.extend(_span_labels(columns, ('Team', 'GP')))
        for name, pairs in _KEY_GROUPS:
            found = [(column, label) for column, label in pairs if column in present]
            if not found:
                continue
            top.append(_th(name, 'braves-th-group', cols=len(found)))
            sub.extend(_th(label, 'braves-th-sub') for _column, label in found)
        if 'BP' in present:
            top.append(_th('BP', 'braves-th-span', span=2))
    else:
        top.extend(_span_labels(columns, ('Team', 'GP', 'Pace')))
        factors = [column for column in ('eFG%', 'TO%', 'ORB%', 'FT-R') if column in present]
        if factors:
            top.append(_th('FOUR FACTORS', 'braves-th-group', cols=len(factors)))
            sub.extend(_th(column, 'braves-th-sub') for column in factors)
    rows = [dmc.TableTr(top)]
    if sub:
        rows.append(dmc.TableTr(sub))
    return rows


def _body_rows(card):
    rows = []
    for record in card.get('rows') or []:
        cells = []
        for column in card.get('columns') or []:
            cell = record.get(column) if isinstance(record, dict) else None
            text = ''
            style = None
            if isinstance(cell, dict):
                text = '' if cell.get('text') is None else str(cell.get('text'))
                if cell.get('winner'):
                    style = {'color': '#0077b6', 'fontWeight': 700}
            cells.append(dmc.TableTd(text, style=style))
        rows.append(dmc.TableTr(cells, className='braves-clean-row'))
    return rows


def _paper(card):
    table = dmc.Table(
        [
            dmc.TableThead(_header_rows(card.get('id'), card.get('columns') or [])),
            dmc.TableTbody(_body_rows(card)),
        ],
        withTableBorder=False,
        withColumnBorders=False,
        className='braves-clean-table',
        style={'width': '100%'},
    )
    children = [dmc.Box(table, className='braves-table-scroll')]
    title = card.get('title')
    if title:
        children.insert(0, dmc.Text(
            str(title).upper(),
            size='xs',
            fw=700,
            c='dimmed',
            mb=6,
            style={'letterSpacing': '0.05em'},
        ))
    return dmc.Paper(
        children,
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def _cards_view(cards):
    return dmc.Stack(
        [
            dmc.SimpleGrid(
                cols={'base': 1, 'lg': 2},
                spacing='12px',
                children=[_paper(cards['pace']), _paper(cards['advanced'])],
            ),
            _paper(cards['key']),
            _paper(cards['team']),
        ],
        gap='sm',
    )


def _view(payload):
    if not payload or not payload.get('ok'):
        return error_alert((payload or {}).get('message') or ERROR_GAME)
    if payload.get('empty') or not payload.get('cards'):
        return empty_state(payload.get('message') or '', payload.get('next_step') or '')
    return _cards_view(payload['cards'])


def layout():
    league = 'PLG'
    season_id = _default_season(league)
    league_control = dmc.SegmentedControl(
        id='ts-league',
        data=LEAGUE_OPTIONS,
        value=league,
        radius='md',
        size='xs',
    )
    season_control = dmc.Select(
        id='ts-season',
        data=_season_data(league),
        value=season_id,
        allowDeselect=False,
        clearable=False,
        searchable=False,
        size='xs',
        radius='md',
        w=132,
        comboboxProps={'withinPortal': True},
    )
    type_control = dmc.SegmentedControl(
        id='ts-game-type',
        data=[{'label': 'Regular', 'value': 'REGULAR'}],
        value='REGULAR',
        radius='md',
        size='xs',
    )
    return dmc.Stack(
        [
            dcc.Store(id='ts-filter-pack-sync'),
            dcc.Store(
                id='ts-applied',
                data={'league': league, 'season': season_id, 'game_type': 'REGULAR'},
            ),
            dcc.Store(id='ts-intent'),
            dcc.Store(id='ts-job'),
            dmc.Tabs(
                dmc.TabsList([
                    dmc.TabsTab(
                        'Box Score',
                        value='tab-bs',
                        leftSection=icon('tabler:table', width=14),
                    ),
                ]),
                id='ts-tabs',
                value='tab-bs',
                variant='default',
                className='braves-clean-tabs',
                style={'margin': '0 0 16px 0', 'padding': '0', 'borderBottom': 'none'},
            ),
            html.Div(_stamp('Last Update: —'), id='ts-stamp'),
            filter_pack(
                'ts-filter-pack',
                [
                    (
                        'league',
                        [
                            filter_control('', league_control, wrap_id='ts-league-wrap'),
                            filter_control('', season_control, wrap_id='ts-season-wrap'),
                        ],
                    ),
                    (
                        'type',
                        [
                            filter_control(
                                '',
                                type_control,
                                wrap_id='ts-game-type-wrap',
                                visible=False,
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Group(
                [
                    dmc.SegmentedControl(
                        id='ts-period',
                        data=[{'label': 'All', 'value': 'all'}],
                        value='all',
                        radius='md',
                        size='xs',
                    ),
                ],
                id='ts-period-bar',
                wrap='wrap',
                gap='sm',
                style={'display': 'none'},
            ),
            html.Div(_loading_body(), id='ts-body'),
        ],
        gap='md',
    )


_LOADING_BODY = json.dumps(_jsonable(_loading_body()))

clientside_callback(
    """
    function(league, season, gameType, applied) {
        var current = applied || {};
        var leagueValue = league == null ? null : league;
        var seasonValue = season == null ? null : season;
        var typeValue = gameType == null ? null : gameType;
        var sameLeague = leagueValue == (current.league == null ? null : current.league);
        var sameSeason = seasonValue == (current.season == null ? null : current.season);
        var sameType = typeValue == (current.game_type == null ? null : current.game_type);
        if (sameLeague && sameSeason && sameType) {
            return window.dash_clientside.no_update;
        }
        var scope = !sameLeague || !sameSeason;
        return {
            league: leagueValue,
            season: seasonValue,
            game_type: scope ? null : typeValue,
            skeleton: scope,
            nonce: Date.now()
        };
    }
    """,
    Output('ts-intent', 'data'),
    Input('ts-league', 'value'),
    Input('ts-season', 'value'),
    Input('ts-game-type', 'value'),
    State('ts-applied', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(intent) {
        if (!intent || !intent.skeleton) {
            return window.dash_clientside.no_update;
        }
        return __LOADING_BODY__;
    }
    """.replace('__LOADING_BODY__', _LOADING_BODY),
    Output('ts-body', 'children', allow_duplicate=True),
    Input('ts-intent', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function() {
        var api = window.dash_clientside && window.dash_clientside.filter_pack;
        if (api && api.sync) {
            api.sync();
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('ts-filter-pack-sync', 'data'),
    Input('ts-body', 'children'),
    Input('ts-game-type', 'data'),
)


def _same(left, right):
    return left == right


def _triggered_id():
    try:
        return ctx.triggered_id
    except Exception:
        return None


def _load(league, season_id, game_type, period, reason):
    try:
        return team_stats_payload(
            league or 'PLG',
            season_id=season_id,
            game_type=game_type,
            period=period,
            reason=reason,
        )
    except Exception:
        return {
            'ok': False,
            'message': ERROR_GAME,
            'stamp': 'Last Update: —',
            'season_id': season_id,
            'seasons': _season_data(league or 'PLG'),
            'game_type': game_type,
            'game_types': [],
            'game_type_visible': False,
            'period': 'all',
            'period_chips': [],
            'period_visible': False,
        }


def _paint(payload, league, season_id, game_type, period):
    seasons = payload.get('seasons') or _season_data(league or 'PLG')
    selected_season = payload.get('season_id') or season_id
    types = payload.get('game_types') or []
    selected_type = payload.get('game_type')
    if not types:
        types = [{'label': 'Regular', 'value': 'REGULAR'}]
    chips = payload.get('period_chips') or [{'label': 'All', 'value': 'all'}]
    selected_period = payload.get('period') or 'all'
    if not any(item.get('value') == selected_period for item in chips):
        selected_period = 'all'
    type_style = None if payload.get('game_type_visible') else {'display': 'none'}
    period_style = None if payload.get('period_visible') else {'display': 'none'}
    season_out = no_update if _same(selected_season, season_id) else selected_season
    type_out = no_update if _same(selected_type, game_type) else selected_type
    period_out = no_update if _same(selected_period, period) else selected_period
    # Same response as any select correction, so the bridge's applied State
    # already matches and that echo does not fetch again.
    applied = {
        'league': league or 'PLG',
        'season': season_id if season_out is no_update else selected_season,
        'game_type': game_type if type_out is no_update else selected_type,
    }
    return (
        _view(payload),
        _stamp(payload.get('stamp')),
        seasons,
        season_out,
        types,
        type_out,
        type_style,
        chips,
        period_out,
        period_style,
        applied,
    )


def _view_outputs():
    return (
        Output('ts-body', 'children', allow_duplicate=True),
        Output('ts-stamp', 'children', allow_duplicate=True),
        Output('ts-season', 'data', allow_duplicate=True),
        Output('ts-season', 'value', allow_duplicate=True),
        Output('ts-game-type', 'data', allow_duplicate=True),
        Output('ts-game-type', 'value', allow_duplicate=True),
        Output('ts-game-type-wrap', 'style', allow_duplicate=True),
        Output('ts-period', 'data', allow_duplicate=True),
        Output('ts-period', 'value', allow_duplicate=True),
        Output('ts-period-bar', 'style', allow_duplicate=True),
        Output('ts-applied', 'data', allow_duplicate=True),
    )


def _skeleton_job(intent, period):
    # Reset the chip with the skeleton. This callback also listens to the
    # chip, and Dash drops that echo, so the download callback paints All.
    period_out = no_update if _same(period, 'all') else 'all'
    return (
        _loading_body(),
        no_update, no_update, no_update, no_update, no_update, no_update,
        no_update, period_out, no_update, no_update,
        intent,
    )


@callback(
    *_view_outputs(),
    Output('ts-job', 'data'),
    Input('ts-intent', 'data'),
    Input('ts-period', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    prevent_initial_call='initial_duplicate',
)
def render_team_stats(intent, period, league, season_id, game_type):
    triggered = _triggered_id()
    if triggered == 'ts-period':
        reason = 'chip'
    elif isinstance(intent, dict) and not intent.get('skeleton'):
        reason = 'type'
    else:
        reason = 'scope'
    if reason == 'type':
        requested_type = intent.get('game_type') if isinstance(intent, dict) else game_type
        try:
            needs = type_needs_download(league, season_id, requested_type)
        except Exception:
            needs = True
        if needs:
            job = intent if isinstance(intent, dict) else {
                'league': league,
                'season': season_id,
                'game_type': requested_type,
                'skeleton': False,
            }
            return _skeleton_job(job, period)
        payload = _load(league, season_id, requested_type, 'all', 'type')
        return _paint(payload, league, season_id, game_type, period) + (no_update,)
    if reason == 'chip':
        payload = _load(league, season_id, game_type, period or 'all', 'chip')
        painted = _paint(payload, league, season_id, game_type, period)
        return painted[:-1] + (no_update, no_update)
    payload = _load(league, season_id, None, 'all', 'scope')
    return _paint(payload, league, season_id, game_type, period) + (no_update,)


@callback(
    *_view_outputs(),
    Input('ts-job', 'data'),
    State('ts-intent', 'data'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-period', 'value'),
    prevent_initial_call=True,
)
def render_team_stats_download(job, intent, league, season_id, game_type, period):
    if not isinstance(job, dict) or not isinstance(intent, dict):
        raise PreventUpdate
    if job.get('nonce') != intent.get('nonce'):
        raise PreventUpdate
    league = job.get('league') or league or 'PLG'
    if job.get('season') is not None:
        season_id = job.get('season')
    requested_type = job.get('game_type') if isinstance(job, dict) else game_type
    payload = _load(league, season_id, requested_type, 'all', 'type')
    return _paint(payload, league, season_id, game_type, period)
