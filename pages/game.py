import datetime
import io
import json
import os

from dash import ALL, ctx, dcc, html, Input, Output, State, callback, register_page, clientside_callback, no_update
import dash_mantine_components as dmc
import dash_ag_grid as dag
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.runtime_cache import (
    LIVE_CADENCE_SECONDS,
    get_cached_report,
)
from synergy_inbounder.game_status import (
    is_live_play_status,
    status_bucket,
)
from synergy_reporter.report_components import (
    apply_page_cmd,
    lineup_tables_for_size,
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
from synergy_reporter.shot_chart import (
    court_data_uri,
    court_zones,
    period_chips as shot_period_chips,
    player_options,
)
from ui_kit import (
    EMPTY_GAME,
    EMPTY_GAME_NEXT,
    ERROR_GAME,
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
    path_template='/game/<game_id>'
)

ROTATION_GRAPH_CONFIG = {
    'displayModeBar': False,
    'responsive': True,
    'scrollZoom': False,
    'doubleClick': False,
}


def _box_score_wrap():
    matrix = html.Div(id='bs-matrix', children=loading_skeleton('cards'))
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
    detail = html.Div(id='bs-detail')
    body = html.Div(id='pane-bs', children=[matrix, bar, detail])
    if os.environ.get('SPLASHBOARD_E2E'):
        return html.Div(body, id='wrap-bs')
    return html.Div(
        dcc.Loading(custom_spinner=loading_skeleton('cards'), children=body),
        id='wrap-bs',
    )


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
    row = filter_control(
        '',
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
            fullWidth=True,
        ),
    )
    return dmc.Box(row, mb='sm')


def _lineup_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    pane = html.Div(id='pane-lineup', children=loading_skeleton('table'))
    if os.environ.get('SPLASHBOARD_E2E'):
        body = pane
    else:
        body = dcc.Loading(custom_spinner=loading_skeleton('table'), children=pane)
    return html.Div(
        [
            html.Div(id='lineup-last-update', children=_last_update_span()),
            _lineup_controls(),
            body,
        ],
        id='wrap-lineup',
        style=style,
    )


def layout(game_id=None):
    return html.Div([
        html.Div(html.Span(id='game_id', children=game_id, hidden=True)),
        
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
        dcc.Store(id='pbp_store'),
        dcc.Store(id='lineup_store'),
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
        }),
        dcc.Store(id='match_info_store'),
        dcc.Store(id='report-pane-ready', data=''),
        
        # Dummy grid to force Dash to load AG Grid JS/CSS resources on initial load
        html.Div(dag.AgGrid(id="dummy-grid", rowData=[], columnDefs=[]), style={'display': 'none'})
    ])



@callback(
    Output('bs_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children')]
)
def update_bs_store(n, game_id):
    if not game_id:
        return json.dumps({})
    try:
        report = get_cached_report(game_id)
    except Exception as exc:
        print(f"Error loading box score: {exc}")
        return _error_store()
    bs_dict = {
        'qt_pts_df': report.get_period_team_pts_df().to_json(date_format='iso', orient='split'),
        'qt_foul_df': report.get_period_team_fouls_df().to_json(date_format='iso', orient='split'),
        'qt_tout_df': report.get_period_team_timeout_df().to_json(date_format='iso', orient='split'),
        't_adv_df': report.get_team_advance_stats_df().to_json(date_format='iso', orient='split'),
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
     Input('game_id', 'children')]
)
def update_match_info_store(n, game_id):
    if not game_id:
        return json.dumps({})
    try:
        season_df = Parser.parse_season_game_list_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)
        id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)
        game_row = season_df[season_df['fixtureId'] == game_id]
        if game_row.empty:
            return json.dumps({})
        row = game_row.iloc[0]
        
        home_name = id_table.get(row['teamIdHome'], row['teamIdHome'])
        away_name = id_table.get(row['teamIdAway'], row['teamIdAway'])
        venue_name = id_table.get(row['venueId'], row['venueId'])
        
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
        }
        return json.dumps(info, ensure_ascii=False)
    except Exception as e:
        print(f"Error loading match info: {e}")
        return json.dumps({})

