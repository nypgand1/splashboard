import datetime
import json
import io

from dash import dcc, html, Input, Output, callback, dash_table, register_page
import dash_bootstrap_components as dbc
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_reporter.post_game_report import PostGameReport

register_page(
    __name__,
    name='Splashboard TFB | Game',
    top_nav=True,
    path_template='/game/<game_id>'
)

def layout(game_id=None):
    layout = html.Div([
        html.Div(html.Span(id='game_id', children=game_id, hidden=True)),
        dbc.Tabs([
                dbc.Tab(label='Box Score', tab_id='tab-bs'),
                dbc.Tab(label='Play-By-Play', tab_id='tab-pbp'),
                dbc.Tab(label='Lineup Stats', tab_id='tab-lineup'),
            ],
            id='tabs',
            active_tab='tab-bs',
        ),
        html.Div(id='tab_content'),
        html.Div(id='pbp_table', style= {'display': 'block'}),
        dcc.Interval(
            id='interval-component',
            interval=30*1000, #in milliseconds
            n_intervals=0
        ),
        dcc.Store(id='bs_store'),
        dcc.Store(id='pbp_store'),
        dcc.Store(id='lineup_store'),
    ])
    return layout

@callback(Output('bs_store', 'data'), 
        [Input('interval-component', 'n_intervals'),
        Input('game_id', 'children')]
)
def update_bs_store(n, game_id):
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

@callback(Output('pbp_store', 'data'), 
        [Input('interval-component', 'n_intervals'),
        Input('game_id', 'children'),]
)
def update_pbp_store(n, game_id):
    report = PostGameReport(game_id)
    return report.get_play_by_play_df().to_json(date_format='iso', orient='split')

@callback(Output('lineup_store', 'data'), 
        [Input('interval-component', 'n_intervals'),
        Input('game_id', 'children'),]
)
def update_lineup_store(n, game_id):
    report = PostGameReport(game_id)
    return json.dumps(report.get_lineup_stats_json_dict())

@callback(Output('tab_content', 'children'), 
        [Input('tabs', 'active_tab'),
        Input('bs_store', 'data'),
        Input('pbp_store', 'data'),
        Input('lineup_store', 'data'),],
)
def update_tab_content(active_tab, bs_store, pbp_store, lineup_store):
    content_list = [html.Span(f'Last Update: {datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))}')]
    
    if active_tab == 'tab-bs':
        bs_dict = json.loads(bs_store)

        qt_pts_df = pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split')
        qt_foul_df = pd.read_json(io.StringIO(bs_dict['qt_foul_df']), orient='split')
        qt_tout_df = pd.read_json(io.StringIO(bs_dict['qt_tout_df']), orient='split')
        
        t_adv_df = pd.read_json(io.StringIO(bs_dict['t_adv_df']), orient='split')
        t_adv_df['Poss'] = t_adv_df['Poss'].apply(lambda x: f"{x:.1f}")
        t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: f"{x:.1f}")
        t_adv_df['PPP'] = t_adv_df['PPP'].apply(lambda x: f"{x:.2f}")
        
        t_df = pd.read_json(io.StringIO(bs_dict['t_df']), orient='split')
        k_df = pd.read_json(io.StringIO(bs_dict['k_df']), orient='split')
        
        content_list.append(
            html.Div(
                dbc.Row([
                    dbc.Col(dbc.Table.from_dataframe(qt_pts_df, striped=True, bordered=True, hover=True, class_name='text-nowrap')),
                    dbc.Col(dbc.Table.from_dataframe(qt_foul_df, striped=True, bordered=True, hover=True, class_name='text-nowrap')),
                    dbc.Col(dbc.Table.from_dataframe(qt_tout_df, striped=True, bordered=True, hover=True, class_name='text-nowrap')),
                ])
            )
        )
        content_list.append(dbc.Table.from_dataframe(t_adv_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
        content_list.append(dbc.Table.from_dataframe(t_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
        content_list.append(dbc.Table.from_dataframe(k_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
    
        for team_name, p_json in sorted(bs_dict['p_df_dict'].items()):
            content_list.append(html.H4(team_name))
            p_df = pd.read_json(io.StringIO(p_json), orient='split')
            content_list.append(dbc.Table.from_dataframe(p_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
        
    elif active_tab == 'tab-pbp':
        pbp_df = pd.read_json(io.StringIO(pbp_store), orient='split')
        
        team_name_list = pbp_df['Team'].dropna().unique()
        col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'Team', 'Player', 'eventType', 'subType', 'success', 'scores'] 
        col_list.extend(team_name_list)
        pbp_df = pbp_df[col_list]

        content_list.append(dbc.Table.from_dataframe(pbp_df[::-1], striped=True, bordered=True, hover=True, class_name='text-nowrap'))
    
    elif active_tab == 'tab-lineup':
        lineup_dict = json.loads(lineup_store)
        for team_name, l_json in sorted(lineup_dict.items()):
            content_list.append(html.H4(team_name))
            l_df = pd.read_json(io.StringIO(l_json), orient='split')
            content_list.append(dbc.Table.from_dataframe(l_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
    
    return content_list
