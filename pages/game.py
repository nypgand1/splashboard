import datetime
import json

from dash import dcc, html, Input, Output, callback, dash_table, register_page
import dash_bootstrap_components as dbc
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats

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
    team_stats_df, player_stats_df, starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)
    
    t_df = pd.DataFrame()
    t_df['Team'] = team_stats_df.apply(lambda x: id_table.get(x['entityId'], x['entityId']), axis=1)
    t_df['Min'] = team_stats_df['minutes']
    t_df['2PM-A (%)'] = team_stats_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:.1f}%)" if x['pointsTwoAttempted'] else None, axis=1)
    t_df['3PM-A (%)'] = team_stats_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:.1f}%)" if x['pointsThreeAttempted'] else None, axis=1)
    t_df['FTM-A (%)'] = team_stats_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:.1f}%)"if x['freeThrowsAttempted'] else None, axis=1)
    t_df['OR'] = team_stats_df['reboundsOffensive']
    t_df['DR'] = team_stats_df['reboundsDefensive']
    t_df['REB'] = team_stats_df['rebounds']
    t_df['AST'] = team_stats_df['assists']
    t_df['TOV'] = team_stats_df['turnovers']
    t_df['STL'] = team_stats_df['steals']
    t_df['BLK'] = team_stats_df['blocks']
    t_df['PF'] = team_stats_df['foulsTotal']
    t_df['PTS'] = team_stats_df['points']
        
    k_df = pd.DataFrame()
    k_df['Team'] = team_stats_df.apply(lambda x: id_table.get(x['entityId'], x['entityId']), axis=1)
    k_df['PIPM-A'] = team_stats_df.apply(lambda x: f"{x['pointsInThePaintMade']}-{x['pointsInThePaintAttempted']}" if x['pointsInThePaintAttempted'] else None, axis=1)
    k_df['PIP'] = team_stats_df['pointsInThePaint']
    k_df['SCPM-A'] = team_stats_df.apply(lambda x: f"{x['pointsSecondChanceMade']}-{x['pointsSecondChanceAttempted']}" if x['pointsSecondChanceAttempted'] else None, axis=1)
    k_df['SCP'] = team_stats_df['pointsSecondChance']
    k_df['FBP'] = team_stats_df['pointsFastBreak']
    k_df['POT'] = team_stats_df['pointsFromTurnover']
    k_df['BP'] = team_stats_df['pointsFromBench']

    p_df_list = list()
    for t in team_stats_df['entityId'].to_list():
        p_df = player_stats_df[player_stats_df['entityId']==t]
        p_df_t = pd.DataFrame()
        p_df_t['Player'] = p_df.apply(lambda x: id_table.get(x['personId'], x['personId']), axis=1)
        p_df_t['Min'] = p_df['minutes']
        p_df_t['+/-'] = p_df['plusMinus']
        p_df_t['2PM-A (%)'] = p_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:.1f}%)" if x['pointsTwoAttempted']!=0 else '', axis=1)
        p_df_t['3PM-A (%)'] = p_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:.1f}%)" if x['pointsThreeAttempted'] !=0 else '', axis=1)
        p_df_t['FTM-A (%)'] = p_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:.1f}%)" if x['freeThrowsAttempted']!=0 else '', axis=1)
        p_df_t['OR'] = p_df['reboundsOffensive']
        p_df_t['DR'] = p_df['reboundsDefensive']
        p_df_t['REB'] = p_df['rebounds']
        p_df_t['AST'] = p_df['assists']
        p_df_t['TOV'] = p_df['turnovers']
        p_df_t['STL'] = p_df['steals']
        p_df_t['BLK'] = p_df['blocks']
        p_df_t['PF'] = p_df['foulsTotal']
        p_df_t['PTS'] = p_df['points']
        p_df_t['eFG%'] = p_df.apply(lambda x: f"{x['fieldGoalsEffectivePercentage']:.1f}%" if pd.notnull(x['fieldGoalsEffectivePercentage']) else '', axis=1)
        p_df_t['USG%'] = p_df.apply(lambda x: f"{x['usageRate']:.1f}%", axis=1)
        p_df_t['Plus-Minus'] = p_df.apply(lambda x: f"{x['plus']}-{x['minus']}", axis=1)

        p_df_t.sort_values(by=['PTS', '+/-', 'REB', 'AST'], ascending=False, inplace=True)
        p_df_list.append(p_df_t.to_json(date_format='iso', orient='split'))

    bs_dict = {
        't_df': t_df.to_json(date_format='iso', orient='split'),
        'k_df': k_df.to_json(date_format='iso', orient='split'),
        'p_df_list': p_df_list
    }

    return json.dumps(bs_dict)

