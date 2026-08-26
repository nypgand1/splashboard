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
        
        # Game Info Banner Card (visible across all tabs)
        html.Div(id='game-info-banner-wrap'),

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
        'p_df_dict': report.get_player_stats_json_dict(),
        'p_summary_dict': report.get_player_box_score_summary_json_dict(),
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
    Output('game-info-banner-wrap', 'children'),
    Input('match_info_store', 'data')
)
def render_game_info_banner(match_info_store):
    info = safe_loads(match_info_store)
    if not info:
        return html.Div()
    
    home_name = info.get('home_team') or 'Home'
    away_name = info.get('away_team') or 'Away'
    home_score = info.get('home_score') or '—'
    away_score = info.get('away_score') or '—'
    status = info.get('status') or ''
    date_val = info.get('date') or ''
    time_val = info.get('time') or ''
    venue_val = info.get('venue') or ''
    
    is_live = status.upper() in ('LIVE', 'IN_PROGRESS', 'RUNNING')
    badge_color = "red" if is_live else "blue"
    badge_label = "● LIVE" if is_live else (status.upper() if status else "FINISHED")

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                away_name,
                                style={
                                    "fontSize": "16px",
                                    "fontWeight": 800,
                                    "color": "#0f172a",
                                }
                            ),
                            html.Span(
                                f"{away_score}",
                                style={
                                    "fontSize": "22px",
                                    "fontWeight": 900,
                                    "color": "#0077b6",
                                    "margin": "0 12px 0 10px",
                                }
                            ),
                            html.Span(
                                "vs",
                                style={
                                    "fontSize": "13px",
                                    "fontWeight": 700,
                                    "color": "#94a3b8",
                                    "marginRight": "12px",
                                }
                            ),
                            html.Span(
                                f"{home_score}",
                                style={
                                    "fontSize": "22px",
                                    "fontWeight": 900,
                                    "color": "#0077b6",
                                    "marginRight": "10px",
                                }
                            ),
                            html.Span(
                                home_name,
                                style={
                                    "fontSize": "16px",
                                    "fontWeight": 800,
                                    "color": "#0f172a",
                                }
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"}
                    ),
                    dmc.Badge(
                        badge_label,
                        color=badge_color,
                        variant="light",
                        size="md",
                        radius="sm",
                        style={"fontWeight": 700}
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                    "flexWrap": "wrap",
                    "gap": "10px",
                    "marginBottom": "4px",
                }
            ),
            html.Div(
                " • ".join(p for p in (date_val, time_val, venue_val) if p),
                style={"fontSize": "12px", "color": "#64748b", "fontWeight": 500}
            )
        ],
        className="braves-card-wrapper game-info-banner",
        style={
            "backgroundColor": "#ffffff",
            "borderRadius": "10px",
            "border": "1px solid #e2e8f0",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.03)",
            "padding": "12px 18px",
            "marginBottom": "16px",
        }
    )

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


