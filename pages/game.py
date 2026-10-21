import datetime
import io
import json
import os

from dash import ALL, ctx, dcc, html, Input, Output, State, callback, register_page, clientside_callback, no_update
import dash_mantine_components as dmc
import dash_ag_grid as dag
import pandas as pd

from synergy_inbounder.communicator import SynergyAuthError
from synergy_inbounder.live_clock import clock_from_pbp_store
from synergy_inbounder.names import display_name
from synergy_inbounder.settings import organization_for_league, season_ids_for_organization
from synergy_inbounder.parser import Parser
from synergy_inbounder.runtime_cache import (
    LIVE_CADENCE_SECONDS,
    get_cached_game_status,
    get_cached_report,
    report_refresh_state,
    warmup_game_report,
)
from synergy_inbounder.game_status import (
    is_finished_status,
    is_live_play_status,
    status_bucket,
)
from synergy_reporter.report_components import (
    apply_page_cmd,
    lineup_tables_for_size,
    read_split_frame,
    render_report_workspace,
)
from synergy_reporter.report_layout import (
    default_layout,
    report_tab_is_visible,
)
from synergy_reporter.rotation import (
    apply_camera_relayout,
    build_rotation_figure,
    format_run_label,
    live_playhead_t,
    report_rotation_figure,
)
from synergy_reporter.matchups import matchup_grid_records
from synergy_reporter.team_order import (
    order_named_items,
    order_team_frame,
    section_dot,
    side_names,
    team_stripe,
)
from synergy_reporter.shot_chart import (
    court_data_uri,
    court_zones,
    period_chips as shot_period_chips,
    player_options,
    report_shot_chart_payload,
)
from ui_kit import (
    EMPTY_GAME,
    EMPTY_GAME_NEXT,
    EMPTY_MATCHUPS,
    ERROR_GAME,
    REFRESH_DELAYED,
    empty_state,
    error_alert,
    filter_control,
    game_banner,
    icon,
    loading_skeleton,
)

register_page(
    __name__,
    name='Splashboard TFB | Game',
    top_nav=True,
    path_template='/game/<league>/<game_id>'
)

ROTATION_GRAPH_CONFIG = {
    'displayModeBar': False,
    'responsive': True,
    'scrollZoom': False,
    'doubleClick': False,
}


def _bs_scroll_card(scroll_id, title=None):
    scrolled = dmc.Box(id=scroll_id, className='braves-table-scroll')
    children = [scrolled]
    if title:
        children.insert(0, dmc.Text(
            title.upper(),
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
                        'cellClassRules': {'ag-sorted-col-bg': 'params.column.isSortActive()'},
                        'cellDataType': False,
                    },
                    dashGridOptions={
                        'domLayout': 'autoHeight',
                        'suppressHorizontalScroll': False,
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
                _bs_player_block(0, '#94a3b8'),
                _bs_player_block(1, '#00b4d8'),
            ],
            id='bs-detail-body',
            style={'display': 'none'},
        ),
        id='bs-detail',
    )
    body = html.Div(id='pane-bs', children=[matrix, bar, detail])
    return html.Div(body, id='wrap-bs')


def _pane(wrap_id, pane_id, kind, hidden=False):
    body = html.Div(id=pane_id, children=loading_skeleton(kind))
    style = {'display': 'none'} if hidden else {}
    if os.environ.get('SPLASHBOARD_E2E'):
        return html.Div(body, id=wrap_id, style=style)
    return html.Div(
        dcc.Loading(custom_spinner=loading_skeleton(kind), children=body),
        id=wrap_id,
        style=style,
    )


def _rotation_controls():
    return dmc.Group(
        [
            dmc.Group(
                [
                    dmc.Button(
                        'Live',
                        id='rotation-live',
                        size='compact-xs',
                        variant='filled',
                        color='blue',
                        radius='sm',
                        style={'display': 'none'},
                    ),
                    dmc.SegmentedControl(
                        id='rotation-period',
                        data=[{'label': 'All', 'value': 'all'}],
                        value='all',
                        radius='md',
                        size='xs',
                    ),
                ],
                gap='sm',
                align='center',
                wrap='wrap',
            ),
            dmc.Switch(
                id='rotation-show-dnp',
                label='Show DNP',
                checked=False,
                size='sm',
                color='gray',
            ),
        ],
        justify='space-between',
        align='center',
        mb='sm',
        wrap='wrap',
        gap='sm',
    )


def _rotation_graph_paper():
    return dmc.Paper(
        dcc.Graph(
            id='rotation-graph',
            figure={},
            config=ROTATION_GRAPH_CONFIG,
            style={'width': '100%', 'height': '520px'},
        ),
        id='rotation-graph-paper',
        withBorder=True,
        radius='md',
        shadow='xs',
        className='braves-card-wrapper',
        style={'overflow': 'hidden', 'display': 'none'},
    )


def _rotation_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    pane = html.Div(id='pane-rotation', children=loading_skeleton('chart'))
    if os.environ.get('SPLASHBOARD_E2E'):
        body = pane
    else:
        body = dcc.Loading(custom_spinner=loading_skeleton('chart'), children=pane)
    return html.Div(
        [
            html.Div(id='rotation-last-update', children=_last_update_span()),
            _rotation_controls(),
            body,
            _rotation_graph_paper(),
        ],
        id='wrap-rotation',
        style=style,
    )


def _shot_chart_court(side):
    return dmc.Stack(
        [
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
                style={'width': '100%', 'maxWidth': '380px'},
            ),
        ],
        gap='xs',
        align='center',
        style={'width': '100%', 'maxWidth': '380px', 'marginInline': 'auto'},
    )