@callback(
    Output('game-info-banner-wrap', 'children'),
    Input('match_info_store', 'data')
)
def render_game_info_banner(match_info_store):
    info = safe_loads(match_info_store)
    if not info:
        return html.Div()
    return game_banner(
        home_team=info.get('home_team') or 'Home',
        away_team=info.get('away_team') or 'Away',
        home_score=info.get('home_score') or '—',
        away_score=info.get('away_score') or '—',
        status=info.get('status') or '',
        date=info.get('date') or '',
        time=info.get('time') or '',
        venue=info.get('venue') or '',
    )

@callback(
    Output('interval-component', 'disabled'),
    Input('match_info_store', 'data'),
)
def set_interval_disabled(match_info_store):
    info = safe_loads(match_info_store)
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
     Input('game_id', 'children')]
)
def update_pbp_store(n, game_id):
    if not game_id:
        return json.dumps({})
    try:
        report = get_cached_report(game_id)
    except Exception as exc:
        print(f"Error loading play-by-play: {exc}")
        return _error_store()
    return report.get_play_by_play_df().to_json(date_format='iso', orient='split')

@callback(
    Output('lineup_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children')]
)
def update_lineup_store(n, game_id):
    if not game_id:
        return json.dumps({})
    try:
        report = get_cached_report(game_id)
        from synergy_inbounder.runtime_cache import warmup_game_report
        warmup_game_report(game_id)
    except Exception as exc:
        print(f"Error loading lineup: {exc}")
        return _error_store()
    return json.dumps(report.get_all_lineup_stats_json_dict(sizes=(5,)))

