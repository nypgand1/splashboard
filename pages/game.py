import datetime
import io
import json

from dash import dcc, html, Input, Output, State, callback, register_page, clientside_callback, no_update
import dash_mantine_components as dmc
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
        
        # Upper Tabs (DMC Tabs with Dark Liquid Glass container, sticky below 56px Navbar)
        dmc.Tabs(
            [
                dmc.TabsList(
                    [
                        dmc.TabsTab("Box Score", value="tab-bs", leftSection=html.I(className="bi bi-table")),
                        dmc.TabsTab("Rotation", value="tab-rotation", leftSection=html.I(className="bi bi-bar-chart-steps")),
                        dmc.TabsTab("Play-By-Play", value="tab-pbp", leftSection=html.I(className="bi bi-list-ol")),
                        dmc.TabsTab("Lineup Stats", value="tab-lineup", leftSection=html.I(className="bi bi-people")),
                        dmc.TabsTab(
                            "Report",
                            value="tab-report",
                            id="report-tab",
                            leftSection=html.I(className="bi bi-file-earmark-richtext"),
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
        return json.dumps({})
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
        return json.dumps({})
    return json.dumps(report.get_all_lineup_stats_json_dict(sizes=(5,)))

@callback(
    Output('rotation_store', 'data'),
    [Input('interval-component', 'n_intervals'),
     Input('game_id', 'children'),
     Input('tabs', 'value'),
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


def _parse_numeric_stat(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s in ('nan', 'None', '—', '-'):
        return None
    # If percentage in parentheses e.g. "16-47 (34.0%)" or "34.0%"
    if '%' in s:
        try:
            # Extract number before %
            import re
            m = re.search(r'([\d\.]+)%', s)
            if m:
                return float(m.group(1))
        except Exception:
            pass
    # If time MM:SS
    if ':' in s and len(s.split(':')) == 2:
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
        return html.Div("—", className="text-muted fst-italic text-center p-2")
    
    # Alignment: Team/Player left, numeric/stats right
    def _align(col):
        return "left" if col in ('Team', 'Player', 'Venue', 'Game Type', 'Time', 'Status') else "right"

    # Precalculate winning values for each column across rows (team summary tables have 2 rows: Home vs Away)
    col_winners = {}
    if is_team_summary and len(df) == 2:
        for col in df.columns:
            if col in ('Team', 'Min'):
                continue
            val0 = _parse_numeric_stat(df.iloc[0][col])
            val1 = _parse_numeric_stat(df.iloc[1][col])
            if val0 is not None and val1 is not None and val0 != val1:
                # Lower is better for TOV and PF
                if col in ('TOV', 'PF'):
                    col_winners[col] = 0 if val0 < val1 else 1
                else:
                    col_winners[col] = 0 if val0 > val1 else 1

    header = [html.Tr([
        html.Th(
            col,
            style={
                "textAlign": _align(col),
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
            else:
                val_str = str(val)

            # Determine bolding: Only winning row in column is bold (team name itself is regular or semi-bold)
            is_winner = col_winners.get(col) == row_idx
            font_weight = 700 if is_winner else 400

            cell_style = {
                "textAlign": _align(col),
                "padding": "7px 10px",
                "fontSize": "13px",
                "fontWeight": font_weight,
                "color": "#1e293b",
                "whiteSpace": "nowrap",
            }
            if c_idx == 0 and team_stripe_style:
                cell_style.update(team_stripe_style)

            cells.append(html.Td(val_str, style=cell_style))

        rows.append(html.Tr(
            cells,
            className="braves-clean-row",
            style={"backgroundColor": "#ffffff"}
        ))

    table = dmc.Table(
        [html.Thead(header), html.Tbody(rows)],
        withTableBorder=False,
        withColumnBorders=False,
        className="braves-clean-table",
        style={"width": "100%"}
    )

    if title:
        return html.Div(
            [
                html.Div(
                    title.upper(),
                    style={
                        "fontSize": "11px",
                        "fontWeight": 700,
                        "letterSpacing": "0.05em",
                        "color": "#64748b",
                        "padding": "0 0 6px 0",
                    }
                ),
                table
            ],
            className="braves-card-wrapper",
            style={
                "backgroundColor": "#ffffff",
                "borderRadius": "10px",
                "border": "1px solid #e2e8f0",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.03)",
                "padding": "12px 14px",
                "overflow": "hidden",
            }
        )
    return html.Div(
        table,
        className="braves-card-wrapper",
        style={
            "backgroundColor": "#ffffff",
            "borderRadius": "10px",
            "border": "1px solid #e2e8f0",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.03)",
            "padding": "12px 14px",
            "overflow": "hidden",
        }
    )


def _ag_grid_from_df(df, page_size=None, filterable_cols=None):
    if df is None or df.empty:
        return html.Div("—", className="text-muted fst-italic text-center p-2")
    
    column_defs = []
    for c in df.columns:
        align = "left" if c in ('Player', 'Team', 'Lineup', 'Lineups') or 'lineup' in c.lower() else "right"
        cell_style = {"textAlign": align}
        
        # Bolding rules: Player name or Lineup combinations bold
        if c in ('Player', 'Lineup', 'Lineups') or 'lineup' in c.lower():
            cell_style["fontWeight"] = "700"

        # Filter rules:
        has_filter = bool(filterable_cols and (c in filterable_cols or any(fc.lower() in c.lower() for fc in filterable_cols)))

        # Column width settings: Lineup needs generous minWidth to prevent truncating player names
        col_width_props = {}
        if c in ('Lineup', 'Lineups') or 'lineup' in c.lower():
            col_width_props["minWidth"] = 320
            col_width_props["flex"] = 4
        elif c in ('Player', 'Team'):
            col_width_props["minWidth"] = 110
            col_width_props["flex"] = 1.8
        elif c in ('2PM-A (%)', '3PM-A (%)', 'FTM-A (%)'):
            col_width_props["minWidth"] = 100
            col_width_props["flex"] = 1.2
        elif c == 'Min':
            col_width_props["minWidth"] = 65
            col_width_props["flex"] = 0.9
        elif c in ('PM', '+/-'):
            col_width_props["minWidth"] = 55
            col_width_props["flex"] = 0.8
        else:
            col_width_props["minWidth"] = 45
            col_width_props["flex"] = 0.75

        col_def = {
            "field": c,
            "headerName": c,
            "sortable": True,
            "filter": has_filter,
            "type": "rightAligned" if align == "right" else None,
            "cellStyle": cell_style,
            "headerClass": f"ag-header-align-{align}",
            **col_width_props
        }
        column_defs.append(col_def)

    dash_options = {
        "domLayout": "autoHeight",
        "suppressHorizontalScroll": False,
    }
    if page_size:
        dash_options["pagination"] = True
        dash_options["paginationPageSize"] = page_size

    return html.Div(
        dag.AgGrid(
            rowData=df.to_dict('records'),
            columnDefs=column_defs,
            defaultColDef={"sortable": True, "filter": False, "resizable": True},
            dashGridOptions=dash_options,
            className="ag-theme-alpine braves-clean-ag-grid",
            style={'width': '100%'}
        ),
        className="braves-grid-wrap",
        style={
            "borderRadius": "10px",
            "border": "1px solid #e2e8f0",
            "overflow": "hidden",
            "backgroundColor": "#ffffff",
            "marginBottom": "20px",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.03)"
        }
    )


def render_bs_children(bs_store):
    bs_dict = safe_loads(bs_store)
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_last_update_span(), _loading_placeholder()]

    qt_pts_df = pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split')
    qt_foul_df = pd.read_json(io.StringIO(bs_dict['qt_foul_df']), orient='split')
    qt_tout_df = pd.read_json(io.StringIO(bs_dict['qt_tout_df']), orient='split')

    t_adv_df = pd.read_json(io.StringIO(bs_dict['t_adv_df']), orient='split')
    t_adv_df['Poss'] = t_adv_df['Poss'].apply(lambda x: f"{float(x):.1f}")
    t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: f"{float(x):.1f}")
    t_adv_df['PPP'] = t_adv_df['PPP'].apply(lambda x: f"{float(x):.2f}")

    t_df = pd.read_json(io.StringIO(bs_dict['t_df']), orient='split')
    k_df = pd.read_json(io.StringIO(bs_dict['k_df']), orient='split')

    # Row 1: 3-column quarter summary with titles 'SCORE', 'FOULS', 'TIMEOUTS' (gap 12px)
    row1 = dmc.SimpleGrid(
        cols={"base": 1, "sm": 3},
        spacing="12px",
        children=[
            _dmc_table_from_df(qt_pts_df, is_team_summary=True, title="Score"),
            _dmc_table_from_df(qt_foul_df, is_team_summary=True, title="Fouls"),
            _dmc_table_from_df(qt_tout_df, is_team_summary=True, title="Timeouts"),
        ],
        style={"marginBottom": "12px"}
    )

    # Row 2: 2-column with titles 'POSS & 4 FACTORS' and 'PAINT / 2nd CHANCE / FASTBREAK / OFF TOV / BENCH' (gap 12px)
    row2 = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2},
        spacing="12px",
        children=[
            _dmc_table_from_df(t_adv_df, is_team_summary=True, title="Poss & 4 Factors"),
            _dmc_table_from_df(k_df, is_team_summary=True, title="Paint / 2nd Chance / Fastbreak / Off TOV / Bench"),
        ],
        style={"marginBottom": "12px"}
    )

    # Row 3: Full Team Box Score
    row3 = html.Div(_dmc_table_from_df(t_df, is_team_summary=True), style={"marginBottom": "12px"})

    children = [
        _last_update_span(),
        row1,
        row2,
        row3,
    ]

    p_dict = bs_dict.get('p_df_dict', {})
    for idx, (team_name, p_json) in enumerate(sorted(p_dict.items())):
        dot_color = "#00b4d8" if idx == 0 else "#94a3b8"
        title_section = html.Div(
            [
                html.Span(
                    style={
                        "display": "inline-block",
                        "width": "8px",
                        "height": "8px",
                        "borderRadius": "50%",
                        "backgroundColor": dot_color,
                        "marginRight": "8px",
                    }
                ),
                html.Span(
                    team_name,
                    style={
                        "fontSize": "16px",
                        "fontWeight": 800,
                        "color": "#0f172a",
                    }
                ),
            ],
            style={"display": "flex", "alignItems": "center", "margin": "20px 0 10px 2px"}
        )
        children.append(title_section)
        p_df = pd.read_json(io.StringIO(p_json), orient='split')
        children.append(_ag_grid_from_df(p_df, page_size=None))
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
        className="ag-theme-alpine braves-clean-ag-grid",
        style={'width': '100%'}
    )
    return [_last_update_span(), grid]


def render_lineup_children(lineup_store, lineup_size):
    lineup_dict = lineup_tables_for_size(lineup_store, lineup_size)
    if not lineup_dict:
        return [_last_update_span(), _loading_placeholder()]
    children = [_last_update_span()]
    for idx, (team_name, l_json) in enumerate(sorted(lineup_dict.items())):
        dot_color = "#00b4d8" if idx == 0 else "#94a3b8"
        title_section = html.Div(
            [
                html.Span(
                    style={
                        "display": "inline-block",
                        "width": "8px",
                        "height": "8px",
                        "borderRadius": "50%",
                        "backgroundColor": dot_color,
                        "marginRight": "8px",
                    }
                ),
                html.Span(
                    team_name,
                    style={
                        "fontSize": "16px",
                        "fontWeight": 800,
                        "color": "#0f172a",
                    }
                ),
            ],
            style={"display": "flex", "alignItems": "center", "margin": "20px 0 10px 2px"}
        )
        children.append(title_section)
        l_df = pd.read_json(io.StringIO(l_json), orient='split')
        children.append(_ag_grid_from_df(l_df, page_size=None, filterable_cols=['Lineup', 'Lineups']))
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
    Input('tabs', 'value'),
)
def update_pane_bs(bs_store, active_tab):
    if active_tab != 'tab-bs':
        return no_update
    return render_bs_children(bs_store)


@callback(
    Output('pane-rotation', 'children'),
    Input('rotation_store', 'data'),
    Input('tabs', 'value'),
)
def update_pane_rotation(rotation_store, active_tab):
    if active_tab != 'tab-rotation':
        return no_update
    return render_rotation_children(rotation_store)


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
def update_pane_lineup(lineup_size=5, active_tab='tab-lineup', lineup_store=None, game_id=None):
    if active_tab != 'tab-lineup':
        return no_update
    lineup_dict = lineup_tables_for_size(lineup_store, lineup_size)
    if not lineup_dict and game_id:
        try:
            report = get_cached_report(game_id)
            custom_dict = report.get_lineup_stats_json_dict(lineup_size=lineup_size)
            if custom_dict:
                children = [_last_update_span()]
                for team_name, l_json in sorted(custom_dict.items()):
                    children.append(dmc.Title(team_name, order=4, style={"margin": "16px 0 8px"}))
                    l_df = pd.read_json(io.StringIO(l_json), orient='split')
                    children.append(_ag_grid_from_df(l_df, page_size=20))
                return children
        except Exception as exc:
            print(f"Error computing lineup size {lineup_size}: {exc}")
    return render_lineup_children(lineup_store, lineup_size)


@callback(
    Output('pane-report', 'children'),
    Input('tabs', 'value'),
    State('lineup_store', 'data'),
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
    Input('tabs', 'value'),
)