def _align_from_header(col):
    col_str = str(col).lower()
    if 'player' in col_str or 'lineup' in col_str or 'team' in col_str:
        return "right"
    return "center"


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
        return html.Div("—", className="text-muted fst-italic text-center p-2")
    
    def _align(col):
        return "center"

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
                top_row.append(html.Th(
                    col.upper(),
                    rowSpan=2,
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
            top_row.append(html.Th("2PT", colSpan=3, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                html.Th("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("%", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        if any(c in df.columns for c in ('3M', '3A', '3FG%')):
            top_row.append(html.Th("3PT", colSpan=3, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                html.Th("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("%", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        if any(c in df.columns for c in ('FTM', 'FTA', 'FT%')):
            top_row.append(html.Th("FT", colSpan=3, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                html.Th("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("%", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        if any(c in df.columns for c in ('OR', 'DR', 'REB')):
            top_row.append(html.Th("REB", colSpan=3, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                html.Th("O", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("D", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("T", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])

        for col in ('AST', 'TO', 'ST', 'BL', 'PF', 'FD', 'PTS', 'eFG%', 'USG%', 'PM'):
            if col in df.columns:
                top_row.append(html.Th(
                    col,
                    rowSpan=2,
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
        header = [html.Tr(top_row), html.Tr(sub_row)]
    elif has_key_stats_grouped:
        top_row = []
        sub_row = []
        if 'Team' in df.columns:
            top_row.append(html.Th(
                "TEAM",
                rowSpan=2,
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
            top_row.append(html.Th("PIP", colSpan=3, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                html.Th("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("PTS", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])
        if any(c in df.columns for c in ('SCPM', 'SCPA', 'SCP')):
            top_row.append(html.Th("SCP", colSpan=3, style={"textAlign": "center", "padding": "4px 8px", "fontSize": "12px", "fontWeight": 700, "color": "#0f172a", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}))
            sub_row.extend([
                html.Th("M", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("A", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
                html.Th("PTS", style={"textAlign": "center", "padding": "4px 6px", "fontSize": "11px", "fontWeight": 700, "color": "#475569", "borderBottom": "1px solid #e2e8f0", "backgroundColor": "#f8fafc"}),
            ])
        for col in ('FBP', 'POT', 'BP'):
            if col in df.columns:
                top_row.append(html.Th(
                    col,
                    rowSpan=2,
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
        header = [html.Tr(top_row), html.Tr(sub_row)]
    elif any(c in df.columns for c in ('eFG%', 'TOV%', 'ORB%', 'FT-R')):
        top_row = []
        sub_row = []
        if 'Team' in df.columns:
            top_row.append(html.Th(
                "TEAM",
                rowSpan=2,
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
            top_row.append(html.Th(
                "PACE",
                rowSpan=2,
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
            top_row.append(html.Th(
                "PPP",
                rowSpan=2,
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
            top_row.append(html.Th(
                "4 FACTORS",
                colSpan=len(ff_cols),
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
                sub_row.append(html.Th(
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
        header = [html.Tr(top_row), html.Tr(sub_row)]
    else:
        header = [html.Tr([
            html.Th(
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


def _build_stats_column_defs(columns, filterable_cols=None):
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
            "minWidth": 260 if is_lineup else 95,
            "cellStyle": {"textAlign": "center", "fontWeight": "700"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        }
        if is_lineup:
            col_def["flex"] = 1
        else:
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
            "cellStyle": {"textAlign": "center", "fontWeight": "700", "color": "#0077b6"},
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
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if '+/-' in col_set:
        column_defs.append({
            "field": "+/-",
            "headerName": "+/-",
            "sortable": True,
            "minWidth": 42,
            "width": 46,
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


def _ag_grid_from_df(df, page_size=None, filterable_cols=None, pinned_bottom_data=None):
    if df is None or df.empty:
        return html.Div("—", className="text-muted fst-italic text-center p-2")
    
    sorted_cell_rules = {"ag-sorted-col-bg": "params.column.isSortActive()"}

    # If standard basketball stats table (2PT/3PT/FT breakdown present), use multi-level grouped columns
    if any(c in df.columns for c in ('2M', '2A', '2FG%', '3M', '3A', '3FG%')):
        column_defs = _build_stats_column_defs(df.columns, filterable_cols=filterable_cols)
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
                col_width_props["minWidth"] = 260
                col_width_props["flex"] = 1
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

    return html.Div(
        dag.AgGrid(
            rowData=df.to_dict('records'),
            columnDefs=column_defs,
            defaultColDef={"sortable": True, "filter": False, "resizable": True, "cellClassRules": sorted_cell_rules},
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
    if 'Pace' in t_adv_df.columns:
        t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: f"{float(x):.1f}")
    if 'PPP' in t_adv_df.columns:
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

    # Row 2: 2-column with titles 'PACE & 4 FACTORS' and 'PAINT / 2nd CHANCE / FASTBREAK / OFF TOV / BENCH' (gap 12px)
    row2 = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2},
        spacing="12px",
        children=[
            _dmc_table_from_df(t_adv_df, is_team_summary=True, title="Pace & 4 Factors"),
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
    p_summary = bs_dict.get('p_summary_dict', {})
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
        summary_rows = p_summary.get(team_name) if isinstance(p_summary, dict) else None
        children.append(_ag_grid_from_df(p_df, page_size=None, pinned_bottom_data=summary_rows))
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