def _shot_chart_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    pane = html.Div(id='pane-shot-chart', children=loading_skeleton('chart'))
    if not os.environ.get('SPLASHBOARD_E2E'):
        pane = dcc.Loading(custom_spinner=loading_skeleton('chart'), children=pane)
    return html.Div(
        [
            html.Div(id='shot-chart-last-update', children=_last_update_span()),
            dmc.Paper(
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
                id='shot-chart-card',
                withBorder=True,
                radius='md',
                shadow='xs',
                p='md',
                className='braves-card-wrapper',
                style={'width': '100%', 'maxWidth': '808px', 'marginInline': 'auto'},
            ),
        ],
        id='wrap-shot-chart',
        style=style,
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


def layout(game_id=None, league='plg'):
    return html.Div([
        html.Div([
            html.Span(id='game_league', children=league, hidden=True),
            html.Span(id='game_id', children=game_id, hidden=True),
        ]),
        
        # Game Info Banner Card (visible across all tabs)
        html.Div(id='game-info-banner-wrap'),

        dmc.Tabs(
            [
                dmc.TabsList(
                    [
                        dmc.TabsTab("Box Score", value="tab-bs", leftSection=icon("tabler:table", width=14)),
                        dmc.TabsTab("Rotation", value="tab-rotation", leftSection=icon("tabler:chart-bar", width=14)),
                        dmc.TabsTab("Shot Chart", value="tab-shot-chart", leftSection=icon("tabler:ball-basketball", width=14)),
                        dmc.TabsTab("Lineup Stats", value="tab-lineup", leftSection=icon("tabler:users", width=14)),
                        dmc.TabsTab("Matchups", value="tab-matchups", leftSection=icon("tabler:users-group", width=14)),
                        dmc.TabsTab("Play-By-Play", value="tab-pbp", leftSection=icon("tabler:list-numbers", width=14)),
                        dmc.TabsTab(
                            "Report",
                            value="tab-report",
                            id="report-tab",
                            leftSection=icon("tabler:file-text", width=14),
                            style={"display": "none"},
                        ),
                    ],
                )
            ],
            id="tabs",
            value="tab-bs",
            variant="default",
            className="braves-clean-tabs",
            style={
                "margin": "0 0 16px 0",
                "padding": "0",
                "borderBottom": "none",
            }
        ),
        
        _box_score_wrap(),
        _rotation_wrap(hidden=True),
        _shot_chart_wrap(hidden=True),
        _pane('wrap-pbp', 'pane-pbp', 'table', hidden=True),
        _lineup_wrap(hidden=True),
        _matchup_wrap(hidden=True),
        _pane('wrap-report', 'pane-report', 'table', hidden=True),
        html.Div(id='pbp_table', style={'display': 'block'}),
        
        # Background Stores & Intervals
        dcc.Interval(
            id='interval-component',
            interval=LIVE_CADENCE_SECONDS * 1000,
            n_intervals=0
        ),
        dcc.Store(id='bs_store'),
        dcc.Store(id='bs-period', data='all'),
        dcc.Store(id='bs-player-columns'),
        dcc.Store(id='bs-view-reset'),
        dcc.Store(id='pbp_store'),
        dcc.Store(id='lineup_store'),
        dcc.Store(id='lineup-show-opp-sync'),
        dcc.Store(id='matchup_store'),
        dcc.Store(id='rotation_store'),
        dcc.Store(id='rotation-click-t'),
        html.Button(id='rotation-click-fire', n_clicks=0, style={'display': 'none'}),
        dcc.Store(id='rotation_view_store', data={
            'period': 'all',
            't': None,
            'x0': None,
            'x1': None,
            'show_dnp': False,
            'slice_width': None,
            'axis_rev': 0,
            'follow_live': True,
            'saw_live': False,
            'finished_reset': False,
        }),
        dcc.Store(id='match_info_store'),
        dcc.Store(id='report-pane-ready', data=''),
        
        # Dummy grid to force Dash to load AG Grid JS/CSS resources on initial load
        html.Div(dag.AgGrid(id="dummy-grid", rowData=[], columnDefs=[]), style={'display': 'none'})
    ])



def _organization(league):
    return organization_for_league(league)


def _triggered_id():
    try:
        return ctx.triggered_id
    except Exception:
        return None


def _is_game_load(n_intervals, triggered):
    """A load is a game or league change, or the callback before the interval ticks."""
    if triggered in ('game_id', 'game_league'):
        return True
    return not isinstance(n_intervals, int) or n_intervals == 0


@callback(
    Output('bs_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('game_league', 'children')]
)
def update_bs_store(n, game_id, league='plg'):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store(game_id=game_id)
    try:
        report = get_cached_report(game_id, org)
    except Exception as exc:
        print(f"Error loading box score: {exc}")
        return _error_store(game_id=game_id)
    bs_dict = {
        'game_id': game_id,
        'qt_pts_df': report.get_period_team_pts_df().to_json(date_format='iso', orient='split'),
        'qt_foul_df': report.get_period_team_fouls_df().to_json(date_format='iso', orient='split'),
        'qt_tout_df': report.get_period_team_timeout_df().to_json(date_format='iso', orient='split'),
        't_adv_df': report.get_team_advance_stats_df().to_json(date_format='iso', orient='split'),
        'adv_df': report.get_team_advanced_df().to_json(date_format='iso', orient='split'),
        't_df': report.get_team_stats_df().to_json(date_format='iso', orient='split'),
        'k_df': report.get_team_key_stats_df().to_json(date_format='iso', orient='split'),
        'p_df_dict': report.get_player_stats_json_dict(),
        'p_summary_dict': report.get_player_box_score_summary_json_dict(),
        'period_chips': report.box_score_period_chips() if hasattr(report, 'box_score_period_chips') else [],
        'slices': report.box_score_slice_json() if hasattr(report, 'box_score_slice_json') else {},
    }
    return json.dumps(bs_dict)

@callback(
    Output('match_info_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('game_league', 'children')],
    State('match_info_store', 'data'),
)
def update_match_info_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store(game_id=game_id)
    try:
        row = Parser.find_game_row(org, game_id, season_ids_for_organization(org))
        if row is None:
            return json.dumps({})
        id_table = Parser.parse_id_tables(org)

        home_name = display_name(id_table, row.get('teamIdHome'))
        away_name = display_name(id_table, row.get('teamIdAway'))
        venue_name = display_name(id_table, row.get('venueId'))
        
        dt_str = str(row['startTimeLocal'])
        try:
            dt = pd.to_datetime(dt_str)
            date_display = dt.strftime('%Y-%m-%d')
            time_display = dt.strftime('%H:%M')
        except Exception:
            date_display = dt_str
            time_display = ''

        info = {
            'date': date_display,
            'time': time_display,
            'venue': venue_name,
            'home_team': home_name,
            'away_team': away_name,
            'home_team_id': None if pd.isna(row['teamIdHome']) else str(row['teamIdHome']),
            'away_team_id': None if pd.isna(row['teamIdAway']) else str(row['teamIdAway']),
            'home_score': str(row.get('teamScoreHome', '')),
            'away_score': str(row.get('teamScoreAway', '')),
            'status': str(row.get('status', '')).strip(),
            'organization_id': org,
        }
        return json.dumps(info, ensure_ascii=False)
    except SynergyAuthError as e:
        print(f"Error loading match info: {e}")
        return _error_store(game_id=game_id)
    except Exception as e:
        print(f"Error loading match info: {e}")
        kept = safe_loads(previous)
        if kept.get('status') and kept.get('_ui') != 'error':
            return previous if isinstance(previous, str) else json.dumps(kept)
        return _error_store(game_id=game_id)

@callback(
    Output('game-info-banner-wrap', 'children'),
    Input('match_info_store', 'data'),
    Input('pbp_store', 'data'),
)
def render_game_info_banner(match_info_store, pbp_store=None):
    info = safe_loads(match_info_store)
    if not info or info.get('_ui') == 'error':
        return html.Div()
    time_display = info.get('time') or ''
    if str(info.get('status') or '').strip() == 'IN_PROGRESS':
        label = clock_from_pbp_store(pbp_store)
        if label:
            time_display = label
    return game_banner(
        home_team=info.get('home_team') or 'Home',
        away_team=info.get('away_team') or 'Away',
        home_score=info.get('home_score') or '—',
        away_score=info.get('away_score') or '—',
        status=info.get('status') or '',
        date=info.get('date') or '',
        time=time_display,
        venue=info.get('venue') or '',
    )

@callback(
    Output('interval-component', 'disabled'),
    Input('match_info_store', 'data'),
)
def set_interval_disabled(match_info_store):
    info = safe_loads(match_info_store)
    if info.get('_ui') == 'error':
        return False
    return not is_live_play_status(info.get('status'))


@callback(
    Output('report-tab', 'style'),
    Output('tabs', 'value'),
    Input('match_info_store', 'data'),
    State('tabs', 'value'),
)
def toggle_report_tab(match_info_store, active_tab):
    info = safe_loads(match_info_store)
    visible = report_tab_is_visible(info.get('status'))
    style = {} if visible else {'display': 'none'}
    if (not visible) and active_tab == 'tab-report':
        return style, 'tab-bs'
    return style, no_update

@callback(
    Output('pbp_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('game_league', 'children')]
)
def update_pbp_store(n, game_id, league='plg'):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        report = get_cached_report(game_id, org)
    except Exception as exc:
        print(f"Error loading play-by-play: {exc}")
        return _error_store()
    return report.get_play_by_play_df().to_json(date_format='iso', orient='split')

@callback(
    Output('lineup_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('game_league', 'children')]
)
def update_lineup_store(n, game_id, league='plg'):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        report = get_cached_report(game_id, org)
        if (
            _is_game_load(n, _triggered_id())
            and is_finished_status(get_cached_game_status(game_id, org))
        ):
            warmup_game_report(game_id, organization_id=org)
    except Exception as exc:
        print(f"Error loading lineup: {exc}")
        return _error_store()
    return json.dumps(report.get_all_lineup_stats_json_dict(sizes=(5,)))

@callback(
    Output('matchup_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('match_info_store', 'data'),
     Input('game_league', 'children')],
)
def update_matchup_store(n, game_id, match_info_store, league='plg'):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    info = safe_loads(match_info_store)
    if not info.get('home_team_id') or not info.get('away_team_id'):
        return json.dumps({})
    try:
        report = get_cached_report(game_id, org)
        return json.dumps(report.get_matchup_payload(
            home_team_id=info.get('home_team_id'),
            away_team_id=info.get('away_team_id'),
        ))
    except Exception as exc:
        print(f"Error loading matchups: {exc}")
        return _error_store()

@callback(
    Output('rotation_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('match_info_store', 'data'),
     Input('game_league', 'children')],
)
def update_rotation_store(n, game_id, match_info_store, league='plg'):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        report = get_cached_report(game_id, org)
        info = safe_loads(match_info_store)
        return json.dumps(report.get_rotation_payload(
            home_team_id=info.get('home_team_id'),
            away_team_id=info.get('away_team_id'),
        ))
    except Exception as exc:
        print(f"Error loading rotation: {exc}")
        return _error_store()

def safe_loads(val):
    if val is None:
        return {}
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except Exception:
            return {}
        if isinstance(parsed, (dict, list)):
            return parsed
    return {}

def _error_store(message=None, game_id=None):
    payload = {
        '_ui': 'error',
        'message': message or ERROR_GAME,
    }
    if game_id is not None:
        payload['game_id'] = game_id
    return json.dumps(payload)


def _last_update_span(game_id=None, organization_id=None):
    label = None
    delayed = False
    if game_id:
        state = report_refresh_state(game_id, organization_id)
        label = state.get('label')
        delayed = bool(state.get('delayed'))
    if not label:
        when = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
        label = f'Last Update: {when}'
    line = dmc.Text(
        label,
        size="sm",
        c="dimmed",
        mb=0 if delayed else 8,
        className="no-print",
    )
    if not delayed:
        return line
    return [
        line,
        dmc.Text(
            REFRESH_DELAYED,
            size="sm",
            c="dimmed",
            mb=8,
            className="no-print",
        ),
    ]


def _empty_view():
    return empty_state(EMPTY_GAME, EMPTY_GAME_NEXT)


def _error_view(payload=None):
    data = payload if isinstance(payload, dict) else safe_loads(payload)
    return error_alert(data.get('message') or ERROR_GAME)


def _parse_numeric_stat(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s in ('nan', 'None', '—', '-'):
        return None
    # If percentage e.g. "59.1%"
    if s.endswith('%'):
        try:
            return float(s[:-1])
        except Exception:
            return None
    # If fraction e.g. "26-44" or "30-62 (48.4%)"
    if '(' in s and '%' in s:
        try:
            pct_part = s.split('(')[1].split('%')[0].strip()
            return float(pct_part)
        except Exception:
            pass
    if '-' in s and not s.startswith('-'):
        try:
            made_part = s.split('-')[0].strip()
            return float(made_part)
        except Exception:
            pass
    # If MM:SS
    if ':' in s:
        try:
            parts = s.split(':')
            return float(parts[0]) * 60 + float(parts[1])
        except Exception:
            pass
    # Standard float
    try:
        return float(s)
    except Exception:
        return None


def _stat_header(name):
    return {'AST': 'AS', 'PTS': 'PT'}.get(name, name)


_KEY_STAT_GROUPS = (
    ('Points in the Paint', (('PIPM', 'M'), ('PIPA', 'A'), ('PIP', 'PT'))),
    ('Second Chance Points', (('SCP2M', '2M'), ('SCP2A', '2A'), ('SCP3M', '3M'), ('SCP3A', '3A'), ('SCP', 'PT'))),
    ('Fast Break Points', (('FBP2M', '2M'), ('FBP2A', '2A'), ('FBP3M', '3M'), ('FBP3A', '3A'), ('FBP', 'PT'))),
    ('Points off Turnovers', (('POT2M', '2M'), ('POT2A', '2A'), ('POT3M', '3M'), ('POT3A', '3A'), ('POT', 'PT'))),
)
_KEY_STAT_LEAVES = tuple(
    column for _name, pairs in _KEY_STAT_GROUPS for column, _label in pairs
) + ('BP',)
PACE_CARD_TITLE = 'Pace & Four Factors'
ADVANCED_CARD_TITLE = 'ADVANCED'
KEY_CARD_TITLE = 'Paint / 2nd Chance / Fastbreak / Off TO / Bench'


def _dmc_table_from_df(df, is_team_summary=True, title=None, away_name=None, home_name=None):
    if df is None or df.empty:
        return dmc.Text("No data available.", c="dimmed", ta="center", fs="italic", p="sm")

    # Precalculate winning values for each column across rows (team summary tables have 2 rows: Home vs Away)
    is_timeouts_card = bool(title and 'timeout' in title.lower())
    col_winners = {}
    if is_team_summary and len(df) == 2 and not is_timeouts_card:
        is_fouls_card = bool(title and 'foul' in title.lower())
        for col in df.columns:
            if col in ('Team', 'Min'):
                continue
            val0 = _parse_numeric_stat(df.iloc[0][col])
            val1 = _parse_numeric_stat(df.iloc[1][col])
            if val0 is not None and val1 is not None and val0 != val1:
                # Lower is better for Fouls, TO, TO%, PF. 3P-R is a mix, not a result.
                if col in ('3Pr', '3P-R'):
                    continue
                if is_fouls_card or col in ('Foul', 'PF', 'TO', 'TOV', 'TO%'):
                    col_winners[col] = 0 if val0 < val1 else 1
                else:
                    col_winners[col] = 0 if val0 > val1 else 1

    has_grouped_cols = any(c in df.columns for c in ('2M', '2A', '2FG%', '3M', '3A', '3FG%'))
    has_key_stats_grouped = any(c in df.columns for c in _KEY_STAT_LEAVES)
    
    if has_grouped_cols:
        top_row = []
        sub_row = []
        for col in ('Team', 'Min'):
            if col in df.columns:
                top_row.append(dmc.TableTh(
                    col.upper(),
                    tableProps={"rowSpan": 2},
                    style={
                        "textAlign": "center",
                        "verticalAlign": "middle",
                        "padding": "6px 10px",
                        "fontSize": "12px",
                        "fontWeight": 700,
                        "color": "#0f172a",
                        "borderBottom": "1px solid #e2e8f0",
                        "backgroundColor": "#f8fafc",
                        "whiteSpace": "nowrap",
                    }
                ))

        if any(c in df.columns for c in ('2M', '2A', '2FG%')):
            top_row.append(dmc.TableTh("2PT", tableProps={"colSpan": 3}, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                dmc.TableTh("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("%", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        if any(c in df.columns for c in ('3M', '3A', '3FG%')):
            top_row.append(dmc.TableTh("3PT", tableProps={"colSpan": 3}, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                dmc.TableTh("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("%", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        if any(c in df.columns for c in ('FTM', 'FTA', 'FT%')):
            top_row.append(dmc.TableTh("FT", tableProps={"colSpan": 3}, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                dmc.TableTh("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("%", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        if any(c in df.columns for c in ('OR', 'DR', 'REB')):
            top_row.append(dmc.TableTh("REB", tableProps={"colSpan": 3}, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                dmc.TableTh("O", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("D", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("T", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        for col in ('AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS', 'eFG%', 'USG%', 'PM'):
            if col in df.columns:
                top_row.append(dmc.TableTh(
                    _stat_header(col),
                    tableProps={"rowSpan": 2},
                    style={
                        "textAlign": "center",
                        "verticalAlign": "middle",
                        "padding": "6px 8px",
                        "fontSize": "12px",
                        "fontWeight": 700,
                        "color": "#0f172a",
                        "borderBottom": "1px solid #e2e8f0",
                        "backgroundColor": "#f8fafc",
                        "whiteSpace": "nowrap",
                    }
                ))
        header = [dmc.TableTr(top_row), dmc.TableTr(sub_row)]
    elif has_key_stats_grouped:
        top_row = []
        sub_row = []
        top_style = {
            "textAlign": "center",
            "verticalAlign": "middle",
            "padding": "6px 10px",
            "fontSize": "12px",
            "fontWeight": 700,
            "color": "#0f172a",
            "borderBottom": "1px solid #e2e8f0",
            "backgroundColor": "#f8fafc",
            "whiteSpace": "nowrap",
        }
        group_style = {
            "textAlign": "center",
            "padding": "4px 8px",
            "fontSize": "12px",
            "fontWeight": 700,
            "color": "#0f172a",
            "borderBottom": "1px solid #e2e8f0",
            "backgroundColor": "#f8fafc",
        }
        sub_style = {
            "textAlign": "center",
            "padding": "4px 6px",
            "fontSize": "11px",
            "fontWeight": 700,
            "color": "#475569",
            "borderBottom": "1px solid #e2e8f0",
            "backgroundColor": "#f8fafc",
        }
        if 'Team' in df.columns:
            top_row.append(dmc.TableTh("TEAM", tableProps={"rowSpan": 2}, style=top_style))
        for name, pairs in _KEY_STAT_GROUPS:
            present = [(column, label) for column, label in pairs if column in df.columns]
            if not present:
                continue
            top_row.append(dmc.TableTh(
                name, tableProps={"colSpan": len(present)}, style=group_style,
            ))
            sub_row.extend(dmc.TableTh(label, style=sub_style) for _column, label in present)
        if 'BP' in df.columns:
            top_row.append(dmc.TableTh("BP", tableProps={"rowSpan": 2}, style=top_style))
        header = [dmc.TableTr(top_row), dmc.TableTr(sub_row)]
    elif any(c in df.columns for c in ('eFG%', 'TO%', 'ORB%', 'FT-R')):
        top_row = []
        sub_row = []
        if 'Team' in df.columns:
            top_row.append(dmc.TableTh(
                "TEAM",
                tableProps={"rowSpan": 2},
                style={
                    "textAlign": "center",
                    "verticalAlign": "middle",
                    "padding": "6px 10px",
                    "fontSize": "12px",
                    "fontWeight": 700,
                    "color": "#0f172a",
                    "borderBottom": "1px solid #e2e8f0",
                    "backgroundColor": "#f8fafc",
                    "whiteSpace": "nowrap",
                }
            ))
        if 'Pace' in df.columns:
            top_row.append(dmc.TableTh(
                "PACE",
                tableProps={"rowSpan": 2},
                style={
                    "textAlign": "center",
                    "verticalAlign": "middle",
                    "padding": "6px 10px",
                    "fontSize": "12px",
                    "fontWeight": 700,
                    "color": "#0f172a",
                    "borderBottom": "1px solid #e2e8f0",
                    "backgroundColor": "#f8fafc",
                    "whiteSpace": "nowrap",
                }
            ))
        ff_cols = [c for c in ('eFG%', 'TO%', 'ORB%', 'FT-R') if c in df.columns]
        if ff_cols:
            top_row.append(dmc.TableTh(
                "FOUR FACTORS",
                tableProps={"colSpan": len(ff_cols)},
                style={
                    "textAlign": "center",
                    "padding": "4px 8px",
                    "fontSize": "12px",
                    "fontWeight": 700,
                    "color": "#0f172a",
                    "borderBottom": "1px solid #e2e8f0",
                    "backgroundColor": "#f8fafc",
                }
            ))
            for fc in ff_cols:
                sub_row.append(dmc.TableTh(
                    fc,
                    style={
                        "textAlign": "center",
                        "padding": "4px 6px",
                        "fontSize": "11px",
                        "fontWeight": 700,
                        "color": "#475569",
                        "borderBottom": "1px solid #e2e8f0",
                        "backgroundColor": "#f8fafc",
                    }
                ))
        header = [dmc.TableTr(top_row), dmc.TableTr(sub_row)]
    elif any(c in df.columns for c in ('PPP', 'AS/TO', 'AST%', '3P-R', 'TS%')):
        labels = ['TEAM'] if 'Team' in df.columns else []
        labels.extend(col for col in ('PPP', 'AS/TO', 'AST%', '3P-R', 'TS%') if col in df.columns)
        header = [dmc.TableTr([
            dmc.TableTh(
                label,
                style={
                    "textAlign": "center",
                    "padding": "7px 10px",
                    "fontSize": "13px",
                    "fontWeight": 700,
                    "color": "#0f172a",
                    "borderBottom": "1px solid #e2e8f0",
                    "backgroundColor": "#f8fafc",
                    "whiteSpace": "nowrap",
                }
            ) for label in labels
        ])]
    else:
        header = [dmc.TableTr([
            dmc.TableTh(
                col,
                style={
                    "textAlign": "center",
                    "padding": "7px 10px",
                    "fontSize": "13px",
                    "fontWeight": 700,
                    "color": "#0f172a",
                    "borderBottom": "1px solid #e2e8f0",
                    "backgroundColor": "#f8fafc",
                    "whiteSpace": "nowrap",
                }
            ) for col in df.columns
        ])]

    rows = []
    for row_idx in range(len(df)):
        team_stripe_style = {}
        if is_team_summary and 'Team' in df.columns:
            raw_name = df.iloc[row_idx]['Team']
            team_name = '' if pd.isna(raw_name) else str(raw_name)
            stripe_color = team_stripe(team_name, away_name, home_name, row_idx)
            team_stripe_style = {"borderLeft": f"3.5px solid {stripe_color}"}

        cells = []
        for c_idx, col in enumerate(df.columns):
            val = df.iloc[row_idx][col]
            if pd.isna(val) or val is None or str(val).strip() in ('nan', 'None'):
                val_str = ""
            elif is_timeouts_card and str(val).strip() in ('0', '0.0'):
                val_str = ""
            else:
                val_str = str(val)

            # Determine bolding and color: Only winning row in column is bold blue (team name itself is regular or semi-bold)
            is_winner = col_winners.get(col) == row_idx
            text_color = "#0077b6" if is_winner else "#1e293b"
            font_weight = 700 if is_winner else 400

            cell_style = {
                "textAlign": "center",
                "padding": "7px 10px",
                "fontSize": "13px",
                "fontWeight": font_weight,
                "color": text_color,
                "whiteSpace": "nowrap",
            }
            if c_idx == 0 and team_stripe_style:
                cell_style.update(team_stripe_style)

            cells.append(dmc.TableTd(val_str, style=cell_style))

        rows.append(dmc.TableTr(
            cells,
            className="braves-clean-row",
            style={"backgroundColor": "#ffffff"}
        ))

    table = dmc.Table(
        [dmc.TableThead(header), dmc.TableTbody(rows)],
        withTableBorder=False,
        withColumnBorders=False,
        className="braves-clean-table",
        style={"width": "100%"}
    )

    scrolled = dmc.Box(table, className="braves-table-scroll")
    paper_children = [scrolled]
    if title:
        paper_children = [
            dmc.Text(title.upper(), size="xs", fw=700, c="dimmed", mb=6, style={"letterSpacing": "0.05em"}),
            scrolled,
        ]
    return dmc.Paper(
        paper_children,
        withBorder=True,
        radius="md",
        p="sm",
        shadow="xs",
        className="braves-card-wrapper",
    )


LINEUP_COL_SIZES = {
    2: (140, 150),
    3: (180, 190),
    4: (220, 230),
    5: (240, 250),
}


def _lineup_col_size(lineup_size):
    try:
        size = int(lineup_size)
    except Exception:
        size = 5
    return LINEUP_COL_SIZES.get(size, LINEUP_COL_SIZES[5])


def _stamp_designed_widths(column_defs):
    for col in column_defs:
        children = col.get('children')
        if children:
            _stamp_designed_widths(children)
        elif 'width' in col:
            col['designedWidth'] = col['width']
    return column_defs


_LINEUP_FIT_EVENTS = {
    'gridSizeChanged': ['splashboardFitLineupWidth(params)'],
    'firstDataRendered': ['splashboardFitLineupWidth(params)'],
}


def _build_stats_column_defs(columns, filterable_cols=None, lineup_size=5):
    col_set = set(columns)
    column_defs = []

    sorted_cell_rules = {"ag-sorted-col-bg": "params.column.isSortActive()"}
    is_lineup = any('lineup' in str(name).lower() for name in col_set)
    if is_lineup:
        count_min, count_w = 22, 22
        pct_min, pct_w = 42, 42
        letter_min, letter_w = 28, 30
        minute_min, minute_w = 44, 48
        plusminus_min, plusminus_w = 34, 36
        pt_min, pt_w = 36, 40
        key_min, key_w = 26, 26
        ppp_min, ppp_w = 36, 40
    else:
        count_min, count_w = 36, 38
        pct_min, pct_w = 52, 56
        letter_min, letter_w = 42, 44
        minute_min, minute_w = 50, 56
        plusminus_min, plusminus_w = 46, 48
        pt_min, pt_w = 44, 46
        key_min, key_w = 42, 44
        ppp_min, ppp_w = 48, 52

    def _num_col(field, header, min_w, width):
        return {
            "field": field,
            "headerName": header,
            "sortable": True,
            "minWidth": min_w,
            "width": width,
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        }

    # Pinned left columns: #, PLAYER/LINEUP/TEAM, S
    if '#' in col_set:
        column_defs.append({
            "field": "#",
            "headerName": "#",
            "pinned": "left",
            "sortable": True,
            "filter": False,
            "cellDataType": "text",
            "minWidth": 36,
            "width": 38,
            "cellStyle": {"textAlign": "center", "fontWeight": "600", "color": "#64748b"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
            "valueFormatter": {"function": "params.value != null ? params.value : ''"},
            "colSpan": {"function": "params.data && (params.data['#'] === 'TEAM / COACHES' || params.data['#'] === 'TOTAL') ? 3 : 1"},
        })

    first_col = next((c for c in ('Player', 'Lineup', 'Lineups', 'Team') if c in col_set), None)
    if first_col:
        is_lineup = 'lineup' in first_col.lower()
        has_filter = bool(filterable_cols and any(fc.lower() in first_col.lower() for fc in filterable_cols))
        col_def = {
            "field": first_col,
            "headerName": first_col.upper(),
            "pinned": "left",
            "sortable": True,
            "filter": has_filter,
            "cellStyle": {"textAlign": "center", "fontWeight": "700"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        }
        if is_lineup:
            min_w, width = _lineup_col_size(lineup_size)
            col_def["minWidth"] = min_w
            col_def["width"] = width
            col_def["wrapText"] = True
            col_def["autoHeight"] = True
            col_def["cellStyle"] = {
                "textAlign": "center",
                "fontWeight": "700",
                "whiteSpace": "normal",
                "lineHeight": "1.3",
            }
        else:
            col_def["minWidth"] = 95
            col_def["width"] = 95
            if first_col == 'Player':
                # tooltipField is a data key. A tooltipValueGetter string is
                # compiled as `params => expr`, and a function expression there
                # becomes the browser title instead of the full name.
                col_def["tooltipField"] = "_playerFull"
        column_defs.append(col_def)

    if 'S' in col_set:
        column_defs.append({
            "field": "S",
            "headerName": "S",
            "pinned": "left",
            "sortable": True,
            "minWidth": 34,
            "width": 36,
            "cellRenderer": "StarterCell",
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if 'Min' in col_set:
        column_defs.append({
            "field": "Min",
            "headerName": "MIN",
            "sortable": True,
            "minWidth": minute_min,
            "width": minute_w,
            "cellStyle": {
                "styleConditions": [
                    {
                        "condition": "params.value === 'DNP'",
                        "style": {"textAlign": "center", "fontWeight": "700", "color": "#94a3b8", "letterSpacing": "0.05em"}
                    }
                ],
                "default": {"textAlign": "center"}
            },
            "colSpan": {"function": "params.data && params.data['Min'] === 'DNP' ? 30 : 1"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if '+/-' in col_set:
        column_defs.append({
            "field": "+/-",
            "headerName": "+/-",
            "sortable": True,
            "minWidth": plusminus_min,
            "width": plusminus_w,
            "cellRenderer": "PlusMinusCell",
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if any(c in col_set for c in ('2M', '2A', '2FG%')):
        children = []
        if '2M' in col_set:
            children.append(_num_col("2M", "M", count_min, count_w))
        if '2A' in col_set:
            children.append(_num_col("2A", "A", count_min, count_w))
        if '2FG%' in col_set:
            children.append(_num_col("2FG%", "%", pct_min, pct_w))
        column_defs.append({
            "headerName": "2PT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('3M', '3A', '3FG%')):
        children = []
        if '3M' in col_set:
            children.append(_num_col("3M", "M", count_min, count_w))
        if '3A' in col_set:
            children.append(_num_col("3A", "A", count_min, count_w))
        if '3FG%' in col_set:
            children.append(_num_col("3FG%", "%", pct_min, pct_w))
        column_defs.append({
            "headerName": "3PT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('FTM', 'FTA', 'FT%')):
        children = []
        if 'FTM' in col_set:
            children.append(_num_col("FTM", "M", count_min, count_w))
        if 'FTA' in col_set:
            children.append(_num_col("FTA", "A", count_min, count_w))
        if 'FT%' in col_set:
            children.append(_num_col("FT%", "%", pct_min, pct_w))
        column_defs.append({
            "headerName": "FT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('OR', 'DR', 'REB')):
        children = []
        if 'OR' in col_set:
            children.append(_num_col("OR", "O", count_min, count_w))
        if 'DR' in col_set:
            children.append(_num_col("DR", "D", count_min, count_w))
        if 'REB' in col_set:
            children.append(_num_col("REB", "T", count_min, count_w))
        column_defs.append({
            "headerName": "REB",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    stat_specs = [
        ('AST', 'AS', letter_min, letter_w),
        ('TO', 'TO', letter_min, letter_w),
        ('ST', 'ST', letter_min, letter_w),
        ('BS', 'BS', letter_min, letter_w),
        ('PF', 'PF', letter_min, letter_w),
        ('FD', 'FD', letter_min, letter_w),
        ('PTS', 'PT', pt_min, pt_w),
    ]
    for col_name, hdr_name, min_w, w in stat_specs:
        if col_name in col_set:
            column_defs.append({
                "field": col_name,
                "headerName": hdr_name,
                "sortable": True,
                "minWidth": min_w,
                "width": w,
                "cellStyle": {"textAlign": "center"},
                "cellClass": "ag-cell-align-center",
                "headerClass": "ag-header-align-center",
                "cellClassRules": sorted_cell_rules,
            })

    key_fields = [name for name in ('PIP', 'SCP', 'FBP', 'POT') if name in col_set]
    if key_fields:
        column_defs.append({
            "headerName": "Key Stats",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": [
                {
                    "field": name,
                    "headerName": name,
                    "sortable": True,
                    "minWidth": key_min,
                    "width": key_w,
                    "cellStyle": {"textAlign": "center"},
                    "cellClass": "ag-cell-align-center",
                    "headerClass": "ag-header-align-center",
                    "cellClassRules": sorted_cell_rules,
                }
                for name in key_fields
            ],
        })

    stat_specs = [
        ('PPP', 'PPP', ppp_min, ppp_w),
        ('eFG%', 'eFG%', 54, 58),
        ('USG%', 'USG%', 54, 58),
        ('PM', 'PM', 56, 62),
    ]
    for col_name, hdr_name, min_w, w in stat_specs:
        if col_name in col_set:
            column_defs.append({
                "field": col_name,
                "headerName": hdr_name,
                "sortable": True,
                "minWidth": min_w,
                "width": w,
                "cellStyle": {"textAlign": "center"},
                "cellClass": "ag-cell-align-center",
                "headerClass": "ag-header-align-center",
                "cellClassRules": sorted_cell_rules,
            })

    _apply_click_sort_columns(column_defs)
    return _stamp_designed_widths(column_defs)


def _display_cell(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except TypeError:
        pass
    return value


def _lineup_visible_columns(df):
    return [
        col for col in df.columns
        if not str(col).startswith('Opp_') and not str(col).startswith('_')
    ]


def _lineup_pair_records(df):
    """One lineup JSON row becomes our row, then an Opp row on the same columns."""
    columns = _lineup_visible_columns(df)
    records = []
    for raw in df.to_dict('records'):
        own = {col: _display_cell(raw.get(col)) for col in columns}
        pair = own.get('Lineup', own.get('Lineups', ''))
        our = dict(own)
        our['_opp'] = False
        our['_pair'] = pair
        our['_own'] = dict(own)
        records.append(our)
        opp = {}
        for col in columns:
            if col in ('Min', '+/-'):
                opp[col] = ''
            elif 'lineup' in str(col).lower():
                opp[col] = pair
            else:
                opp[col] = _display_cell(raw.get('Opp_' + col, ''))
        opp['_opp'] = True
        opp['_pair'] = pair
        opp['_own'] = dict(own)
        records.append(opp)
    return records


_DESC_SORT_FIELDS = {
    '#', 'Min', '+/-',
    '2M', '2A', '2FG%', '3M', '3A', '3FG%', 'FTM', 'FTA', 'FT%',
    'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS',
    'PIP', 'SCP', 'FBP', 'POT', 'PPP', 'eFG%', 'USG%',
}
DESC_FIRST_SORT = ['desc', 'asc', None]


def _numeric_rank_js():
    # M:SS becomes seconds. A trailing % is stripped so 0.0% and .833 compare
    # as numbers. Blank stays below 0.
    return (
        "(function(raw) {"
        "return raw === '' || raw === null || raw === undefined ? null"
        " : (typeof raw === 'number' ? (raw !== raw ? null : raw)"
        " : (typeof raw === 'string' && raw.indexOf(':') >= 0"
        " ? (function(parts) {"
        "return parts && parts.length === 2 && (+parts[0]) === (+parts[0]) && (+parts[1]) === (+parts[1])"
        " ? (+parts[0]) * 60 + (+parts[1]) : null;"
        "})(raw.split(':'))"
        " : (typeof raw === 'string'"
        " ? (function(text) { return (+text) === (+text) ? +text : null; })(raw.replace('%', ''))"
        " : null)));"
        "})"
    )


def _lineup_pair_comparator(field):
    # dash-ag-grid evaluates this once with static-eval. That walker rejects
    # var/if/for, and it prewalks the body with every parameter set to null,
    # so member access and `typeof` stay behind a null check.
    # AG Grid inverts a descending column. The DNP bias flips with
    # isDescending so those rows stay last in both directions.
    field_js = json.dumps(field)
    rank = _numeric_rank_js()
    return {
        "function": (
            "(function(a, b, nodeA, nodeB, isDescending) {"
            "return (function(dnpA, dnpB) {"
            "return dnpA !== dnpB ? (dnpA ? 1 : -1) * (isDescending ? -1 : 1)"
            " : (function(av, bv) {"
            "return (function(an, bn) {"
            "return an === null && bn === null ? (av < bv ? -1 : av > bv ? 1 : 0)"
            " : an === null ? -1 : bn === null ? 1"
            " : an < bn ? -1 : an > bn ? 1 : 0;"
            "})(" + rank + "(av), " + rank + "(bv));"
            "})("
            f"nodeA && nodeA.data ? (nodeA.data._own ? nodeA.data._own[{field_js}] : nodeA.data[{field_js}]) : null,"
            f"nodeB && nodeB.data ? (nodeB.data._own ? nodeB.data._own[{field_js}] : nodeB.data[{field_js}]) : null);"
            "})("
            "nodeA && nodeA.data && nodeA.data.Min === 'DNP',"
            "nodeB && nodeB.data && nodeB.data.Min === 'DNP');"
            "})"
        )
    }


# Family, then the initial run. J.Lee sorts with K.Lee. dash-ag-grid's
# function walker rejects var/if/for and prewalks with null arguments.
_PLAYER_NAME_COMPARATOR = {
    "function": (
        "(function(a, b) {"
        "return (function(keyOf) {"
        "return (function(ka, kb) {"
        "return !ka || !kb ? 0"
        " : ka[0] < kb[0] ? -1 : ka[0] > kb[0] ? 1"
        " : ka[1] < kb[1] ? -1 : ka[1] > kb[1] ? 1 : 0;"
        "})(keyOf ? keyOf(a) : null, keyOf ? keyOf(b) : null);"
        "})(function(label) {"
        "return (function(text) {"
        "return (function(match) {"
        "return match ? [match[2].toLowerCase(), match[1].toLowerCase()]"
        " : [(text && text.toLowerCase) ? text.toLowerCase() : '', ''];"
        "})(text && text.match ? text.match(/^((?:[A-Z]\\.)+)(.+)$/) : null);"
        "})(label == null ? '' : '' + label);"
        "});"
        "})"
    ),
}

def _apply_click_sort(col):
    field = col.get('field')
    if field == 'Player':
        col['comparator'] = _PLAYER_NAME_COMPARATOR
        return
    if field not in _DESC_SORT_FIELDS:
        return
    col['sortingOrder'] = list(DESC_FIRST_SORT)
    col['comparator'] = _lineup_pair_comparator(field)


def _apply_click_sort_columns(column_defs):
    for col in column_defs:
        children = col.get('children')
        if children:
            _apply_click_sort_columns(children)
            continue
        _apply_click_sort(col)


# postSortRows is compiled as `params => expr` on every sort. Snapshot the
# comparator order first: indexOf on the live array moves while it sorts.
_LINEUP_POST_SORT = {
    "function": (
        "(function(original) {"
        "return params.nodes.sort(function(a, b) {"
        "return (function(ai, bi) {"
        "return ai < bi ? -1 : ai > bi ? 1"
        " : ((a && a.data && a.data._opp) ? 1 : 0) - ((b && b.data && b.data._opp) ? 1 : 0);"
        "})("
        "original ? original.indexOf(original.find(function(n) {"
        "return n && n.data && a && a.data && n.data._pair === a.data._pair && !n.data._opp;"
        "})) : -1,"
        "original ? original.indexOf(original.find(function(n) {"
        "return n && n.data && b && b.data && n.data._pair === b.data._pair && !n.data._opp;"
        "})) : -1);"
        "});"
        "})(params && params.nodes ? params.nodes.slice() : [])"
    )
}


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


def _apply_matchup_pair_columns(column_defs):
    for col in column_defs:
        children = col.get('children')
        if children:
            _apply_matchup_pair_columns(children)
            continue
        field = col.get('field')
        if not field:
            continue
        col['comparator'] = _lineup_pair_comparator(field)
        if field != 'Lineup':
            continue
        rules = dict(col.get('cellClassRules') or {})
        rules['ag-cell-align-right'] = 'params.data && params.data._opp'
        rules['ag-cell-align-left'] = '!(params.data && params.data._opp)'
        col['cellClassRules'] = rules
        col.pop('cellClass', None)
        col['filterValueGetter'] = {
            'function': "params.data && params.data._filter ? params.data._filter : ''",
        }
        col['cellStyle'] = {
            'styleConditions': [
                {
                    'condition': 'params.data && params.data._opp',
                    'style': {
                        'textAlign': 'right',
                        'fontWeight': '400',
                        'color': '#0f172a',
                        'whiteSpace': 'normal',
                        'lineHeight': '1.3',
                    },
                }
            ],
            'defaultStyle': {
                'textAlign': 'left',
                'fontWeight': '700',
                'whiteSpace': 'normal',
                'lineHeight': '1.3',
            },
        }


def _matchup_column_defs():
    columns = [
        'Lineup', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
        'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS',
        'PF', 'FD', 'PTS', 'PIP', 'SCP', 'FBP', 'POT', 'PPP',
    ]
    column_defs = _build_stats_column_defs(
        columns,
        filterable_cols=['Lineup'],
        lineup_size=5,
    )
    _apply_matchup_pair_columns(column_defs)
    return column_defs


def _matchup_grid():
    return dag.AgGrid(
        id='matchup-grid',
        rowData=[],
        columnDefs=_matchup_column_defs(),
        defaultColDef={
            'sortable': True,
            'filter': False,
            'resizable': True,
            'cellDataType': False,
        },
        dashGridOptions={
            'domLayout': 'autoHeight',
            'suppressHorizontalScroll': False,
            'postSortRows': _LINEUP_POST_SORT,
        },
        eventListeners=_LINEUP_FIT_EVENTS,
        className='ag-theme-alpine braves-clean-ag-grid braves-lineup-grid',
        style={'width': '100%'},
        getRowId="params.data._pair + (params.data._opp ? ':other' : ':view')",
        getRowStyle={
            'styleConditions': [
                {
                    'condition': 'params.data && params.data._opp',
                    'style': {'backgroundColor': '#f1f5f9'},
                }
            ],
            'defaultStyle': {'backgroundColor': '#ffffff'},
        },
        rowClassRules={'lineup-opp-row': 'params.data && params.data._opp'},
    )


def _apply_lineup_pair_columns(column_defs):
    for col in column_defs:
        children = col.get("children")
        if children:
            _apply_lineup_pair_columns(children)
            continue
        field = col.get("field")
        if not field:
            continue
        col["comparator"] = _lineup_pair_comparator(field)
        if "lineup" not in str(field).lower():
            continue
        rules = dict(col.get("cellClassRules") or {})
        rules["ag-cell-align-right"] = "params.data && params.data._opp"
        rules["ag-cell-align-center"] = "!(params.data && params.data._opp)"
        col["cellClassRules"] = rules
        col.pop("cellClass", None)
        field_js = json.dumps(field)
        col["valueGetter"] = {
            "function": (
                "params.data && params.data._opp ? 'Opp' : "
                f"(params.data ? params.data[{field_js}] : '')"
            ),
        }
        col["filterValueGetter"] = {
            "function": f"params.data ? params.data[{field_js}] : ''",
        }
        col["cellStyle"] = {
            "styleConditions": [
                {
                    "condition": "params.data && params.data._opp",
                    "style": {
                        "textAlign": "right",
                        "fontWeight": "400",
                        "color": "#0f172a",
                        "whiteSpace": "normal",
                        "lineHeight": "1.3",
                    },
                }
            ],
            "defaultStyle": {
                "textAlign": "center",
                "fontWeight": "700",
                "whiteSpace": "normal",
                "lineHeight": "1.3",
            },
        }


def _ag_grid_from_df(df, page_size=None, filterable_cols=None, pinned_bottom_data=None, lineup_size=5, row_records=None, pair_rows=False, show_opp=False, grid_id=None):
    if df is None or df.empty:
        return dmc.Text("No data available.", c="dimmed", ta="center", fs="italic", p="sm")
    
    sorted_cell_rules = {"ag-sorted-col-bg": "params.column.isSortActive()"}

    # If standard basketball stats table (2PT/3PT/FT breakdown present), use multi-level grouped columns
    if any(c in df.columns for c in ('2M', '2A', '2FG%', '3M', '3A', '3FG%')):
        column_defs = _build_stats_column_defs(
            df.columns,
            filterable_cols=filterable_cols,
            lineup_size=lineup_size,
        )
    else:
        column_defs = []
        for c_idx, c in enumerate(df.columns):
            align = "center"

            cell_style = {"textAlign": align}
            if c in ('Player', 'Lineup', 'Lineups') or 'lineup' in c.lower():
                cell_style["fontWeight"] = "700"

            has_filter = bool(filterable_cols and (c in filterable_cols or any(fc.lower() in c.lower() for fc in filterable_cols)))

            col_width_props = {}
            if c in ('Lineup', 'Lineups') or 'lineup' in c.lower():
                min_w, width = _lineup_col_size(lineup_size)
                col_width_props["minWidth"] = min_w
                col_width_props["width"] = width
            elif c in ('Player', 'Team'):
                col_width_props["minWidth"] = 90
                col_width_props["width"] = 95
            elif c == 'Min':
                col_width_props["minWidth"] = 50
                col_width_props["width"] = 55
            elif c in ('PM', '+/-'):
                col_width_props["minWidth"] = 42
                col_width_props["width"] = 45
            else:
                col_width_props["minWidth"] = 38
                col_width_props["width"] = 42

            col_def = {
                "field": c,
                "headerName": c,
                "sortable": True,
                "filter": has_filter,
                "cellStyle": cell_style,
                "cellClass": f"ag-cell-align-{align}",
                "headerClass": f"ag-header-align-{align}",
                "cellClassRules": sorted_cell_rules,
                **col_width_props
            }
            if c in ('Lineup', 'Lineups') or 'lineup' in c.lower():
                col_def['wrapText'] = True
                col_def['autoHeight'] = True
                col_def['cellStyle'] = {
                    **cell_style,
                    'whiteSpace': 'normal',
                    'lineHeight': '1.3',
                }
            _apply_click_sort(col_def)
            column_defs.append(col_def)
        _stamp_designed_widths(column_defs)

    dash_options = {
        "domLayout": "autoHeight",
        "suppressHorizontalScroll": False,
    }
    lineup_events = None
    if any('lineup' in str(col).lower() for col in df.columns):
        lineup_events = _LINEUP_FIT_EVENTS
    if page_size:
        dash_options["pagination"] = True
        dash_options["paginationPageSize"] = page_size
    if pinned_bottom_data:
        dash_options["pinnedBottomRowData"] = pinned_bottom_data
    pair_props = {}
    if pair_rows:
        _apply_lineup_pair_columns(column_defs)
        dash_options["postSortRows"] = _LINEUP_POST_SORT
        dash_options["isExternalFilterPresent"] = {
            "function": "false" if show_opp else "true",
        }
        dash_options["doesExternalFilterPass"] = {
            "function": "!(params && params.data && params.data._opp)",
        }
        pair_props = {
            "id": grid_id,
            "getRowId": "params.data._pair + (params.data._opp ? ':opp' : ':us')",
            "getRowStyle": {
                "styleConditions": [
                    {
                        "condition": "params.data && params.data._opp",
                        "style": {"backgroundColor": "#f1f5f9"},
                    }
                ],
                "defaultStyle": {"backgroundColor": "#ffffff"},
            },
            "rowClassRules": {"lineup-opp-row": "params.data && params.data._opp"},
        }

    grid_class = "ag-theme-alpine braves-clean-ag-grid"
    if any('lineup' in str(c).lower() for c in df.columns):
        grid_class += " braves-lineup-grid"
    if lineup_events:
        pair_props = dict(pair_props)
        pair_props['eventListeners'] = lineup_events
    return dmc.Paper(
        dag.AgGrid(
            rowData=row_records if row_records is not None else df.to_dict('records'),
            columnDefs=column_defs,
            defaultColDef={"sortable": True, "filter": False, "resizable": True, "cellClassRules": sorted_cell_rules, "cellDataType": False},
            dashGridOptions=dash_options,
            className=grid_class,
            style={'width': '100%'},
            **pair_props,
        ),
        withBorder=True,
        radius="md",
        shadow="xs",
        mb="md",
        className="braves-grid-wrap",
        style={"overflowX": "auto"},
    )


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
        except Exception:
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
        style={"marginBottom": "12px"}
    )
    row2 = dmc.SimpleGrid(
        cols={"base": 1, "lg": 2},
        spacing="12px",
        children=[
            _dmc_table_from_df(frames['t_adv'], is_team_summary=True, title=PACE_CARD_TITLE, away_name=away_name, home_name=home_name),
            _dmc_table_from_df(frames['adv'], is_team_summary=True, title=ADVANCED_CARD_TITLE, away_name=away_name, home_name=home_name),
        ],
        style={"marginBottom": "12px"}
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
        patch['last_update'] = _last_update_span(game_id, (info or {}).get('organization_id'))
        patch['score'] = _table_children(frames['qt_pts'], 'Score', away_name, home_name)
        patch['fouls'] = _table_children(frames['qt_foul'], 'Fouls', away_name, home_name)
        patch['tout'] = _table_children(frames['qt_tout'], 'Timeouts', away_name, home_name)
    return tuple(patch[key] for key in BS_SYNC_KEYS)


DEFAULT_ROTATION_VIEW = {
    'period': 'all',
    't': None,
    'x0': None,
    'x1': None,
    'show_dnp': False,
    'slice_width': None,
    'axis_rev': 0,
    'follow_live': True,
    'saw_live': False,
    'finished_reset': False,
}


def _rotation_view(view_store):
    data = view_store if isinstance(view_store, dict) else safe_loads(view_store)
    merged = dict(DEFAULT_ROTATION_VIEW)
    if isinstance(data, dict):
        for key in DEFAULT_ROTATION_VIEW:
            if key in data:
                merged[key] = data[key]
    return merged


def resolve_bs_period(triggered_id, control_value):
    if triggered_id == 'game_id':
        return 'all'
    if control_value in (None, ''):
        return 'all'
    return str(control_value)


def _pbp_frame(pbp_store):
    if pbp_store is None:
        return 'loading', None
    payload = pbp_store if isinstance(pbp_store, dict) else safe_loads(pbp_store)
    if not isinstance(payload, dict) or not payload:
        return 'empty', None
    if payload.get('_ui') == 'error':
        return 'error', None
    if 'columns' not in payload or 'data' not in payload:
        return 'empty', None
    raw = pbp_store if isinstance(pbp_store, str) else json.dumps(payload)
    try:
        frame = pd.read_json(io.StringIO(raw), orient='split')
    except (ValueError, TypeError):
        return 'empty', None
    if frame.empty:
        return 'empty', None
    return 'ready', frame


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


def shot_chart_panel(pbp_store, match_info, period, away_player, home_player):
    status, frame = _pbp_frame(pbp_store)
    info = safe_loads(match_info)
    if status == 'loading':
        return {'status': 'loading'}
    if status == 'error':
        return {'status': 'error', 'message': ERROR_GAME}
    if status != 'ready':
        return {'status': 'empty'}
    return {
        'status': 'ready',
        'away_name': info.get('away_team') or 'Away',
        'home_name': info.get('home_team') or 'Home',
        'away_src': court_data_uri(court_zones(
            frame, info.get('away_team_id'), period=period or 'all', player_id=away_player or 'all',
        )),
        'home_src': court_data_uri(court_zones(
            frame, info.get('home_team_id'), period=period or 'all', player_id=home_player or 'all',
        )),
    }


def _court_image(src, alt):
    return html.Img(
        src=src,
        alt=alt,
        style={'width': '100%', 'maxWidth': '380px', 'height': 'auto', 'display': 'block'},
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


def _period_control_data(periods):
    data = [{'label': 'All', 'value': 'all'}]
    seen = {'all'}
    for period in periods or []:
        value = str(period.get('id'))
        if value in seen:
            continue
        seen.add(value)
        data.append({'label': period.get('label') or value, 'value': value})
    return data


def _find_period(periods, period_value):
    for period in periods or []:
        if str(period.get('id')) == str(period_value):
            return period
    return None


def _rotation_chip(label, kind, index, side):
    return dmc.Button(
        label,
        id={'type': kind, 'index': index},
        color='blue' if side == 'home' else 'gray',
        variant='light' if kind == 'rotation-run' else 'outline',
        size='compact-xs',
        radius='sm',
        px=8,
    )


def _render_run_buttons(runs, periods):
    items = []
    for index, run in enumerate(runs or []):
        items.append((run.get('start') or 0, index, run))
    if not items:
        return None
    items.sort(key=lambda item: item[0])
    buttons = [
        _rotation_chip(
            format_run_label(run, periods),
            'rotation-run',
            index,
            run.get('side'),
        )
        for _start, index, run in items
    ]
    return dmc.Group(
        buttons,
        gap=6,
        mb='sm',
        style={'flexWrap': 'wrap'},
    )


def resolve_rotation_playhead(payload, view, match_info_store=None):
    info = match_info_store if isinstance(match_info_store, dict) else safe_loads(match_info_store)
    live = is_live_play_status(info.get('status'))
    periods = (payload or {}).get('periods') or []
    if live and view.get('follow_live', True):
        return live_playhead_t(payload)
    playhead = view.get('t')
    if playhead is not None:
        return playhead
    if live:
        return live_playhead_t(payload)
    if is_finished_status(info.get('status')) and periods:
        return periods[0]['start']
    if periods:
        return periods[-1]['end']
    return None


def _rotation_figure_from_view(payload, view, match_info_store=None):
    playhead = resolve_rotation_playhead(payload, view, match_info_store)
    x_range = None
    if view.get('x0') is not None and view.get('x1') is not None:
        x_range = (view['x0'], view['x1'])
    width = (x_range[1] - x_range[0]) if x_range else None
    uirevision = f"{width if width is not None else 'all'}:{int(view.get('axis_rev') or 0)}"
    return build_rotation_figure(
        payload,
        playhead=playhead,
        x_range=x_range,
        show_dnp=bool(view.get('show_dnp')),
        uirevision=uirevision,
    )


def render_rotation_children(rotation_store, view_store=None, match_info_store=None):
    payload = safe_loads(rotation_store)
    if payload.get('_ui') == 'error':
        return [_error_view(payload)]
    if not payload or not payload.get('teams'):
        return [_empty_view()]
    runs = payload.get('runs') or []
    periods = payload.get('periods') or []
    runs_row = _render_run_buttons(runs, periods)
    if runs_row is not None:
        return [runs_row]
    return []


def apply_rotation_view_event(
    triggered_id,
    period,
    show_dnp,
    run_clicks,
    click_t,
    rotation_store,
    game_id,
    view_store,
    match_info_store,
    relayout_data=None,
):
    view = _rotation_view(view_store)
    if triggered_id == 'game_id':
        return dict(DEFAULT_ROTATION_VIEW)
    payload = safe_loads(rotation_store)
    periods = payload.get('periods') or []
    runs = payload.get('runs') or []
    if triggered_id == 'rotation-graph.relayoutData':
        updated = apply_camera_relayout(relayout_data, view, periods)
        return updated if updated is not None else no_update

    if triggered_id == 'rotation-live':
        view['follow_live'] = True
        view['t'] = live_playhead_t(payload)
        return view

    if triggered_id == 'rotation-period':
        if period == view.get('period'):
            already_all = period in (None, 'all') and view.get('x0') is None
            already_period = (
                period not in (None, 'all')
                and _find_period(periods, period)
                and view.get('x0') == _find_period(periods, period)['start']
                and view.get('x1') == _find_period(periods, period)['end']
            )
            if already_all or already_period:
                return no_update
        view['period'] = period or 'all'
        if view['period'] == 'all':
            view['x0'] = None
            view['x1'] = None
            view['slice_width'] = None
        else:
            found = _find_period(periods, view['period'])
            if found:
                view['x0'] = found['start']
                view['x1'] = found['end']
                view['slice_width'] = float(found['end'] - found['start'])
                view['t'] = found['start']
                view['follow_live'] = False
        view['axis_rev'] = int(view.get('axis_rev') or 0) + 1
        return view

    if triggered_id == 'rotation-show-dnp':
        checked = bool(show_dnp)
        if checked == bool(view.get('show_dnp')):
            return no_update
        view['show_dnp'] = checked
        return view

    if isinstance(triggered_id, dict) and triggered_id.get('type') == 'rotation-run':
        index = triggered_id.get('index')
        clicks = run_clicks or []
        if not clicks or not any(clicks):
            return no_update
        if not isinstance(index, int) or index < 0 or index >= len(runs):
            return no_update
        run = runs[index]
        view['period'] = 'all'
        view['x0'] = None
        view['x1'] = None
        view['slice_width'] = None
        view['t'] = run['start']
        view['follow_live'] = False
        view['axis_rev'] = int(view.get('axis_rev') or 0) + 1
        return view

    if triggered_id == 'rotation-click-t':
        if click_t is None:
            return no_update
        try:
            t_val = float(click_t)
        except (TypeError, ValueError):
            return no_update
        game_end = periods[-1]['end'] if periods else None
        if game_end is not None:
            t_val = min(max(0.0, t_val), float(game_end))
        view['t'] = t_val
        view['follow_live'] = False
        return view

    if triggered_id in ('rotation_store', 'match_info_store'):
        info = match_info_store if isinstance(match_info_store, dict) else safe_loads(match_info_store)
        status = info.get('status')
        if is_live_play_status(status):
            changed = False
            if not view.get('saw_live'):
                view['saw_live'] = True
                changed = True
            if view.get('follow_live', True):
                now = live_playhead_t(payload)
                if now != view.get('t'):
                    view['t'] = now
                    changed = True
            return view if changed else no_update
        if (
            is_finished_status(status)
            and view.get('saw_live')
            and not view.get('finished_reset')
        ):
            view['t'] = None
            view['follow_live'] = False
            view['period'] = 'all'
            view['x0'] = None
            view['x1'] = None
            view['slice_width'] = None
            view['finished_reset'] = True
            view['axis_rev'] = int(view.get('axis_rev') or 0) + 1
            return view
        return no_update

    return no_update


def render_pbp_children(pbp_store, game_id=None, organization_id=None):
    payload = safe_loads(pbp_store)
    if payload.get('_ui') == 'error':
        return [_error_view(payload)]
    if not payload or 'columns' not in payload:
        return [_empty_view()]
    pbp_df = pd.read_json(io.StringIO(pbp_store), orient='split')
    if pbp_df.empty:
        return [_empty_view()]
    team_name_list = pbp_df['Team'].dropna().unique() if 'Team' in pbp_df.columns else []
    col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'Team', 'Player', 'eventType', 'subType', 'success', 'scores']
    col_list.extend(team_name_list)
    col_list = [c for c in col_list if c in pbp_df.columns]
    pbp_df = pbp_df[col_list][::-1]
    column_defs = []
    for column in pbp_df.columns:
        col_def = {
            "field": column,
            "headerClass": "ag-header-align-center",
            "cellClass": "ag-cell-align-center",
            "cellStyle": {"textAlign": "center"},
        }
        if column == 'Player':
            col_def['comparator'] = _PLAYER_NAME_COMPARATOR
        column_defs.append(col_def)
    grid = dag.AgGrid(
        rowData=pbp_df.to_dict('records'),
        columnDefs=column_defs,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        columnSize="autoSize",
        className="ag-theme-alpine braves-clean-ag-grid",
        style={'width': '100%'}
    )
    return [_last_update_span(game_id, organization_id), dmc.Paper(grid, withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden"})]


def render_lineup_children(lineup_store, lineup_size=5, show_opp=False, match_info=None):
    try:
        size_int = int(lineup_size)
    except Exception:
        size_int = 5
    payload = safe_loads(lineup_store)
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


def _report_org(match_info):
    info = match_info or {}
    return info.get('organization_id')


def _report_rotation_figure_json(game_id, match_info):
    if not game_id:
        return json.dumps({'_ui': 'empty'})
    try:
        report = get_cached_report(game_id, _report_org(match_info))
        payload = report.get_rotation_payload(
            home_team_id=(match_info or {}).get('home_team_id'),
            away_team_id=(match_info or {}).get('away_team_id'),
        )
        if not isinstance(payload, dict) or payload.get('_ui') == 'error':
            return json.dumps({'_ui': 'error'})
        if not payload.get('teams'):
            return json.dumps({'_ui': 'empty'})
        return report_rotation_figure(payload).to_json()
    except Exception as exc:
        print(f"Error building report rotation: {exc}")
        return json.dumps({'_ui': 'error'})


def _report_shot_chart_json(game_id, match_info):
    if not game_id:
        return json.dumps({'_ui': 'empty'})
    info = match_info or {}
    try:
        report = get_cached_report(game_id, _report_org(info))
        payload = report_shot_chart_payload(
            report.get_play_by_play_df(),
            info.get('away_team_id'),
            info.get('home_team_id'),
            info.get('away_team') or 'Away',
            info.get('home_team') or 'Home',
        )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        print(f"Error building report shot chart: {exc}")
        return json.dumps({'_ui': 'error'})


def render_report_children(bs_store, lineup_store, match_info_store, game_id=None):
    bs_dict = safe_loads(bs_store) if bs_store else {}
    match_info = safe_loads(match_info_store) if match_info_store else {}
    layout = default_layout(match_info)
    if bs_dict.get('_ui') == 'error':
        return [_error_view(bs_dict)]
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_empty_view()]
    return [
        _last_update_span(game_id, match_info.get('organization_id')),
        render_report_workspace(
            layout,
            bs_dict,
            lineup_store,
            match_info,
            game_id,
            rotation_json=_report_rotation_figure_json(game_id, match_info),
            shot_chart_json=_report_shot_chart_json(game_id, match_info),
        ),
    ]


@callback(
    Output('bs-matrix', 'children'),
    Output('bs-detail', 'children'),
    Input('bs_store', 'data'),
    Input('tabs', 'value'),
    Input('bs-period', 'data'),
)
def update_pane_bs(bs_store, active_tab, period='all'):
    # The shell is mounted in the layout. sync_box_score patches the hosts.
    return no_update, no_update


@callback(
    Output('bs-skeleton', 'style'),
    Output('bs-matrix-body', 'style'),
    Output('bs-detail-body', 'style'),
    Output('bs-status', 'style'),
    Output('bs-status', 'children'),
    Output('bs-period-bar', 'style'),
    Output('bs-period-control', 'data'),
    Output('bs-last-update', 'children'),
    Output('bs-score-scroll', 'children'),
    Output('bs-fouls-scroll', 'children'),
    Output('bs-tout-scroll', 'children'),
    Output('bs-pace-scroll', 'children'),
    Output('bs-advanced-scroll', 'children'),
    Output('bs-key-scroll', 'children'),
    Output('bs-team-scroll', 'children'),
    Output('bs-player-title-0', 'children'),
    Output('bs-player-title-1', 'children'),
    Output('bs-player-block-0', 'style'),
    Output('bs-player-block-1', 'style'),
    Output('bs-player-grid-0', 'rowData'),
    Output('bs-player-grid-1', 'rowData'),
    Output('bs-player-grid-0', 'dashGridOptions'),
    Output('bs-player-grid-1', 'dashGridOptions'),
    Output('bs-player-grid-0', 'columnDefs'),
    Output('bs-player-grid-1', 'columnDefs'),
    Output('bs-player-columns', 'data'),
    Input('bs_store', 'data'),
    Input('bs-period', 'data'),
    Input('game_id', 'children'),
    Input('tabs', 'value'),
    Input('match_info_store', 'data'),
    State('bs-player-columns', 'data'),
)
def sync_box_score(bs_store, period, game_id, active_tab, match_info, column_state):
    return box_score_sync_values(
        bs_store, period, game_id, active_tab, column_state, ctx.triggered_id, match_info,
    )


clientside_callback(
    """
    function(gameId) {
        window.__bsScrollKeep = false;
        window.__bsScrollSaved = {};
        document.querySelectorAll(
            '#bs-matrix-body .braves-table-scroll, #bs-detail-body .braves-table-scroll, #bs-detail-body .braves-grid-wrap'
        ).forEach(function(el) {
            el.scrollLeft = 0;
            el.scrollTop = 0;
        });
        ['bs-player-grid-0', 'bs-player-grid-1'].forEach(function(id) {
            var api = null;
            try {
                api = window.dash_ag_grid && window.dash_ag_grid.getApi && window.dash_ag_grid.getApi(id);
            } catch (err) {
                api = null;
            }
            if (api && !(api.isDestroyed && api.isDestroyed()) && api.resetColumnState) {
                api.resetColumnState();
            }
            var root = document.getElementById(id);
            if (!root) {
                return;
            }
            root.querySelectorAll(
                '.ag-body-viewport, .ag-center-cols-viewport, .ag-body-horizontal-scroll-viewport'
            ).forEach(function(node) {
                node.scrollTop = 0;
                node.scrollLeft = 0;
            });
        });
        window.__bsScrollKeep = true;
        return window.dash_clientside.no_update;
    }
    """,
    Output('bs-view-reset', 'data'),
    Input('game_id', 'children'),
)


@callback(
    Output('bs-period', 'data'),
    Output('bs-period-control', 'value'),
    Input('bs-period-control', 'value'),
    Input('game_id', 'children'),
    prevent_initial_call=True,
)
def update_bs_period(control_value, game_id):
    period = resolve_bs_period(ctx.triggered_id, control_value)
    return period, period


@callback(
    Output('pane-rotation', 'children'),
    Input('rotation_store', 'data'),
    Input('tabs', 'value'),
)
def update_pane_rotation(rotation_store, active_tab, view_store=None, match_info_store=None):
    if active_tab != 'tab-rotation':
        return no_update
    return render_rotation_children(rotation_store, view_store, match_info_store)


@callback(
    Output('rotation-period', 'data'),
    Input('rotation_store', 'data'),
)
def update_rotation_period_options(rotation_store):
    payload = safe_loads(rotation_store)
    return _period_control_data(payload.get('periods') or [])


@callback(
    Output('shot-chart-period', 'data'),
    Output('shot-chart-period-bar', 'style'),
    Input('pbp_store', 'data'),
)
def update_shot_chart_period_options(pbp_store):
    return shot_chart_period_state(pbp_store)


@callback(
    Output('shot-chart-player-away', 'data'),
    Output('shot-chart-player-home', 'data'),
    Input('pbp_store', 'data'),
    Input('match_info_store', 'data'),
)
def update_shot_chart_players(pbp_store, match_info_store):
    return shot_chart_player_state(pbp_store, match_info_store)


@callback(
    Output('shot-chart-period', 'value'),
    Output('shot-chart-player-away', 'value'),
    Output('shot-chart-player-home', 'value'),
    Input('game_id', 'children'),
    State('shot-chart-period', 'value'),
    State('shot-chart-player-away', 'value'),
    State('shot-chart-player-home', 'value'),
    prevent_initial_call=True,
)
def reset_shot_chart_filters(game_id, period, away_player, home_player):
    return resolve_shot_chart_filters(ctx.triggered_id, period, away_player, home_player)


@callback(
    Output('pane-shot-chart', 'children'),
    Output('pane-shot-chart', 'style'),
    Output('shot-chart-courts', 'style'),
    Output('shot-chart-name-away', 'children'),
    Output('shot-chart-name-home', 'children'),
    Output('shot-chart-court-away', 'children'),
    Output('shot-chart-court-home', 'children'),
    Input('pbp_store', 'data'),
    Input('match_info_store', 'data'),
    Input('shot-chart-period', 'value'),
    Input('shot-chart-player-away', 'value'),
    Input('shot-chart-player-home', 'value'),
    Input('tabs', 'value'),
)
def update_shot_chart(pbp_store, match_info_store, period, away_player, home_player, active_tab):
    if active_tab != 'tab-shot-chart':
        return (no_update,) * 7
    return shot_chart_outputs(shot_chart_panel(
        pbp_store, match_info_store, period, away_player, home_player,
    ))


@callback(
    Output('rotation-graph', 'figure'),
    Output('rotation-graph', 'style'),
    Output('rotation-graph-paper', 'style'),
    Input('rotation_store', 'data'),
    Input('rotation_view_store', 'data'),
    Input('tabs', 'value'),
    State('match_info_store', 'data'),
)
def update_rotation_graph(rotation_store, view_store, active_tab, match_info_store=None):
    if active_tab != 'tab-rotation':
        return no_update, no_update, no_update
    payload = safe_loads(rotation_store)
    hidden_paper = {'overflow': 'hidden', 'display': 'none'}
    if payload.get('_ui') == 'error' or not payload or not payload.get('teams'):
        return {}, {'width': '100%', 'height': '520px'}, hidden_paper
    fig = _rotation_figure_from_view(payload, _rotation_view(view_store), match_info_store)
    return (
        fig,
        {'width': '100%', 'height': f"{fig.layout.height or 520}px"},
        {'overflow': 'hidden'},
    )


@callback(
    Output('rotation_view_store', 'data'),
    Output('rotation-period', 'value'),
    Output('rotation-show-dnp', 'checked'),
    Input('rotation-period', 'value'),
    Input('rotation-show-dnp', 'checked'),
    Input({'type': 'rotation-run', 'index': ALL}, 'n_clicks'),
    Input('rotation-live', 'n_clicks'),
    Input('rotation-click-t', 'data'),
    Input('rotation-graph', 'relayoutData'),
    Input('rotation_store', 'data'),
    Input('game_id', 'children'),
    State('rotation_view_store', 'data'),
    Input('match_info_store', 'data'),
    prevent_initial_call=True,
)
def update_rotation_view(
    period,
    show_dnp,
    run_clicks,
    live_clicks,
    click_t,
    relayout_data,
    rotation_store,
    game_id,
    view_store,
    match_info_store,
):
    previous = _rotation_view(view_store)
    triggered_id = ctx.triggered_id
    prop_id = ''
    if ctx.triggered:
        prop_id = ctx.triggered[0].get('prop_id') or ''
    if isinstance(prop_id, str) and prop_id.endswith('relayoutData'):
        triggered_id = 'rotation-graph.relayoutData'
    if triggered_id == 'rotation-live' and not live_clicks:
        return no_update, no_update, no_update
    result = apply_rotation_view_event(
        triggered_id,
        period,
        show_dnp,
        run_clicks,
        click_t,
        rotation_store,
        game_id,
        view_store,
        match_info_store,
        relayout_data=relayout_data,
    )
    if result is no_update:
        return no_update, no_update, no_update
    if triggered_id == 'game_id':
        return result, 'all', False
    chip = ctx.triggered_id if isinstance(ctx.triggered_id, dict) else None
    if chip and chip.get('type') == 'rotation-run':
        return result, 'all', no_update
    if triggered_id == 'rotation-graph.relayoutData':
        return result, result.get('period') or 'all', no_update
    if (
        isinstance(result, dict)
        and result.get('finished_reset')
        and not previous.get('finished_reset')
    ):
        return result, 'all', no_update
    return result, no_update, no_update


clientside_callback(
    """
    function(n) {
        if (!n) { return window.dash_clientside.no_update; }
        if (typeof window._rotationClickT !== 'number') {
            return window.dash_clientside.no_update;
        }
        return window._rotationClickT;
    }
    """,
    Output('rotation-click-t', 'data'),
    Input('rotation-click-fire', 'n_clicks'),
    prevent_initial_call=True,
)


@callback(
    Output('rotation-live', 'style'),
    Output('rotation-live', 'variant'),
    Input('match_info_store', 'data'),
    Input('rotation_view_store', 'data'),
)
def update_rotation_live_chip(match_info_store, view_store):
    live = is_live_play_status(safe_loads(match_info_store).get('status'))
    if not live:
        return {'display': 'none'}, 'light'
    follow = _rotation_view(view_store).get('follow_live', True)
    return {}, ('filled' if follow else 'light')


@callback(
    Output('rotation-last-update', 'children'),
    Input('rotation_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_rotation_last_update(rotation_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-rotation':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('lineup-last-update', 'children'),
    Input('lineup_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_lineup_last_update(lineup_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-lineup':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('matchup-team', 'data'),
    Output('matchup-team', 'value'),
    Input('match_info_store', 'data'),
    Input('game_id', 'children'),
    State('matchup-team', 'value'),
)
def sync_matchup_team(match_info_store, _game_id, current):
    info = safe_loads(match_info_store)
    away_id = info.get('away_team_id')
    home_id = info.get('home_team_id')
    away_id = None if away_id in (None, '') else str(away_id)
    home_id = None if home_id in (None, '') else str(home_id)
    if not away_id and not home_id:
        return no_update, no_update
    options = []
    if away_id:
        options.append({'label': info.get('away_team') or 'Away', 'value': away_id})
    if home_id:
        options.append({'label': info.get('home_team') or 'Home', 'value': home_id})
    try:
        triggered = ctx.triggered_id
    except Exception:
        triggered = None
    return options, matchup_team_value(current, away_id, home_id, triggered)


@callback(
    Output('matchup-last-update', 'children'),
    Input('matchup_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_matchup_last_update(matchup_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-matchups':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('matchup-grid', 'rowData'),
    Output('matchup-status', 'children'),
    Output('matchup-grid-wrap', 'style'),
    Input('matchup_store', 'data'),
    Input('matchup-team', 'value'),
    Input('tabs', 'value'),
)
def update_matchup_rows(matchup_store, viewpoint, active_tab):
    if active_tab != 'tab-matchups':
        return no_update, no_update, no_update
    payload = safe_loads(matchup_store)
    hidden = {'display': 'none'}
    if not payload:
        return [], loading_skeleton('table'), hidden
    if payload.get('_ui') == 'error':
        return [], _error_view(payload), hidden
    pairs = payload.get('pairs')
    if not isinstance(pairs, list):
        return [], loading_skeleton('table'), hidden
    if not pairs:
        return [], empty_state(EMPTY_MATCHUPS, EMPTY_GAME_NEXT), hidden
    return matchup_grid_records(payload, viewpoint), [], {'display': 'block'}


@callback(
    Output('shot-chart-last-update', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_shot_chart_last_update(pbp_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-shot-chart':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('pane-pbp', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_pane_pbp(pbp_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-pbp':
        return no_update
    return render_pbp_children(pbp_store, game_id, _organization(league))


@callback(
    Output('pane-lineup', 'children'),
    Input('lineup_size_dropdown', 'value'),
    Input('tabs', 'value'),
    Input('lineup_store', 'data'),
    State('game_id', 'children'),
    State('lineup-show-opp', 'checked'),
    State('game_league', 'children'),
    Input('match_info_store', 'data'),
)
def update_pane_lineup(lineup_size='5', active_tab='tab-lineup', lineup_store=None, game_id=None, show_opp=False, league='plg', match_info=None):
    if active_tab != 'tab-lineup':
        return no_update
    try:
        size_int = int(lineup_size)
    except Exception:
        size_int = 5
    show_opp = bool(show_opp)
    lineup_dict = lineup_tables_for_size(lineup_store, size_int)
    if not lineup_dict and game_id:
        try:
            report = get_cached_report(game_id, _organization(league))
            custom_dict = report.get_lineup_stats_json_dict(lineup_size=size_int)
            if custom_dict:
                return render_lineup_children(
                    json.dumps({str(size_int): custom_dict}),
                    size_int,
                    show_opp=show_opp,
                    match_info=match_info,
                )
        except Exception as exc:
            print(f"Error computing lineup size {lineup_size}: {exc}")
    return render_lineup_children(lineup_store, size_int, show_opp=show_opp, match_info=match_info)


@callback(
    Output('lineup-show-opp', 'checked'),
    Input('game_id', 'children'),
    prevent_initial_call=True,
)
def reset_lineup_show_opp(_game_id):
    return False


clientside_callback(
    """
    function(checked) {
        if (window.applyLineupShowOpp) {
            window.applyLineupShowOpp(!!checked);
        }
        return !!checked;
    }
    """,
    Output('lineup-show-opp-sync', 'data'),
    Input('lineup-show-opp', 'checked'),
    prevent_initial_call=True,
)


@callback(
    Output('pane-report', 'children'),
    Input('tabs', 'value'),
    Input('report-pane-ready', 'data'),
    State('bs_store', 'data'),
    State('lineup_store', 'data'),
    State('match_info_store', 'data'),
    State('game_id', 'children'),
)
def update_pane_report(
    active_tab,
    pane_ready='',
    bs_store=None,
    lineup_store=None,
    match_info_store=None,
    game_id=None,
):
    if active_tab != 'tab-report':
        return no_update
    if str(pane_ready or '') in ('1', 'true', 'True'):
        return no_update
    try:
        return render_report_children(
            bs_store,
            lineup_store,
            match_info_store,
            game_id=game_id,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"Error rendering report: {exc}")
        return [_error_view({'_ui': 'error', 'message': ERROR_GAME})]


@callback(
    Output('report-papers', 'children'),
    Output('report-page-list', 'children'),
    Input('report-page-cmd', 'data'),
    State('match_info_store', 'data'),
    prevent_initial_call=True,
)
def sync_report_page_shells(cmd, match_info_store):
    return apply_page_cmd(cmd, safe_loads(match_info_store))


@callback(
    Output('report-dialog', 'opened'),
    Input('report-dialog-opened', 'data'),
    prevent_initial_call=True,
)
def sync_report_dialog(opened):
    return bool(opened)


clientside_callback(
    """
    function(active_tab) {
        const hide = {display: 'none'};
        const show = {display: 'block'};
        return [
            active_tab === 'tab-bs' ? show : hide,
            active_tab === 'tab-rotation' ? show : hide,
            active_tab === 'tab-shot-chart' ? show : hide,
            active_tab === 'tab-lineup' ? show : hide,
            active_tab === 'tab-matchups' ? show : hide,
            active_tab === 'tab-pbp' ? show : hide,
            active_tab === 'tab-report' ? show : hide
        ];
    }
    """,
    Output('wrap-bs', 'style'),
    Output('wrap-rotation', 'style'),
    Output('wrap-shot-chart', 'style'),
    Output('wrap-lineup', 'style'),
    Output('wrap-matchups', 'style'),
    Output('wrap-pbp', 'style'),
    Output('wrap-report', 'style'),
    Input('tabs', 'value'),
)

