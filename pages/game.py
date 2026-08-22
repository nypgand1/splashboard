import datetime
import io
import json

from dash import dcc, html, Input, Output, State, callback, register_page, clientside_callback, no_update
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.runtime_cache import (
    LIVE_CADENCE_SECONDS,
    get_cached_report,
    is_finished_status,
)
from synergy_reporter.report_components import (
    lineup_tables_for_size,
    render_report_workspace,
)
from synergy_reporter.report_layout import (
    default_layout,
    report_tab_is_visible,
)
from synergy_reporter.rotation import build_rotation_figure

register_page(
    __name__,
    name='Splashboard TFB | Game',
    top_nav=True,
    path_template='/game/<game_id>'
)

def layout(game_id=None):
    return html.Div([
        html.Div(html.Span(id='game_id', children=game_id, hidden=True)),
        
        # Upper Tabs
        dbc.Tabs([
            dbc.Tab(label='Box Score', tab_id='tab-bs'),
            dbc.Tab(label='Rotation', tab_id='tab-rotation'),
            dbc.Tab(label='Play-By-Play', tab_id='tab-pbp'),
            dbc.Tab(label='Lineup Stats', tab_id='tab-lineup'),
            dbc.Tab(
                label='Report',
                tab_id='tab-report',
                id='report-tab',
                tab_style={'display': 'none'},
            ),
        ],
        id='tabs',
        active_tab='tab-bs',
        ),
        
        # Lineup Dropdown Container
        html.Div([
            html.Label("Lineups", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
            dcc.Dropdown(
                id='lineup_size_dropdown',
                options=[
                    {'label': '5 Players', 'value': 5},
                    {'label': '4 Players', 'value': 4},
                    {'label': '3 Players', 'value': 3},
                    {'label': '2 Players', 'value': 2},
                ],
                value=5,
                clearable=False,
                searchable=False,
                style={'width': '200px', 'margin-bottom': '10px'}
            )
        ], id='lineup_dropdown_container', style={'display': 'none'}),

        html.Div(
            dcc.Loading(type='circle', children=html.Div(id='pane-bs')),
            id='wrap-bs',
        ),
        html.Div(
            dcc.Loading(type='circle', children=html.Div(id='pane-rotation')),
            id='wrap-rotation',
            style={'display': 'none'},
        ),
        html.Div(
            dcc.Loading(type='circle', children=html.Div(id='pane-pbp')),
            id='wrap-pbp',
            style={'display': 'none'},
        ),
        html.Div(
            dcc.Loading(type='circle', children=html.Div(id='pane-lineup')),
            id='wrap-lineup',
            style={'display': 'none'},
        ),
        html.Div(
            dcc.Loading(type='circle', children=html.Div(id='pane-report')),
            id='wrap-report',
            style={'display': 'none'},
        ),
        html.Div(id='pbp_table', style={'display': 'block'}),
        
        # Background Stores & Intervals
        dcc.Interval(
            id='interval-component',
            interval=LIVE_CADENCE_SECONDS * 1000,
            n_intervals=0
        ),
        dcc.Store(id='bs_store'),
        dcc.Store(id='pbp_store'),
        dcc.Store(id='lineup_store'),
        dcc.Store(id='rotation_store'),
        dcc.Store(id='match_info_store'),
        
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
        return json.dumps({})
    bs_dict = {
        'qt_pts_df': report.get_period_team_pts_df().to_json(date_format='iso', orient='split'),
        'qt_foul_df': report.get_period_team_fouls_df().to_json(date_format='iso', orient='split'),
        'qt_tout_df': report.get_period_team_timeout_df().to_json(date_format='iso', orient='split'),
        't_adv_df': report.get_team_advance_stats_df().to_json(date_format='iso', orient='split'),
        't_df': report.get_team_stats_df().to_json(date_format='iso', orient='split'),
        'k_df': report.get_team_key_stats_df().to_json(date_format='iso', orient='split'),
        'p_df_dict': report.get_player_stats_json_dict()
    }
    return json.dumps(bs_dict)

@callback(
    Output('match_info_store', 'data'),
    Input('game_id', 'children'),
)
def update_match_info_store(game_id):
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
            date_display = dt.strftime('%Y年%m月%d日')
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
    Output('interval-component', 'disabled'),
    Input('match_info_store', 'data'),
)
def set_interval_disabled(match_info_store):
    info = safe_loads(match_info_store)
    return is_finished_status(info.get('status'))


@callback(
    Output('report-tab', 'tab_style'),
    Output('tabs', 'active_tab'),
    Input('match_info_store', 'data'),
    State('tabs', 'active_tab'),
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
        return json.dumps({})
    return report.get_play_by_play_df().to_json(date_format='iso', orient='split')

@callback(
    Output('lineup_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('tabs', 'active_tab')]
)
def update_lineup_store(n, game_id, active_tab):
    if not game_id:
        return json.dumps({})
    if active_tab not in ('tab-lineup', 'tab-report'):
        return no_update
    try:
        report = get_cached_report(game_id)
    except Exception as exc:
        print(f"Error loading lineup: {exc}")
        return json.dumps({})
    return json.dumps(report.get_all_lineup_stats_json_dict())

@callback(
    Output('rotation_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('tabs', 'active_tab'),
     Input('match_info_store', 'data')],
)
def update_rotation_store(n, game_id, active_tab, match_info_store):
    if not game_id:
        return json.dumps({})
    if active_tab != 'tab-rotation':
        return no_update
    try:
        report = get_cached_report(game_id)
    except Exception as exc:
        print(f"Error loading rotation: {exc}")
        return json.dumps({})
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

def _last_update_span():
    return html.Span(
        f'Last Update: {datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))}',
        className="text-muted small mb-2 d-block no-print"
    )


def _loading_placeholder():
    return html.Div("Loading...", className="p-4 text-center text-muted")


def render_bs_children(bs_store):
    if not bs_store:
        return _loading_placeholder()
    bs_dict = safe_loads(bs_store)
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return _loading_placeholder()

    qt_pts_df = pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split')
    qt_foul_df = pd.read_json(io.StringIO(bs_dict['qt_foul_df']), orient='split')
    qt_tout_df = pd.read_json(io.StringIO(bs_dict['qt_tout_df']), orient='split')

    t_adv_df = pd.read_json(io.StringIO(bs_dict['t_adv_df']), orient='split')
    t_adv_df['Poss'] = t_adv_df['Poss'].apply(lambda x: f"{float(x):.1f}")
    t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: f"{float(x):.1f}")
    t_adv_df['PPP'] = t_adv_df['PPP'].apply(lambda x: f"{float(x):.2f}")

    t_df = pd.read_json(io.StringIO(bs_dict['t_df']), orient='split')
    k_df = pd.read_json(io.StringIO(bs_dict['k_df']), orient='split')

    children = [
        _last_update_span(),
        html.Div(
            dbc.Row([
                dbc.Col(dbc.Table.from_dataframe(qt_pts_df, striped=True, bordered=True, hover=True, className='text-nowrap')),
                dbc.Col(dbc.Table.from_dataframe(qt_foul_df, striped=True, bordered=True, hover=True, className='text-nowrap')),
                dbc.Col(dbc.Table.from_dataframe(qt_tout_df, striped=True, bordered=True, hover=True, className='text-nowrap')),
            ])
        ),
        dbc.Table.from_dataframe(t_adv_df, striped=True, bordered=True, hover=True, className='text-nowrap'),
        dbc.Table.from_dataframe(t_df, striped=True, bordered=True, hover=True, className='text-nowrap'),
        dbc.Table.from_dataframe(k_df, striped=True, bordered=True, hover=True, className='text-nowrap'),
    ]
    for team_name, p_json in sorted(bs_dict.get('p_df_dict', {}).items()):
        children.append(html.H4(team_name))
        p_df = pd.read_json(io.StringIO(p_json), orient='split')
        children.append(dbc.Table.from_dataframe(p_df, striped=True, bordered=True, hover=True, className='text-nowrap'))
    return children


def render_rotation_children(rotation_store):
    payload = safe_loads(rotation_store)
    if not payload or not payload.get('teams'):
        return [_last_update_span(), _loading_placeholder()]
    fig = build_rotation_figure(payload)
    return [
        _last_update_span(),
        dcc.Graph(
            id='rotation-graph',
            figure=fig,
            config={'displayModeBar': False, 'responsive': False},
            style={
                'height': f"{fig.layout.height or 640}px",
                'width': f"{fig.layout.width or 1220}px",
            },
        ),
    ]


def render_pbp_children(pbp_store):
    if not pbp_store or pbp_store == "{}" or pbp_store == '"{}"':
        return [_last_update_span(), _loading_placeholder()]
    pbp_df = pd.read_json(io.StringIO(pbp_store), orient='split')
    team_name_list = pbp_df['Team'].dropna().unique()
    col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'Team', 'Player', 'eventType', 'subType', 'success', 'scores']
    col_list.extend(team_name_list)
    col_list = [c for c in col_list if c in pbp_df.columns]
    pbp_df = pbp_df[col_list][::-1]
    grid = dag.AgGrid(
        rowData=pbp_df.to_dict('records'),
        columnDefs=[{"field": c} for c in pbp_df.columns],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight"},
        columnSize="autoSize",
        className="ag-theme-alpine",
        style={'width': '100%'}
    )
    return [_last_update_span(), grid]


def render_lineup_children(lineup_store, lineup_size):
    lineup_dict = lineup_tables_for_size(lineup_store, lineup_size)
    if not lineup_dict:
        return [_last_update_span(), _loading_placeholder()]
    children = [_last_update_span()]
    for team_name, l_json in sorted(lineup_dict.items()):
        children.append(html.H4(team_name))
        l_df = pd.read_json(io.StringIO(l_json), orient='split')
        children.append(dbc.Table.from_dataframe(l_df, striped=True, bordered=True, hover=True, className='text-nowrap'))
    return children


def render_report_children(bs_store, lineup_store, match_info_store, game_id=None):
    bs_dict = safe_loads(bs_store) if bs_store else {}
    match_info = safe_loads(match_info_store) if match_info_store else {}
    layout = default_layout(match_info)
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_last_update_span(), _loading_placeholder()]
    return [
        _last_update_span(),
        render_report_workspace(layout, bs_dict, lineup_store, match_info, game_id),
    ]


@callback(
    Output('pane-bs', 'children'),
    Input('bs_store', 'data'),
    Input('tabs', 'active_tab'),
)
def update_pane_bs(bs_store, active_tab):
    if active_tab != 'tab-bs':
        return no_update
    return render_bs_children(bs_store)


@callback(
    Output('pane-rotation', 'children'),
    Input('rotation_store', 'data'),
    Input('tabs', 'active_tab'),
)
def update_pane_rotation(rotation_store, active_tab):
    if active_tab != 'tab-rotation':
        return no_update
    return render_rotation_children(rotation_store)


@callback(
    Output('pane-pbp', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'active_tab'),
)
def update_pane_pbp(pbp_store, active_tab):
    if active_tab != 'tab-pbp':
        return no_update
    return render_pbp_children(pbp_store)


@callback(
    Output('pane-lineup', 'children'),
    Input('lineup_store', 'data'),
    Input('lineup_size_dropdown', 'value'),
    Input('tabs', 'active_tab'),
)
def update_pane_lineup(lineup_store, lineup_size, active_tab):
    if active_tab != 'tab-lineup':
        return no_update
    return render_lineup_children(lineup_store, lineup_size)


@callback(
    Output('pane-report', 'children'),
    Input('tabs', 'active_tab'),
    Input('lineup_store', 'data'),
    State('bs_store', 'data'),
    State('match_info_store', 'data'),
    State('game_id', 'children'),
)
def update_pane_report(active_tab, lineup_store, bs_store, match_info_store, game_id):
    if active_tab != 'tab-report':
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
        return [_last_update_span(), html.Div(str(exc), className="p-4 text-danger")]


clientside_callback(
    """
    function(active_tab) {
        const hide = {display: 'none'};
        const show = {display: 'block'};
        const dropdown = (active_tab === 'tab-lineup')
            ? {display: 'block', 'margin-bottom': '10px'}
            : {display: 'none'};
        return [
            active_tab === 'tab-bs' ? show : hide,
            active_tab === 'tab-rotation' ? show : hide,
            active_tab === 'tab-pbp' ? show : hide,
            active_tab === 'tab-lineup' ? show : hide,
            active_tab === 'tab-report' ? show : hide,
            dropdown
        ];
    }
    """,
    Output('wrap-bs', 'style'),
    Output('wrap-rotation', 'style'),
    Output('wrap-pbp', 'style'),
    Output('wrap-lineup', 'style'),
    Output('wrap-report', 'style'),
    Output('lineup_dropdown_container', 'style'),
    Input('tabs', 'active_tab'),
)