@callback(Output('pbp_store', 'data'), 
        [Input('interval-component', 'n_intervals'),
        Input('game_id', 'children'),]
)
def update_pbp_store(n, game_id):
    team_stats_df, player_stats_df, starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
    playbyplay_df = Parser.parse_game_pbp_df(SYNERGY_ORGANIZATION_ID, game_id)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)
 
    process_lineup_pbp(playbyplay_df, starter_dict)
    team_id_list = playbyplay_df['entityId'].dropna().unique()
    
    playbyplay_df['Team'] = playbyplay_df.apply(lambda x: id_table.get(x['entityId'], x['entityId']), axis=1)
    playbyplay_df['Player'] = playbyplay_df.apply(lambda x: id_table.get(x['personId'], x['personId']), axis=1)
    team_name_list = playbyplay_df['Team'].dropna().unique()
    
    def decode_scores(scores):
        d = json.loads(scores)
        return str({id_table.get(t ,t):  d[t] for t in d})[1:-1].replace('\'', '')
    playbyplay_df['scores'] = playbyplay_df['scores'].apply(lambda x: decode_scores(x))

    def decode_lineup(lineup):
        return str(sorted([id_table.get(p ,p) for p in lineup]))[1:-1].replace('\'', '')
    for t in team_id_list:
        playbyplay_df[id_table.get(t, f"name_{t}")] = playbyplay_df[t].apply(lambda x: decode_lineup(x))
    
    col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'entityId', 'Team', 'personId', 'Player', 'eventType', 'subType', 'success', 'scores', 'options'] 
    col_list.extend(team_name_list)
    col_list.extend(team_id_list)
    if 'ERROR' in playbyplay_df:
        col_list.append('ERROR')

    pbp_df = playbyplay_df[col_list]
    return pbp_df.to_json(date_format='iso', orient='split')

@callback(Output('lineup_store', 'data'), 
        [Input('pbp_store', 'data'),]
)
def update_lineup_store(pbp_store):
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)
    
    pbp_df = pd.read_json(pbp_store, orient='split')
    lineup_df_dict = process_lineup_stats(pbp_df)

    def decode_lineup(lineup):
        return str(sorted([id_table.get(p ,p) for p in lineup]))[1:-1].replace('\'', '')

    lineup_list = list()
    for t in lineup_df_dict:
        team_lineup_df = lineup_df_dict[t]
        team_lineup_df['Lineup'] = team_lineup_df[t].apply(lambda x: decode_lineup(x))

        team_lineup_df['Min'] = team_lineup_df.apply(lambda x: f"{x['duration']//60:02.0f}:{x['duration']%60:02.0f}", axis=1)
        team_lineup_df['+/-'] = team_lineup_df['PTS']-team_lineup_df['Opp_PTS']
        team_lineup_df['2PM-A (%)'] = team_lineup_df.apply(lambda x: f"{x['2M']}-{x['2A']} ({x['2M']/x['2A']:.1%})" if x['2A'] else None, axis=1)
        team_lineup_df['3PM-A (%)'] = team_lineup_df.apply(lambda x: f"{x['3M']}-{x['3A']} ({x['3M']/x['3A']:.1%})" if x['3A'] else None, axis=1)
        team_lineup_df['FTM-A (%)'] = team_lineup_df.apply(lambda x: f"{x['1M']}-{x['1A']} ({x['1M']/x['1A']:.1%})" if x['1A'] else None, axis=1)
        team_lineup_df['Plus-Minus'] = team_lineup_df.apply(lambda x: f"{x['PTS']}-{x['Opp_PTS']}", axis=1)
        
        team_lineup_df = team_lineup_df[['Lineup', 'Min', '+/-', '2PM-A (%)', '3PM-A (%)', 'FTM-A (%)', 'OR', 'DR', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'PTS', 'Plus-Minus']]
        team_lineup_df.sort_values(by=['+/-', 'PTS', 'REB', 'AST'], ascending=False, inplace=True)
        lineup_list.append(team_lineup_df.to_json(date_format='iso', orient='split'))

    return json.dumps(lineup_list)

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
        t_df = pd.read_json(bs_dict['t_df'], orient='split')
        k_df = pd.read_json(bs_dict['k_df'], orient='split')

        content_list.append(dbc.Table.from_dataframe(t_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
        content_list.append(dbc.Table.from_dataframe(k_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
    
        for p_json in bs_dict['p_df_list']:
            p_df = pd.read_json(p_json, orient='split')
            content_list.append(dbc.Table.from_dataframe(p_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
        
    elif active_tab == 'tab-pbp':
        pbp_df = pd.read_json(pbp_store, orient='split')
        
        team_name_list = pbp_df['Team'].dropna().unique()
        col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'Team', 'Player', 'eventType', 'subType', 'success', 'scores'] 
        col_list.extend(team_name_list)
        pbp_df = pbp_df[col_list]

        content_list.append(dbc.Table.from_dataframe(pbp_df[::-1], striped=True, bordered=True, hover=True, class_name='text-nowrap'))
    
    elif active_tab == 'tab-lineup':
        lineup_list = json.loads(lineup_store)
        for l_json in lineup_list:
            l_df = pd.read_json(l_json, orient='split')
            content_list.append(dbc.Table.from_dataframe(l_df, striped=True, bordered=True, hover=True, class_name='text-nowrap'))
    
    return content_list
