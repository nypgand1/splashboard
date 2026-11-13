# -*- coding: utf-8 -*-
import json

from dash import (
    ALL,
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

from synergy_inbounder.logs import data as log_data
from synergy_inbounder.logs import unexpected as log_unexpected
from synergy_inbounder.names import TEAM_TBD, display_name
from synergy_inbounder.publisher import note_season, peek_season
from synergy_inbounder.runtime_cache import LIVE_CADENCE_SECONDS
from synergy_inbounder.settings import (
    EASL_SEASON_ID,
    SYNERGY_SEASON_ID,
    organization_for_league,
    selectable_seasons,
)
from synergy_reporter.rotation import period_label
from synergy_reporter.shot_chart import COURT_IMAGE_STYLE, court_data_uri, season_zones
from synergy_reporter.team_lineups import (
    EMPTY_LINEUPS,
    EMPTY_MATCHUPS,
    season_lineup_records,
    season_matchup_records,
)
from synergy_reporter.team_rotation import (
    ROTATION_EMPTY,
    ROTATION_SELECT,
    ROTATION_SELECT_NEXT,
    build_team_rotation_figure,
    season_aggregate,
)
from synergy_reporter.team_season import (
    EMPTY_TEAM_STATS,
    EMPTY_TEAM_STATS_NEXT,
    OPPONENT_ALL,
    OPPONENT_ALL_LABEL,
    SITE_ALL,
    SITE_OPTIONS,
    STADIUM_ALL,
    STADIUM_ALL_LABEL,
    TEAM_ALL,
    TEAM_ALL_LABEL,
    next_team_sort,
    order_team_cards,
    rotation_games,
    schedule_chrome,
    team_stats_payload,
)
from domain.schedule_filters import (
    LEAGUE_OPTIONS,
    default_season_id as _default_season,
    selectable_season_options as _season_data,
)
from ui.game_tabs.lineup_matchups import team_lineup_grid, team_matchup_grid
from ui.tables.stat_cards import (
    COUNT_TAILS as _COUNT_TAILS,
    KEY_STAT_GROUPS as _KEY_GROUPS,
    SHOT_GROUPS as _SHOT_GROUPS,
    TAIL_LABEL as _TAIL_LABEL,
    card_header_rows as _header_rows,
    card_segments as _segments,
    edge_columns as _edge_columns,
    span_labels as _span_labels,
    stat_th as _th,
    team_label_cell as _team_label,
    team_stats_body_rows as _body_rows,
    team_stats_cards_view as _cards_view,
    team_stats_paper as _paper,
)
from ui_kit import (
    ERROR_GAME,
    empty_state,
    error_alert,
    filter_cluster as _cluster,
    filter_control,
    icon,
    last_update_line,
    loading_skeleton,
    shot_chart_paper,
    shot_court_column,
    sized_select as _sized_select,
    team_name_lines,
    to_jsonable as _jsonable,
)

register_page(
    __name__,
    name='Splashboard TFB | Team Stats',
    top_nav=True,
    path='/team-stats',
)


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
    return last_update_line(text)


def _view(payload, sort=None):
    if not payload or not payload.get('ok'):
        return error_alert((payload or {}).get('message') or ERROR_GAME)
    if payload.get('empty') or not payload.get('cards'):
        return empty_state(payload.get('message') or '', payload.get('next_step') or '')
    return _cards_view(order_team_cards(payload['cards'], sort), sort)


def _rotation_pane():
    return html.Div(id='ts-rotation', style={'display': 'none'})


def _shot_pane():
    return html.Div(
        shot_chart_paper(
            [
                dmc.Box(
                    dmc.SegmentedControl(
                        id='ts-shot-period',
                        data=[{'label': 'All', 'value': 'all'}],
                        value='all',
                        radius='md',
                        size='xs',
                    ),
                    id='ts-shot-period-bar',
                    mb='sm',
                    style={'display': 'none'},
                ),
                html.Div(id='ts-shot-body'),
            ],
            card_id='ts-shot-card',
        ),
        id='ts-shot',
        style={'display': 'none'},
    )


def _lineup_pane():
    return html.Div(
        [
            dcc.Store(id='ts-lineup-show-opp-sync'),
            dmc.Group(
                [
                    dmc.SegmentedControl(
                        id='ts-lineup-size',
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
                        id='ts-lineup-show-opp',
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
            ),
            html.Div(id='ts-lineup-body'),
        ],
        id='ts-lineup',
        style={'display': 'none'},
    )


def _matchup_pane():
    return html.Div(
        html.Div(id='ts-matchups-body'),
        id='ts-matchups',
        style={'display': 'none'},
    )


def _opp_chart_name(opponent, id_table):
    if not opponent or opponent == OPPONENT_ALL:
        return 'Opp'
    bare = display_name(id_table, opponent)
    if bare == TEAM_TBD:
        return 'Opp'
    return bare


def _shot_column(name, zones):
    return shot_court_column([
        dmc.Text(name, fw=700, ta='center', size='sm'),
        html.Img(
            src=court_data_uri(zones),
            alt='{0} shot chart'.format(name),
            style=dict(COURT_IMAGE_STYLE),
        ),
    ])


def _shot_courts(team_name, team_zones, opp_name, opp_zones):
    return dmc.SimpleGrid(
        cols={'base': 1, 'sm': 2},
        spacing='16px',
        children=[
            _shot_column(team_name, team_zones),
            _shot_column(opp_name, opp_zones),
        ],
    )


def _shot_skeleton_column():
    return shot_court_column([
        dmc.Skeleton(height=14, width=160, radius='sm'),
        dmc.Skeleton(
            radius='md',
            style={'width': '100%', 'aspectRatio': '380.05 / 400.51'},
        ),
    ])


def shot_chart_skeleton():
    return dmc.SimpleGrid(
        cols={'base': 1, 'sm': 2},
        spacing='16px',
        children=[_shot_skeleton_column(), _shot_skeleton_column()],
    )


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
    team_control = _sized_select(
        'ts-team',
        'ts-team-probes',
        TEAM_ALL_LABEL,
        [{'label': TEAM_ALL_LABEL, 'value': TEAM_ALL}],
        TEAM_ALL,
    )
    opponent_control = _sized_select(
        'ts-opponent',
        'ts-opponent-probes',
        OPPONENT_ALL_LABEL,
        [{'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL}],
        OPPONENT_ALL,
    )
    stadium_control = _sized_select(
        'ts-stadium',
        'ts-stadium-probes',
        STADIUM_ALL_LABEL,
        [{'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL}],
        STADIUM_ALL,
    )
    site_control = dmc.SegmentedControl(
        id='ts-site',
        data=list(SITE_OPTIONS),
        value=SITE_ALL,
        radius='md',
        size='xs',
    )
    return dmc.Stack(
        [
            dcc.Store(id='ts-filter-pack-sync'),
            dcc.Store(id='ts-sizer-sync'),
            dcc.Store(id='ts-show-opp-memory'),
            dcc.Store(id='ts-sort', data=None, storage_type='memory'),
            dcc.Store(id='ts-opponent-width', data=[OPPONENT_ALL_LABEL]),
            dcc.Store(
                id='ts-applied',
                data={'league': league, 'season': season_id, 'game_type': 'REGULAR'},
            ),
            dcc.Store(id='ts-intent'),
            dcc.Store(id='ts-job'),
            dcc.Store(id='ts-seen', data=0),
            dcc.Interval(
                id='ts-interval',
                interval=LIVE_CADENCE_SECONDS * 1000,
                n_intervals=0,
            ),
            dcc.Store(
                id='ts-slice',
                data={
                    'team': TEAM_ALL,
                    'opponent': OPPONENT_ALL,
                    'stadium': STADIUM_ALL,
                    'site': SITE_ALL,
                },
            ),
            dmc.Tabs(
                dmc.TabsList([
                    dmc.TabsTab(
                        'Box Score',
                        value='tab-bs',
                        leftSection=icon('tabler:table', width=14),
                    ),
                    dmc.TabsTab(
                        'Rotation',
                        value='tab-rotation',
                        leftSection=icon('tabler:chart-bar', width=14),
                    ),
                    dmc.TabsTab(
                        'Shot Chart',
                        value='tab-shot-chart',
                        leftSection=icon('tabler:ball-basketball', width=14),
                    ),
                    dmc.TabsTab(
                        'Lineup Stats',
                        value='tab-lineup',
                        leftSection=icon('tabler:users', width=14),
                    ),
                    dmc.TabsTab(
                        'Matchups',
                        value='tab-matchups',
                        leftSection=icon('tabler:users-group', width=14),
                    ),
                ]),
                id='ts-tabs',
                value='tab-bs',
                variant='default',
                className='braves-clean-tabs',
                style={'margin': '0 0 16px 0', 'padding': '0', 'borderBottom': 'none'},
            ),
            html.Div(_stamp('Last Update: —'), id='ts-stamp'),
            dmc.Box(
                [
                    _cluster('league', [
                        filter_control('', league_control, wrap_id='ts-league-wrap'),
                        filter_control('', season_control, wrap_id='ts-season-wrap'),
                    ]),
                    _cluster('type', [
                        filter_control(
                            '',
                            type_control,
                            wrap_id='ts-game-type-wrap',
                            visible=False,
                        ),
                    ]),
                ],
                id='ts-filter-pack',
                className='filter-pack filter-pack-scope',
            ),
            dmc.Box(
                [
                    _cluster(
                        'team',
                        [filter_control('', team_control)],
                        cluster_id='ts-team-cluster',
                        style={'display': 'none'},
                    ),
                    _cluster(
                        'opp',
                        [filter_control('', opponent_control)],
                        cluster_id='ts-opponent-cluster',
                        style={'display': 'none'},
                    ),
                ],
                id='ts-match-pack',
                className='filter-pack filter-pack-match',
            ),
            dmc.Box(
                [
                    _cluster(
                        'stadium',
                        [filter_control('', stadium_control)],
                        cluster_id='ts-stadium-cluster',
                        style={'display': 'none'},
                    ),
                    _cluster('site', [
                        filter_control('', site_control, wrap_id='ts-site-wrap'),
                    ]),
                ],
                id='ts-place-pack',
                className='filter-pack filter-pack-place',
            ),
            dmc.Group(
                [
                    html.Div(
                        dmc.SegmentedControl(
                            id='ts-period',
                            data=[{'label': 'All', 'value': 'all'}],
                            value='all',
                            radius='md',
                            size='xs',
                        ),
                        id='ts-period-wrap',
                        style={'display': 'none'},
                    ),
                    dmc.Switch(
                        id='ts-show-opp',
                        label='Show Opp',
                        checked=False,
                        size='sm',
                        color='gray',
                        ms='auto',
                    ),
                ],
                id='ts-period-bar',
                justify='flex-start',
                align='center',
                wrap='wrap',
                gap='sm',
                w='100%',
            ),
            html.Div(_loading_body(), id='ts-body'),
            _rotation_pane(),
            _shot_pane(),
            _lineup_pane(),
            _matchup_pane(),
        ],
        gap='md',
    )


_LOADING_BODY = json.dumps(_jsonable(_loading_body()))
_CHART_LOADING = json.dumps(_jsonable(loading_skeleton('chart')))
_SHOT_LOADING = json.dumps(_jsonable(shot_chart_skeleton()))
_TABLE_LOADING = json.dumps(_jsonable(loading_skeleton('table')))
_ROTATION_PICK = json.dumps(_jsonable(empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)))

clientside_callback(
    """
    function(checked) {
        return checked ? 'ts-show-opp' : '';
    }
    """,
    Output('ts-body', 'className'),
    Input('ts-show-opp', 'checked'),
)

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
            season: sameLeague ? seasonValue : null,
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
    function(intent) {
        var skip = window.dash_clientside.no_update;
        if (!intent || intent.nonce == null) {
            return [skip, skip, skip, skip];
        }
        return [__CHART_LOADING__, __SHOT_LOADING__, __TABLE_LOADING__, __TABLE_LOADING__];
    }
    """.replace('__CHART_LOADING__', _CHART_LOADING).replace(
        '__SHOT_LOADING__', _SHOT_LOADING,
    ).replace('__TABLE_LOADING__', _TABLE_LOADING),
    Output('ts-rotation', 'children', allow_duplicate=True),
    Output('ts-shot-body', 'children', allow_duplicate=True),
    Output('ts-lineup-body', 'children', allow_duplicate=True),
    Output('ts-matchups-body', 'children', allow_duplicate=True),
    Input('ts-intent', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(team, opponent, stadium, site, painted) {
        var current = painted || {};
        function same(left, right) {
            var a = left == null ? null : left;
            var b = right == null ? null : right;
            return a == b;
        }
        var skip = window.dash_clientside.no_update;
        if (
            same(team, current.team)
            && same(opponent, current.opponent)
            && same(stadium, current.stadium)
            && same(site, current.site)
        ) {
            return [skip, skip, skip, skip, skip];
        }
        var cards = skip;
        if (current.team && current.team !== 'all' && (team === 'all' || team == null)) {
            cards = __LOADING_BODY__;
        }
        var chart = __CHART_LOADING__;
        var shot = skip;
        var lineup = skip;
        var matchup = skip;
        if (team === 'all' || team == null) {
            chart = __ROTATION_PICK__;
            shot = __ROTATION_PICK__;
            lineup = __ROTATION_PICK__;
            matchup = __ROTATION_PICK__;
        } else if (!same(team, current.team)) {
            shot = __SHOT_LOADING__;
            lineup = __TABLE_LOADING__;
            matchup = __TABLE_LOADING__;
        }
        return [cards, chart, shot, lineup, matchup];
    }
    """.replace('__LOADING_BODY__', _LOADING_BODY).replace(
        '__CHART_LOADING__', _CHART_LOADING,
    ).replace('__SHOT_LOADING__', _SHOT_LOADING).replace(
        '__TABLE_LOADING__', _TABLE_LOADING,
    ).replace(
        '__ROTATION_PICK__', _ROTATION_PICK,
    ),
    Output('ts-body', 'children', allow_duplicate=True),
    Output('ts-rotation', 'children', allow_duplicate=True),
    Output('ts-shot-body', 'children', allow_duplicate=True),
    Output('ts-lineup-body', 'children', allow_duplicate=True),
    Output('ts-matchups-body', 'children', allow_duplicate=True),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    State('ts-slice', 'data'),
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
    Input('ts-team', 'data'),
    Input('ts-opponent', 'data'),
    Input('ts-stadium', 'data'),
)


clientside_callback(
    """
    function(teamOptions, opponentLabels, stadiumOptions) {
        var api = window.dash_clientside && window.dash_clientside.filter_pack;
        if (api && api.fillProbes) {
            api.fillProbes(teamOptions, opponentLabels, stadiumOptions);
        }
        if (api && api.sync) {
            api.sync();
            window.setTimeout(api.sync, 0);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('ts-sizer-sync', 'data'),
    Input('ts-team', 'data'),
    Input('ts-opponent-width', 'data'),
    Input('ts-stadium', 'data'),
)


clientside_callback(
    """
    function(tab) {
        var hidden = {display: 'none'};
        if (tab === 'tab-rotation') return [hidden, hidden, null, hidden, null, hidden, hidden];
        if (tab === 'tab-shot-chart') return [hidden, hidden, hidden, null, hidden, hidden, hidden];
        if (tab === 'tab-lineup') return [hidden, hidden, hidden, hidden, hidden, null, hidden];
        if (tab === 'tab-matchups') return [hidden, hidden, hidden, hidden, hidden, hidden, null];
        return [null, null, hidden, hidden, null, hidden, hidden];
    }
    """,
    Output('ts-period-bar', 'style'),
    Output('ts-body', 'style'),
    Output('ts-rotation', 'style'),
    Output('ts-shot', 'style'),
    Output('ts-show-opp', 'style'),
    Output('ts-lineup', 'style'),
    Output('ts-matchups', 'style'),
    Input('ts-tabs', 'value'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(checked) {
        if (window.applyLineupShowOpp) {
            window.applyLineupShowOpp(!!checked);
        }
        return !!checked;
    }
    """,
    Output('ts-lineup-show-opp-sync', 'data'),
    Input('ts-lineup-show-opp', 'checked'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(period, shotPeriod) {
        var context = window.dash_clientside.callback_context || {};
        var triggered = (context.triggered && context.triggered[0]) || {};
        var prop = triggered.prop_id || '';
        var skip = window.dash_clientside.no_update;
        if (prop.indexOf('ts-shot-period') === 0) {
            if (shotPeriod == null || shotPeriod === '' || shotPeriod == period) {
                return [skip, skip];
            }
            return [shotPeriod, skip];
        }
        if (period == null || period === '' || period == shotPeriod) {
            return [skip, skip];
        }
        return [skip, period];
    }
    """,
    Output('ts-period', 'value', allow_duplicate=True),
    Output('ts-shot-period', 'value', allow_duplicate=True),
    Input('ts-period', 'value'),
    Input('ts-shot-period', 'value'),
    prevent_initial_call=True,
)


def _same(left, right):
    return left == right


def _triggered_id():
    try:
        return ctx.triggered_id
    except Exception as exc:
        log_data.debug('team stats triggered id unavailable: %s', exc)
        return None


def _menu_value(payload, key, options, fallback):
    selected = payload.get(key) or fallback
    if not any(item.get('value') == selected for item in options):
        return fallback
    return selected


def _load(
    league, season_id, game_type, period, reason,
    opponent=OPPONENT_ALL, stadium=STADIUM_ALL, site=SITE_ALL, team=TEAM_ALL,
):
    try:
        return team_stats_payload(
            league or 'PLG',
            season_id=season_id,
            game_type=game_type,
            period=period,
            reason=reason,
            opponent=opponent,
            stadium=stadium,
            site=site,
            team=team,
        )
    except Exception:
        log_unexpected.exception('team stats page load failed')
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
            'opponent': OPPONENT_ALL,
            'opponent_options': [{'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL}],
            'opponent_visible': False,
            'stadium': STADIUM_ALL,
            'stadium_options': [{'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL}],
            'stadium_visible': False,
            'site': SITE_ALL,
        }


def _paint(payload, league, season_id, game_type, period, opponent, stadium, site, team=TEAM_ALL, sort=None):
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
    opponent_options = payload.get('opponent_options') or [
        {'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL},
    ]
    stadium_options = payload.get('stadium_options') or [
        {'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL},
    ]
    selected_opponent = _menu_value(payload, 'opponent', opponent_options, OPPONENT_ALL)
    selected_stadium = _menu_value(payload, 'stadium', stadium_options, STADIUM_ALL)
    selected_site = payload.get('site') or SITE_ALL
    if selected_site not in ('all', 'away', 'home'):
        selected_site = SITE_ALL
    team_options = payload.get('team_options') or [
        {'label': TEAM_ALL_LABEL, 'value': TEAM_ALL},
    ]
    selected_team = _menu_value(payload, 'team', team_options, TEAM_ALL)
    width_labels = payload.get('opponent_width_labels') or [
        item.get('label') for item in opponent_options if item.get('label')
    ]
    type_style = None if payload.get('game_type_visible') else {'display': 'none'}
    period_style = None if payload.get('period_visible') else {'display': 'none'}
    opponent_style = None if payload.get('opponent_visible') else {'display': 'none'}
    stadium_style = None if payload.get('stadium_visible') else {'display': 'none'}
    team_style = None if payload.get('team_visible') else {'display': 'none'}
    season_out = no_update if _same(selected_season, season_id) else selected_season
    type_out = no_update if _same(selected_type, game_type) else selected_type
    period_out = no_update if _same(selected_period, period) else selected_period
    opponent_out = no_update if _same(selected_opponent, opponent) else selected_opponent
    stadium_out = no_update if _same(selected_stadium, stadium) else selected_stadium
    site_out = no_update if _same(selected_site, site) else selected_site
    team_out = no_update if _same(selected_team, team) else selected_team
    # Same response as any select correction, so the bridge's applied State
    # already matches and that echo does not fetch again.
    applied = {
        'league': league or 'PLG',
        'season': season_id if season_out is no_update else selected_season,
        'game_type': game_type if type_out is no_update else selected_type,
        'ok': payload.get('ok') is not False,
    }
    return (
        _view(payload, sort),
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
        opponent_options,
        opponent_out,
        opponent_style,
        stadium_options,
        stadium_out,
        stadium_style,
        site_out,
        team_options,
        team_out,
        team_style,
        width_labels,
        {
            'team': selected_team,
            'opponent': selected_opponent,
            'stadium': selected_stadium,
            'site': selected_site,
        },
        chips,
        period_out,
        period_style,
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
        Output('ts-period-wrap', 'style', allow_duplicate=True),
        Output('ts-applied', 'data', allow_duplicate=True),
        Output('ts-opponent', 'data', allow_duplicate=True),
        Output('ts-opponent', 'value', allow_duplicate=True),
        Output('ts-opponent-cluster', 'style', allow_duplicate=True),
        Output('ts-stadium', 'data', allow_duplicate=True),
        Output('ts-stadium', 'value', allow_duplicate=True),
        Output('ts-stadium-cluster', 'style', allow_duplicate=True),
        Output('ts-site', 'value', allow_duplicate=True),
        Output('ts-team', 'data', allow_duplicate=True),
        Output('ts-team', 'value', allow_duplicate=True),
        Output('ts-team-cluster', 'style', allow_duplicate=True),
        Output('ts-opponent-width', 'data', allow_duplicate=True),
        Output('ts-slice', 'data', allow_duplicate=True),
        Output('ts-shot-period', 'data', allow_duplicate=True),
        Output('ts-shot-period', 'value', allow_duplicate=True),
        Output('ts-shot-period-bar', 'style', allow_duplicate=True),
    )


def _local_paint(payload, league, season_id, game_type, period, opponent, stadium, site, team=TEAM_ALL, sort=None):
    painted = _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
        sort=sort,
    )
    # applied stays. The slice outputs follow it. The job slot is the caller's.
    return painted[:10] + (no_update,) + painted[11:]


def _menu_hold(payload, league, season_id, game_type, period, opponent, stadium, site, team, job):
    """Schedule paint: menus and applied move, cards stay on the skeleton."""
    painted = _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    )
    return (_loading_body(), no_update) + painted[2:] + (job,)


def _card_job(intent, league, season_id, game_type, team, opponent, stadium, site):
    nonce = intent.get('nonce') if isinstance(intent, dict) else None
    return {
        'league': league,
        'season': season_id,
        'game_type': game_type,
        'team': team,
        'opponent': opponent,
        'stadium': stadium,
        'site': site,
        'skeleton': False,
        'phase': 'cards',
        'nonce': nonce,
    }


def _paint_from_chrome(
    reason, intent, league, season_id, game_type, period,
    opponent, stadium, site, team,
):
    reset = reason == 'scope'
    requested = None if reset else (
        intent.get('game_type') if isinstance(intent, dict) else game_type
    )
    try:
        chrome = schedule_chrome(
            league,
            season_id=season_id,
            game_type=requested,
            reset=reset,
            team=TEAM_ALL if reset else team,
            opponent=OPPONENT_ALL if reset else opponent,
            stadium=STADIUM_ALL if reset else stadium,
            site=SITE_ALL if reset else site,
        )
    except Exception:
        log_unexpected.exception('team stats schedule chrome failed')
        chrome = {
            'ok': False,
            'needs_cards': False,
            'message': ERROR_GAME,
            'stamp': 'Last Update: —',
            'season_id': season_id,
            'seasons': _season_data(league or 'PLG'),
            'game_types': [],
            'game_type': None,
            'game_type_visible': False,
            'period': 'all',
            'period_visible': False,
        }
    if chrome.get('ok') is False:
        return _paint(
            chrome, league, season_id, game_type, period, opponent, stadium, site, team,
        ) + (no_update,)
    resolved_season = chrome.get('season_id') or season_id
    if chrome.get('needs_cards'):
        job = _card_job(
            intent, league, resolved_season, chrome.get('game_type'),
            chrome.get('team', TEAM_ALL),
            chrome.get('opponent', OPPONENT_ALL),
            chrome.get('stadium', STADIUM_ALL),
            chrome.get('site', SITE_ALL),
        )
        return _menu_hold(
            chrome, league, season_id, game_type, period, opponent, stadium, site, team, job,
        )
    if reason == 'scope':
        payload = _load(
            league, resolved_season, None, 'all', 'scope',
            OPPONENT_ALL, STADIUM_ALL, SITE_ALL, TEAM_ALL,
        )
    else:
        chosen_type = chrome.get('game_type') if chrome.get('game_type') is not None else requested
        payload = _load(
            league, resolved_season, chosen_type, 'all', 'type',
            opponent, stadium, site, team,
        )
    return _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    ) + (no_update,)


@callback(
    *_view_outputs(),
    Output('ts-job', 'data'),
    Input('ts-intent', 'data'),
    Input('ts-period', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    Input('ts-team', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-sort', 'data'),
    prevent_initial_call='initial_duplicate',
)
def render_team_stats(intent, period, opponent, stadium, site, team, league, season_id, game_type, sort=None):
    triggered = _triggered_id()
    # The click lives on ts-intent. Control State can still be the previous
    # value when this callback runs, so a league, season, or game-type click
    # loads from the store.
    clicked = triggered == 'ts-intent' and isinstance(intent, dict)
    if clicked:
        if intent.get('league'):
            league = intent.get('league')
        if intent.get('season') is not None:
            season_id = intent.get('season')
    if triggered == 'ts-period':
        reason = 'chip'
    elif triggered in ('ts-opponent', 'ts-stadium', 'ts-site', 'ts-team'):
        reason = 'slice'
    elif isinstance(intent, dict) and not intent.get('skeleton'):
        reason = 'type'
    else:
        reason = 'scope'
    if reason == 'type' or (reason == 'scope' and clicked):
        return _paint_from_chrome(
            reason, intent, league, season_id, game_type, period,
            opponent, stadium, site, team,
        )
    if reason in ('chip', 'slice'):
        payload = _load(
            league, season_id, game_type, period or 'all', reason,
            opponent, stadium, site, team,
        )
        return _local_paint(
            payload, league, season_id, game_type, period, opponent, stadium, site, team,
            sort=sort if reason == 'chip' else None,
        ) + (no_update,)
    payload = _load(
        league, season_id, None, 'all', 'scope',
        OPPONENT_ALL, STADIUM_ALL, SITE_ALL, TEAM_ALL,
    )
    return _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    ) + (no_update,)


@callback(
    Output('ts-sort', 'data', allow_duplicate=True),
    Input('ts-intent', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    prevent_initial_call=True,
)
def clear_team_stats_sort(_intent, _team, _opponent, _stadium, _site):
    return None


@callback(
    Output('ts-sort', 'data', allow_duplicate=True),
    Output('ts-body', 'children', allow_duplicate=True),
    Input({'type': 'ts-sort-th', 'card': ALL, 'column': ALL}, 'n_clicks'),
    State('ts-sort', 'data'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-period', 'value'),
    State('ts-opponent', 'value'),
    State('ts-stadium', 'value'),
    State('ts-site', 'value'),
    State('ts-team', 'value'),
    prevent_initial_call=True,
)
def sort_team_stats_cards(
    _clicks, sort, league, season_id, game_type, period, opponent, stadium, site, team,
):
    triggered = ctx.triggered or []
    if not triggered or not triggered[0].get('value'):
        raise PreventUpdate
    ident = ctx.triggered_id
    if not isinstance(ident, dict) or not ident.get('column'):
        raise PreventUpdate
    nxt = next_team_sort(sort, ident.get('column'))
    payload = _load(
        league, season_id, game_type, period or 'all', 'chip',
        opponent, stadium, site, team,
    )
    return nxt, _view(payload, nxt)


@callback(
    *_view_outputs(),
    Input('ts-job', 'data'),
    State('ts-intent', 'data'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-period', 'value'),
    State('ts-opponent', 'value'),
    State('ts-stadium', 'value'),
    State('ts-site', 'value'),
    State('ts-team', 'value'),
    prevent_initial_call=True,
)
def render_team_stats_download(
    job, intent, league, season_id, game_type, period,
    opponent=OPPONENT_ALL, stadium=STADIUM_ALL, site=SITE_ALL, team=TEAM_ALL,
):
    if not isinstance(job, dict) or not isinstance(intent, dict):
        raise PreventUpdate
    if job.get('nonce') != intent.get('nonce'):
        raise PreventUpdate
    league = job.get('league') or league or 'PLG'
    if job.get('season') is not None:
        season_id = job.get('season')
    requested_type = job.get('game_type') if isinstance(job, dict) else game_type
    load_opponent, load_stadium, load_site, load_team = opponent, stadium, site, team
    if job.get('phase') == 'cards':
        load_opponent = job.get('opponent', opponent)
        load_stadium = job.get('stadium', stadium)
        load_site = job.get('site', site)
        load_team = job.get('team', team)
    payload = _load(
        league, season_id, requested_type, 'all', 'type',
        load_opponent, load_stadium, load_site, load_team,
    )
    return _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    )


def _season_view(league, season_id, game_type, period, opponent, stadium, site, team):
    return {
        'league': league,
        'season_id': season_id,
        'game_type': game_type,
        'period': period or 'all',
        'opponent': OPPONENT_ALL if opponent is None else opponent,
        'stadium': STADIUM_ALL if stadium is None else stadium,
        'site': SITE_ALL if site is None else site,
        'team': TEAM_ALL if team is None else team,
    }


def _same_watched_view(left, right):
    keys = (
        'league', 'season_id', 'game_type', 'period',
        'opponent', 'stadium', 'site', 'team',
    )
    return all(
        str((left or {}).get(key) or '') == str((right or {}).get(key) or '')
        for key in keys
    )


@callback(
    *_view_outputs(),
    Output('ts-seen', 'data'),
    Input('ts-interval', 'n_intervals'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-period', 'value'),
    State('ts-opponent', 'value'),
    State('ts-stadium', 'value'),
    State('ts-site', 'value'),
    State('ts-team', 'value'),
    State('ts-seen', 'data'),
    prevent_initial_call='initial_duplicate',
)
def read_team_stats_drawer(
    n, league, season_id, game_type, period, opponent, stadium, site, team, seen,
):
    """Note the season watch and paint a payload the publisher already built."""
    hold = (no_update,) * (len(_view_outputs()) + 1)
    org = organization_for_league(str(league or '').strip().upper())
    if org is None or not season_id:
        return hold
    view = _season_view(
        league, season_id, game_type, period, opponent, stadium, site, team,
    )
    note_season(org, season_id, view)
    snap = peek_season(org, season_id)
    generation = int((snap or {}).get('generation') or 0)
    if snap is None or generation == int(seen or 0):
        return hold
    if not _same_watched_view(snap.get('view'), view):
        return hold
    return _paint(
        snap.get('payload') or {},
        league, season_id, game_type, period, opponent, stadium, site, team,
    ) + (generation,)


@callback(
    Output('ts-show-opp', 'checked'),
    Output('ts-show-opp', 'disabled'),
    Output('ts-show-opp-memory', 'data'),
    Input('ts-team', 'value'),
    State('ts-show-opp', 'checked'),
    State('ts-show-opp', 'disabled'),
    State('ts-show-opp-memory', 'data'),
    prevent_initial_call=True,
)
def lock_show_opp(team, checked, disabled, memory):
    """A single team forces Show Opp on and restores the All Teams choice."""
    single = bool(team) and team != TEAM_ALL
    if single:
        if disabled:
            return no_update, no_update, no_update
        return True, True, bool(checked)
    restored = False if memory is None else bool(memory)
    if bool(checked) == restored and not disabled:
        return no_update, no_update, no_update
    return restored, False, no_update


def _rotation_caption(aggregate):
    parts = ['{0} games'.format(int(aggregate.get('n') or 0))]
    seen = set()
    for column, sample in zip(aggregate.get('columns') or [], aggregate.get('counts') or []):
        period = column.get('period')
        if period in (1, 2, 3, 4) or period in seen or column.get('minute') != 0:
            continue
        seen.add(period)
        parts.append('{0} {1}'.format(period_label(period), sample))
    return ' · '.join(parts)


def _rotation_chart(figure, aggregate):
    height = int(getattr(figure.layout, 'height', None) or 520)
    return dmc.Paper(
        [
            dmc.Text(_rotation_caption(aggregate), size='sm', c='dimmed', mb=8),
            dcc.Graph(
                id='ts-rotation-graph',
                figure=figure,
                config={
                    'displayModeBar': False,
                    'responsive': True,
                    'scrollZoom': False,
                    'doubleClick': False,
                },
                style={'width': '100%', 'height': '{0}px'.format(height)},
            ),
        ],
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def _season_on_menu(league, season):
    """A season id from another league becomes that league's first season."""
    options = selectable_seasons(league) if league else []
    ids = [value for _label, value in options]
    if season in ids:
        return season
    if ids:
        return ids[0]
    return season


def _scope_pending(intent, applied):
    """True while a league, season, or game-type click has not painted yet."""
    if not isinstance(intent, dict):
        return False
    applied = applied if isinstance(applied, dict) else {}
    league = intent.get('league')
    if league and league != applied.get('league'):
        return True
    season = intent.get('season')
    if season is not None and _season_on_menu(league or applied.get('league'), season) != applied.get('season'):
        return True
    game_type = intent.get('game_type')
    if game_type and game_type != applied.get('game_type'):
        return True
    return False


@callback(
    Output('ts-rotation', 'children'),
    Input('ts-tabs', 'value'),
    Input('ts-applied', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-intent', 'data'),
    prevent_initial_call=True,
)
def render_team_rotation(
    tab, applied, team, opponent, stadium, site, league, season_id, game_type,
    intent=None,
):
    if tab != 'tab-rotation':
        raise PreventUpdate
    applied = applied if isinstance(applied, dict) else {}
    if _scope_pending(intent, applied):
        return loading_skeleton('chart')
    if applied.get('ok') is False:
        return error_alert(ERROR_GAME)
    league = applied.get('league') or league or 'PLG'
    if applied.get('season') is not None:
        season_id = applied.get('season')
    if applied.get('game_type') is not None:
        game_type = applied.get('game_type')
    if not team or team == TEAM_ALL:
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    try:
        source = rotation_games(
            league, season_id, game_type, opponent, stadium, site, team,
        )
    except Exception:
        log_unexpected.exception('team rotation page load failed')
        return error_alert(ERROR_GAME)
    if not source.get('ok'):
        return error_alert(source.get('message') or ERROR_GAME)
    if source.get('select_team'):
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    if source.get('empty') or not source.get('games'):
        return empty_state(EMPTY_TEAM_STATS, EMPTY_TEAM_STATS_NEXT)
    try:
        aggregate = season_aggregate(source)
    except Exception:
        log_unexpected.exception('team rotation aggregate failed')
        return error_alert(ERROR_GAME)
    if not aggregate.get('n') or not aggregate.get('players'):
        return empty_state(ROTATION_EMPTY, EMPTY_TEAM_STATS_NEXT)
    names = source.get('id_table') or {}
    opponent_id = aggregate.get('opponent')
    opponent_name = display_name(names, opponent_id) if opponent_id else None
    figure = build_team_rotation_figure(
        aggregate, display_name(names, source.get('team')), opponent_name,
    )
    return _rotation_chart(figure, aggregate)


@callback(
    Output('ts-shot-body', 'children'),
    Input('ts-tabs', 'value'),
    Input('ts-applied', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    Input('ts-period', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-intent', 'data'),
    prevent_initial_call=True,
)
def render_team_shot_chart(
    tab, applied, team, opponent, stadium, site, period, league, season_id, game_type,
    intent=None,
):
    if tab != 'tab-shot-chart':
        raise PreventUpdate
    applied = applied if isinstance(applied, dict) else {}
    if _scope_pending(intent, applied):
        return shot_chart_skeleton()
    if applied.get('ok') is False:
        return error_alert(ERROR_GAME)
    league = applied.get('league') or league or 'PLG'
    if applied.get('season') is not None:
        season_id = applied.get('season')
    if applied.get('game_type') is not None:
        game_type = applied.get('game_type')
    if not team or team == TEAM_ALL:
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    try:
        source = rotation_games(
            league, season_id, game_type, opponent, stadium, site, team,
        )
    except Exception:
        log_unexpected.exception('team shot chart page load failed')
        return error_alert(ERROR_GAME)
    if not source.get('ok'):
        return error_alert(source.get('message') or ERROR_GAME)
    if source.get('select_team'):
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    if source.get('empty') or not source.get('games'):
        return empty_state(EMPTY_TEAM_STATS, EMPTY_TEAM_STATS_NEXT)
    names = source.get('id_table') or {}
    team_zones, opp_zones = season_zones(source.get('games'), source.get('team') or team, period or 'all')
    return _shot_courts(
        display_name(names, source.get('team') or team),
        team_zones,
        _opp_chart_name(source.get('opponent'), names),
        opp_zones,
    )


def _open_team_source(
    tab, expected, applied, team, opponent, stadium, site,
    league, season_id, game_type, intent, failure,
):
    """Notice for a hidden or unready tab, or the filtered game source."""
    if tab != expected:
        raise PreventUpdate
    applied = applied if isinstance(applied, dict) else {}
    if _scope_pending(intent, applied):
        return loading_skeleton('table')
    if applied.get('ok') is False:
        return error_alert(ERROR_GAME)
    league = applied.get('league') or league or 'PLG'
    if applied.get('season') is not None:
        season_id = applied.get('season')
    if applied.get('game_type') is not None:
        game_type = applied.get('game_type')
    if not team or team == TEAM_ALL:
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    try:
        source = rotation_games(
            league, season_id, game_type, opponent, stadium, site, team,
        )
    except Exception:
        log_unexpected.exception(failure)
        return error_alert(ERROR_GAME)
    if not source.get('ok'):
        return error_alert(source.get('message') or ERROR_GAME)
    if source.get('select_team'):
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    if source.get('empty') or not source.get('games'):
        return empty_state(EMPTY_TEAM_STATS, EMPTY_TEAM_STATS_NEXT)
    return source


@callback(
    Output('ts-lineup-body', 'children'),
    Input('ts-tabs', 'value'),
    Input('ts-applied', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    Input('ts-lineup-size', 'value'),
    State('ts-lineup-show-opp', 'checked'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-intent', 'data'),
    prevent_initial_call=True,
)
def render_team_lineup(
    tab, applied, team, opponent, stadium, site, size, show_opp,
    league, season_id, game_type, intent=None,
):
    source = _open_team_source(
        tab, 'tab-lineup', applied, team, opponent, stadium, site,
        league, season_id, game_type, intent, 'team lineup page load failed',
    )
    if not isinstance(source, dict):
        return source
    try:
        records = season_lineup_records(source, size)
    except Exception:
        log_unexpected.exception('team lineup aggregate failed')
        return error_alert(ERROR_GAME)
    if not records:
        return empty_state(EMPTY_LINEUPS, EMPTY_TEAM_STATS_NEXT)
    return team_lineup_grid(records, size, show_opp)


@callback(
    Output('ts-matchups-body', 'children'),
    Input('ts-tabs', 'value'),
    Input('ts-applied', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-intent', 'data'),
    prevent_initial_call=True,
)
def render_team_matchups(
    tab, applied, team, opponent, stadium, site,
    league, season_id, game_type, intent=None,
):
    source = _open_team_source(
        tab, 'tab-matchups', applied, team, opponent, stadium, site,
        league, season_id, game_type, intent, 'team matchups page load failed',
    )
    if not isinstance(source, dict):
        return source
    try:
        records = season_matchup_records(source)
    except Exception:
        log_unexpected.exception('team matchups aggregate failed')
        return error_alert(ERROR_GAME)
    if not records:
        return empty_state(EMPTY_MATCHUPS, EMPTY_TEAM_STATS_NEXT)
    return team_matchup_grid(records)
