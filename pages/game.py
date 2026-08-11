import datetime
import json
import io

from dash import dcc, html, Input, Output, State, ALL, callback, register_page, clientside_callback
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser
from synergy_reporter.post_game_report import PostGameReport
from synergy_reporter.report_components import (
    get_default_blocks,
    render_block
)

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
            dbc.Tab(label='Play-By-Play', tab_id='tab-pbp'),
            dbc.Tab(label='Lineup Stats', tab_id='tab-lineup'),
            dbc.Tab(label='Report', tab_id='tab-report'),
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
                style={'width': '200px', 'margin-bottom': '10px'}
            )
        ], id='lineup_dropdown_container', style={'display': 'none'}),

        # Main Tab Content Render Area
        html.Div(id='tab_content'),
        html.Div(id='pbp_table', style={'display': 'block'}),
        
        # Background Stores & Intervals
        dcc.Interval(
            id='interval-component',
            interval=30*1000, # 30s
            n_intervals=0
        ),
        dcc.Store(id='bs_store'),
        dcc.Store(id='pbp_store'),
        dcc.Store(id='lineup_store'),
        dcc.Store(id='match_info_store'),
        html.Div(id='pdf-download-dummy'),
        
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
    report = PostGameReport(game_id)
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
            'home_score': str(row.get('teamScoreHome', '')),
            'away_score': str(row.get('teamScoreAway', '')),
        }
        return json.dumps(info, ensure_ascii=False)
    except Exception as e:
        print(f"Error loading match info: {e}")
        return json.dumps({})

@callback(
    Output('pbp_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children')]
)
def update_pbp_store(n, game_id):
    if not game_id:
        return json.dumps({})
    report = PostGameReport(game_id)
    return report.get_play_by_play_df().to_json(date_format='iso', orient='split')

@callback(
    Output('lineup_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('lineup_size_dropdown', 'value')]
)
def update_lineup_store(n, game_id, lineup_size):
    if not game_id:
        return json.dumps({})
    report = PostGameReport(game_id)
    return json.dumps(report.get_lineup_stats_json_dict(lineup_size=lineup_size))

def safe_loads(val):
    if val is None:
        return {}
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            pass
    return val

# ═══════════════════════════════════════════════════════════
# Tab Content Renderer
# ═══════════════════════════════════════════════════════════
@callback(
    [Output('tab_content', 'children'),
     Output('lineup_dropdown_container', 'style')],
    [Input('tabs', 'active_tab'),
     Input('bs_store', 'data'),
     Input('pbp_store', 'data'),
     Input('lineup_store', 'data')],
    [State('match_info_store', 'data'),
     State('game_id', 'children')]
)
def update_tab_content(active_tab, bs_store, pbp_store, lineup_store, match_info_store, game_id):
    content_list = [html.Span(
        f'Last Update: {datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))}',
        className="text-muted small mb-2 d-block no-print"
    )]
    dropdown_style = {'display': 'none'}
    
    if not bs_store:
        return [html.Div("數據載入中...", className="p-4 text-center text-muted")], dropdown_style

    if active_tab == 'tab-bs':
        bs_dict = safe_loads(bs_store)
        qt_pts_df = pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split')
        qt_foul_df = pd.read_json(io.StringIO(bs_dict['qt_foul_df']), orient='split')
        qt_tout_df = pd.read_json(io.StringIO(bs_dict['qt_tout_df']), orient='split')
        
        t_adv_df = pd.read_json(io.StringIO(bs_dict['t_adv_df']), orient='split')
        t_adv_df['Poss'] = t_adv_df['Poss'].apply(lambda x: f"{float(x):.1f}")
        t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: f"{float(x):.1f}")
        t_adv_df['PPP'] = t_adv_df['PPP'].apply(lambda x: f"{float(x):.2f}")
        
        t_df = pd.read_json(io.StringIO(bs_dict['t_df']), orient='split')
        k_df = pd.read_json(io.StringIO(bs_dict['k_df']), orient='split')
        
        content_list.append(
            html.Div(
                dbc.Row([
                    dbc.Col(dbc.Table.from_dataframe(qt_pts_df, striped=True, bordered=True, hover=True, className='text-nowrap')),
                    dbc.Col(dbc.Table.from_dataframe(qt_foul_df, striped=True, bordered=True, hover=True, className='text-nowrap')),
                    dbc.Col(dbc.Table.from_dataframe(qt_tout_df, striped=True, bordered=True, hover=True, className='text-nowrap')),
                ])
            )
        )
        content_list.append(dbc.Table.from_dataframe(t_adv_df, striped=True, bordered=True, hover=True, className='text-nowrap'))
        content_list.append(dbc.Table.from_dataframe(t_df, striped=True, bordered=True, hover=True, className='text-nowrap'))
        content_list.append(dbc.Table.from_dataframe(k_df, striped=True, bordered=True, hover=True, className='text-nowrap'))
    
        for team_name, p_json in sorted(bs_dict['p_df_dict'].items()):
            content_list.append(html.H4(team_name))
            p_df = pd.read_json(io.StringIO(p_json), orient='split')
            content_list.append(dbc.Table.from_dataframe(p_df, striped=True, bordered=True, hover=True, className='text-nowrap'))
        
    elif active_tab == 'tab-pbp':
        if pbp_store and pbp_store != "{}" and pbp_store != '"{}"':
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
            content_list.append(grid)
    
    elif active_tab == 'tab-lineup':
        dropdown_style = {'display': 'block', 'margin-bottom': '10px'}
        if lineup_store:
            lineup_dict = safe_loads(lineup_store)
            for team_name, l_json in sorted(lineup_dict.items()):
                content_list.append(html.H4(team_name))
                l_df = pd.read_json(io.StringIO(l_json), orient='split')
                content_list.append(dbc.Table.from_dataframe(l_df, striped=True, bordered=True, hover=True, className='text-nowrap'))

    elif active_tab == 'tab-report':
        bs_dict = safe_loads(bs_store) if bs_store else {}
        match_info = safe_loads(match_info_store) if match_info_store else {}
        blocks = get_default_blocks(match_info)
        
        # ── Report Action Bar ──
        action_bar = html.Div([
            dbc.Row([
                dbc.Col(
                    html.H5("Report", className="fw-bold mb-0",
                             style={'color': '#1e293b', 'letterSpacing': '0.5px'}),
                    width="auto"
                ),
                dbc.Col(
                    html.Div([
                        dbc.Button(["📄 PDF"], id='btn-export-pdf', color="danger",
                                   title="下載 A4 橫向 PDF 報告", className="report-toolbar-btn-export"),
                    ], className="d-flex align-items-center gap-2 justify-content-end"),
                ),
            ], className="align-items-center")
        ], className="p-2 px-3 mb-3 bg-light border rounded no-print")

        # ── Render blocks ──
        rendered_block_elements = [
            html.Div(className="a4-width-indicator no-print")
        ]
        for b in blocks:
            rendered_block_elements.extend(render_block(b, bs_dict, lineup_store))

        report_canvas = html.Div([
            html.Div(rendered_block_elements, id="report-canvas-list")
        ], id="report-canvas")

        content_list.extend([action_bar, report_canvas])
    
    return content_list, dropdown_style

# Clientside Callback for Native Browser Print to PDF
clientside_callback(
    """
    function(n_clicks) {
        if (!n_clicks) return window.dash_clientside.no_update;
        window.print();
        return '';
    }
    """,
    Output('pdf-download-dummy', 'children'),
    Input('btn-export-pdf', 'n_clicks'),
    prevent_initial_call=True
)