@callback(
    Output('rotation_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('match_info_store', 'data')],
)
def update_rotation_store(n, game_id, match_info_store):
    if not game_id:
        return json.dumps({})
    try:
        report = get_cached_report(game_id)
    except Exception as exc:
        print(f"Error loading rotation: {exc}")
        return _error_store()
    info = safe_loads(match_info_store)
    return json.dumps(report.get_rotation_payload(
        home_team_id=info.get('home_team_id'),
        away_team_id=info.get('away_team_id'),
    ))

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

def _error_store(message=None):
    return json.dumps({
        '_ui': 'error',
        'message': message or ERROR_GAME,
    })


def _last_update_span():
    return dmc.Text(
        f'Last Update: {datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))}',
        size="sm",
        c="dimmed",
        mb=8,
        className="no-print",
    )


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


def _dmc_table_from_df(df, is_team_summary=True, title=None):
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
                # Lower is better for Fouls, TO, TOV, TOV%, PF
                if is_fouls_card or col in ('Foul', 'PF', 'TO', 'TOV', 'TOV%'):
                    col_winners[col] = 0 if val0 < val1 else 1
                else:
                    col_winners[col] = 0 if val0 > val1 else 1

    has_grouped_cols = any(c in df.columns for c in ('2M', '2A', '2FG%', '3M', '3A', '3FG%'))
    has_key_stats_grouped = any(c in df.columns for c in ('PIPM', 'PIPA', 'PIP', 'SCPM', 'SCPA', 'SCP'))
    
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

        for col in ('AST', 'TO', 'ST', 'BL', 'PF', 'FD', 'PTS', 'eFG%', 'USG%', 'PM'):
            if col in df.columns:
                top_row.append(dmc.TableTh(
                    col,
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
        if any(c in df.columns for c in ('PIPM', 'PIPA', 'PIP')):
            top_row.append(dmc.TableTh("PIP", tableProps={"colSpan": 3}, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                dmc.TableTh("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("PTS", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])
        if any(c in df.columns for c in ('SCPM', 'SCPA', 'SCP')):
            top_row.append(dmc.TableTh("SCP", tableProps={"colSpan": 3}, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                dmc.TableTh("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                dmc.TableTh("PTS", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])
        for col in ('FBP', 'POT', 'BP'):
            if col in df.columns:
                top_row.append(dmc.TableTh(
                    col,
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
    elif any(c in df.columns for c in ('eFG%', 'TOV%', 'ORB%', 'FT-R')):
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
        if 'PPP' in df.columns:
            top_row.append(dmc.TableTh(
                "PPP",
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
        ff_cols = [c for c in ('eFG%', 'TOV%', 'ORB%', 'FT-R') if c in df.columns]
        if ff_cols:
            top_row.append(dmc.TableTh(
                "4 FACTORS",
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
            stripe_color = "#0077b6" if row_idx == 0 else "#94a3b8"
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
    5: (260, 270),
}


def _lineup_col_size(lineup_size):
    try:
        size = int(lineup_size)
    except Exception:
        size = 5
    return LINEUP_COL_SIZES.get(size, LINEUP_COL_SIZES[5])


def _build_stats_column_defs(columns, filterable_cols=None, lineup_size=5):
    col_set = set(columns)
    column_defs = []

    sorted_cell_rules = {"ag-sorted-col-bg": "params.column.isSortActive()"}

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
            "minWidth": 50,
            "width": 56,
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
            "minWidth": 46,
            "width": 48,
            "cellRenderer": "PlusMinusCell",
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if any(c in col_set for c in ('2M', '2A', '2FG%')):
        children = []
        if '2M' in col_set:
            children.append({"field": "2M", "headerName": "M", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if '2A' in col_set:
            children.append({"field": "2A", "headerName": "A", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if '2FG%' in col_set:
            children.append({"field": "2FG%", "headerName": "%", "sortable": True, "minWidth": 52, "width": 56, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        column_defs.append({
            "headerName": "2PT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('3M', '3A', '3FG%')):
        children = []
        if '3M' in col_set:
            children.append({"field": "3M", "headerName": "M", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if '3A' in col_set:
            children.append({"field": "3A", "headerName": "A", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if '3FG%' in col_set:
            children.append({"field": "3FG%", "headerName": "%", "sortable": True, "minWidth": 52, "width": 56, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        column_defs.append({
            "headerName": "3PT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('FTM', 'FTA', 'FT%')):
        children = []
        if 'FTM' in col_set:
            children.append({"field": "FTM", "headerName": "M", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if 'FTA' in col_set:
            children.append({"field": "FTA", "headerName": "A", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if 'FT%' in col_set:
            children.append({"field": "FT%", "headerName": "%", "sortable": True, "minWidth": 52, "width": 56, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        column_defs.append({
            "headerName": "FT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('OR', 'DR', 'REB')):
        children = []
        if 'OR' in col_set:
            children.append({"field": "OR", "headerName": "O", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if 'DR' in col_set:
            children.append({"field": "DR", "headerName": "D", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        if 'REB' in col_set:
            children.append({"field": "REB", "headerName": "T", "sortable": True, "minWidth": 36, "width": 38, "cellStyle": {"textAlign": "center"}, "cellClass": "ag-cell-align-center", "headerClass": "ag-header-align-center", "cellClassRules": sorted_cell_rules})
        column_defs.append({
            "headerName": "REB",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    stat_specs = [
        ('AST', 'AST', 42, 44),
        ('TO', 'TO', 42, 44),
        ('ST', 'ST', 42, 44),
        ('BL', 'BL', 42, 44),
        ('PF', 'PF', 42, 44),
        ('FD', 'FD', 42, 44),
        ('PTS', 'PTS', 44, 46),
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

    return column_defs


def _ag_grid_from_df(df, page_size=None, filterable_cols=None, pinned_bottom_data=None, lineup_size=5):
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
            column_defs.append(col_def)

    dash_options = {
        "domLayout": "autoHeight",
        "suppressHorizontalScroll": False,
    }
    if page_size:
        dash_options["pagination"] = True
        dash_options["paginationPageSize"] = page_size
    if pinned_bottom_data:
        dash_options["pinnedBottomRowData"] = pinned_bottom_data

    grid_class = "ag-theme-alpine braves-clean-ag-grid"
    if any('lineup' in str(c).lower() for c in df.columns):
        grid_class += " braves-lineup-grid"
    return dmc.Paper(
        dag.AgGrid(
            rowData=df.to_dict('records'),
            columnDefs=column_defs,
            defaultColDef={"sortable": True, "filter": False, "resizable": True, "cellClassRules": sorted_cell_rules, "cellDataType": False},
            dashGridOptions=dash_options,
            className=grid_class,
            style={'width': '100%'}
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


def render_bs_sections(bs_store, period='all'):
    bs_dict = safe_loads(bs_store)
    if bs_dict.get('_ui') == 'error':
        return [_error_view(bs_dict)], []
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_empty_view()], []

    selected = str(period or 'all')
    slices = bs_dict.get('slices') if isinstance(bs_dict.get('slices'), dict) else {}
    view = slices.get(selected) if selected != 'all' and isinstance(slices.get(selected), dict) else bs_dict

    qt_pts_df = pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split')
    qt_foul_df = pd.read_json(io.StringIO(bs_dict['qt_foul_df']), orient='split')
    qt_tout_df = pd.read_json(io.StringIO(bs_dict['qt_tout_df']), orient='split')

    t_adv_df = pd.read_json(io.StringIO(view['t_adv_df']), orient='split')
    if 'Pace' in t_adv_df.columns:
        t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: _format_metric(x, 1))
    if 'PPP' in t_adv_df.columns:
        t_adv_df['PPP'] = t_adv_df['PPP'].apply(lambda x: _format_metric(x, 2))

    t_df = pd.read_json(io.StringIO(view['t_df']), orient='split')
    k_df = pd.read_json(io.StringIO(view['k_df']), orient='split')

    # Row 1: 3-column quarter summary with titles 'SCORE', 'FOULS', 'TIMEOUTS' (gap 12px)
    row1 = dmc.SimpleGrid(
        cols={"base": 1, "lg": 3},
        spacing="12px",
        children=[
            _dmc_table_from_df(qt_pts_df, is_team_summary=True, title="Score"),
            _dmc_table_from_df(qt_foul_df, is_team_summary=True, title="Fouls"),
            _dmc_table_from_df(qt_tout_df, is_team_summary=True, title="Timeouts"),
        ],
        style={"marginBottom": "12px"}
    )

    # Row 2: 2-column with titles 'PACE & 4 FACTORS' and 'PAINT / 2nd CHANCE / FASTBREAK / OFF TOV / BENCH' (gap 12px)
    row2 = dmc.SimpleGrid(
        cols={"base": 1, "lg": 2},
        spacing="12px",
        children=[
            _dmc_table_from_df(t_adv_df, is_team_summary=True, title="Pace & 4 Factors"),
            _dmc_table_from_df(k_df, is_team_summary=True, title="Paint / 2nd Chance / Fastbreak / Off TOV / Bench"),
        ],
        style={"marginBottom": "12px"}
    )

    # Row 3: Full Team Box Score
    row3 = dmc.Box(_dmc_table_from_df(t_df, is_team_summary=True), mb="sm")

    matrix = [
        _last_update_span(),
        row1,
    ]
    detail = [row2, row3]

    p_dict = view.get('p_df_dict', {})
    p_summary = view.get('p_summary_dict', {})
    for idx, (team_name, p_json) in enumerate(sorted(p_dict.items())):
        dot_color = "#00b4d8" if idx == 0 else "#94a3b8"
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
        detail.append(title_section)
        p_df = pd.read_json(io.StringIO(p_json), orient='split')
        summary_rows = p_summary.get(team_name) if isinstance(p_summary, dict) else None
        detail.append(_ag_grid_from_df(p_df, page_size=None, pinned_bottom_data=summary_rows))
    return matrix, detail


def render_bs_children(bs_store, period='all'):
    matrix, detail = render_bs_sections(bs_store, period)
    return [*matrix, *detail]


DEFAULT_ROTATION_VIEW = {
    'period': 'all',
    't': None,
    'x0': None,
    'x1': None,
    'show_dnp': False,
    'slice_width': None,
    'axis_rev': 0,
    'follow_live': True,
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


def _render_run_buttons(runs, periods):
    if not runs:
        return None
    buttons = []
    for index, run in enumerate(runs):
        is_home = run.get('side') == 'home'
        buttons.append(
            dmc.Button(
                format_run_label(run, periods),
                id={'type': 'rotation-run', 'index': index},
                color='blue' if is_home else 'gray',
                variant='light',
                size='compact-xs',
                radius='sm',
                px=8,
            )
        )
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
        if is_live_play_status(info.get('status')) and view.get('follow_live', True):
            now = live_playhead_t(payload)
            if now == view.get('t'):
                return no_update
            view['t'] = now
            return view
        return no_update

    return no_update


def render_pbp_children(pbp_store):
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
    grid = dag.AgGrid(
        rowData=pbp_df.to_dict('records'),
        columnDefs=[{
            "field": c,
            "headerClass": "ag-header-align-center",
            "cellClass": "ag-cell-align-center",
            "cellStyle": {"textAlign": "center"},
        } for c in pbp_df.columns],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        columnSize="autoSize",
        className="ag-theme-alpine braves-clean-ag-grid",
        style={'width': '100%'}
    )
    return [_last_update_span(), dmc.Paper(grid, withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden"})]


def render_lineup_children(lineup_store, lineup_size=5):
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
    page_size = 20 if size_int < 5 else None
    for idx, (team_name, l_json) in enumerate(sorted(lineup_dict.items())):
        dot_color = "#00b4d8" if idx == 0 else "#94a3b8"
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
        l_df = pd.read_json(io.StringIO(l_json), orient='split')
        children.append(_ag_grid_from_df(
            l_df,
            page_size=page_size,
            filterable_cols=['Lineup', 'Lineups'],
            lineup_size=size_int,
        ))
    return children


def _report_rotation_figure_json(game_id, match_info):
    if not game_id:
        return json.dumps({'_ui': 'empty'})
    try:
        report = get_cached_report(game_id)
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


def render_report_children(bs_store, lineup_store, match_info_store, game_id=None):
    bs_dict = safe_loads(bs_store) if bs_store else {}
    match_info = safe_loads(match_info_store) if match_info_store else {}
    layout = default_layout(match_info)
    if bs_dict.get('_ui') == 'error':
        return [_error_view(bs_dict)]
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_empty_view()]
    return [
        _last_update_span(),
        render_report_workspace(
            layout,
            bs_dict,
            lineup_store,
            match_info,
            game_id,
            rotation_json=_report_rotation_figure_json(game_id, match_info),
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
    if active_tab != 'tab-bs':
        return no_update, no_update
    return render_bs_sections(bs_store, period)


@callback(
    Output('bs-period-control', 'data'),
    Output('bs-period-bar', 'style'),
    Input('bs_store', 'data'),
)
def update_bs_period_options(bs_store):
    return period_bar_state(bs_store)


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
    State('match_info_store', 'data'),
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
    if isinstance(ctx.triggered_id, dict) and ctx.triggered_id.get('type') == 'rotation-run':
        return result, 'all', no_update
    if triggered_id == 'rotation-graph.relayoutData':
        return result, result.get('period') or 'all', no_update
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
)
def update_rotation_last_update(rotation_store, active_tab):
    if active_tab != 'tab-rotation':
        return no_update
    return _last_update_span()


@callback(
    Output('lineup-last-update', 'children'),
    Input('lineup_store', 'data'),
    Input('tabs', 'value'),
)
def update_lineup_last_update(lineup_store, active_tab):
    if active_tab != 'tab-lineup':
        return no_update
    return _last_update_span()


@callback(
    Output('shot-chart-last-update', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
)
def update_shot_chart_last_update(pbp_store, active_tab):
    if active_tab != 'tab-shot-chart':
        return no_update
    return _last_update_span()


@callback(
    Output('pane-pbp', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
)
def update_pane_pbp(pbp_store, active_tab):
    if active_tab != 'tab-pbp':
        return no_update
    return render_pbp_children(pbp_store)


@callback(
    Output('pane-lineup', 'children'),
    Input('lineup_size_dropdown', 'value'),
    Input('tabs', 'value'),
    State('lineup_store', 'data'),
    State('game_id', 'children'),
)
def update_pane_lineup(lineup_size='5', active_tab='tab-lineup', lineup_store=None, game_id=None):
    if active_tab != 'tab-lineup':
        return no_update
    try:
        size_int = int(lineup_size)
    except Exception:
        size_int = 5
    lineup_dict = lineup_tables_for_size(lineup_store, size_int)
    if not lineup_dict and game_id:
        try:
            report = get_cached_report(game_id)
            custom_dict = report.get_lineup_stats_json_dict(lineup_size=size_int)
            if custom_dict:
                return render_lineup_children(
                    json.dumps({str(size_int): custom_dict}),
                    size_int,
                )
        except Exception as exc:
            print(f"Error computing lineup size {lineup_size}: {exc}")
    return render_lineup_children(lineup_store, size_int)


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
            active_tab === 'tab-pbp' ? show : hide,
            active_tab === 'tab-report' ? show : hide
        ];
    }
    """,
    Output('wrap-bs', 'style'),
    Output('wrap-rotation', 'style'),
    Output('wrap-shot-chart', 'style'),
    Output('wrap-lineup', 'style'),
    Output('wrap-pbp', 'style'),
    Output('wrap-report', 'style'),
    Input('tabs', 'value'),
)

