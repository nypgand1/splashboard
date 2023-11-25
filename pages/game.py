import datetime

from dash import dcc, html, Input, Output, callback, dash_table, register_page
import dash_bootstrap_components as dbc
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser

register_page(
    __name__,
    name='Splashboard TFB | Game',
    top_nav=True,
    path_template='/game/<game_id>'
)

def layout(game_id):
    layout = html.Div([
        html.Div(html.Span(id='game_id', children=game_id, hidden=True)),
        html.Div(id='live-update-text'),
        html.Div(id='live-update-team'),
        html.Div(id='live-update-key'),
        html.Div(id='live-update-player'),
        dcc.Interval(
            id='interval-component',
            interval=30*1000, #in milliseconds
            n_intervals=0
        )
    ])
    return layout

@callback(Output('live-update-text', 'children'), 
        Input('interval-component', 'n_intervals'))
def update_datetime_now(n):
    return html.Span(f'Last Update: {datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))}')

@callback(Output('live-update-team', 'children'), 
        Input('interval-component', 'n_intervals'),
        Input('game_id', 'children'))
def update_team_stats_table(n, game_id):
    team_stats_df, player_stats_df, starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    t_df = pd.DataFrame()
    t_df['Team'] = team_stats_df.apply(lambda x: id_table.get(x['entityId'], x['entityId']), axis=1)
    t_df['Min'] = team_stats_df['minutes']
    t_df['2PM-A (%)'] = team_stats_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:.1f}%)" if x['pointsTwoAttempted']!=0 else '', axis=1)
    t_df['3PM-A (%)'] = team_stats_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:.1f}%)" if x['pointsThreeAttempted']!=0 else '', axis=1)
    t_df['FTM-A (%)'] = team_stats_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:.1f}%)"if x['freeThrowsAttempted']!=0 else '', axis=1)
    t_df['OR'] = team_stats_df['reboundsOffensive']
    t_df['DR'] = team_stats_df['reboundsDefensive']
    t_df['REB'] = team_stats_df['rebounds']
    t_df['AST'] = team_stats_df['assists']
    t_df['TOV'] = team_stats_df['turnovers']
    t_df['STL'] = team_stats_df['steals']
    t_df['BLK'] = team_stats_df['blocks']
    t_df['PF'] = team_stats_df['foulsTotal']
    t_df['PTS'] = team_stats_df['points']

    return dbc.Table.from_dataframe(t_df, striped=True, bordered=True, hover=True, class_name='text-nowrap')

@callback(Output('live-update-key', 'children'), 
        Input('interval-component', 'n_intervals'),
        Input('game_id', 'children'))
def update_key_stats_table(n, game_id):
    team_stats_df, player_stats_df, starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    k_df = pd.DataFrame()
    k_df['Team'] = team_stats_df.apply(lambda x: id_table.get(x['entityId'], x['entityId']), axis=1)
    k_df['PIPM-A'] = team_stats_df.apply(lambda x: f"{x['pointsInThePaintMade']}-{x['pointsInThePaintAttempted']}" if x['pointsInThePaintAttempted']!=0 else '', axis=1)
    k_df['PIP'] = team_stats_df['pointsInThePaint']
    k_df['SCPM-A'] = team_stats_df.apply(lambda x: f"{x['pointsSecondChanceMade']}-{x['pointsSecondChanceAttempted']}" if x['pointsSecondChanceAttempted']!=0 else '', axis=1)
    k_df['SCP'] = team_stats_df['pointsSecondChance']
    k_df['FBP'] = team_stats_df['pointsFastBreak']
    k_df['POT'] = team_stats_df['pointsFromTurnover']
    k_df['BP'] = team_stats_df['pointsFromBench']

    return dbc.Table.from_dataframe(k_df, striped=True, bordered=True, hover=True, class_name='text-nowrap')

@callback(Output('live-update-player', 'children'), 
        Input('interval-component', 'n_intervals'),
        Input('game_id', 'children'))
def update_player_stats_table(n, game_id):
    team_stats_df, player_stats_df, starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    p_df_dict = dict()
    for t in team_stats_df['entityId'].to_list():
        p_df = player_stats_df[player_stats_df['entityId']==t]
        p_df_dict[t] = pd.DataFrame()
        p_df_dict[t]['Player'] = p_df.apply(lambda x: id_table.get(x['personId'], x['personId']), axis=1)
        p_df_dict[t]['Min'] = p_df['minutes']
        p_df_dict[t]['+/-'] = p_df['plusMinus']
        p_df_dict[t]['2PM-A (%)'] = p_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:.1f}%)" if x['pointsTwoAttempted']!=0 else '', axis=1)
        p_df_dict[t]['3PM-A (%)'] = p_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:.1f}%)" if x['pointsThreeAttempted'] !=0 else '', axis=1)
        p_df_dict[t]['FTM-A (%)'] = p_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:.1f}%)" if x['freeThrowsAttempted']!=0 else '', axis=1)
        p_df_dict[t]['OR'] = p_df['reboundsOffensive']
        p_df_dict[t]['DR'] = p_df['reboundsDefensive']
        p_df_dict[t]['REB'] = p_df['rebounds']
        p_df_dict[t]['AST'] = p_df['assists']
        p_df_dict[t]['TOV'] = p_df['turnovers']
        p_df_dict[t]['STL'] = p_df['steals']
        p_df_dict[t]['BLK'] = p_df['blocks']
        p_df_dict[t]['PF'] = p_df['foulsTotal']
        p_df_dict[t]['PTS'] = p_df['points']
        p_df_dict[t]['eFG%'] = p_df.apply(lambda x: f"{x['fieldGoalsEffectivePercentage']:.1f}%" if pd.notnull(x['fieldGoalsEffectivePercentage']) else '', axis=1)
        p_df_dict[t]['USG%'] = p_df.apply(lambda x: f"{x['usageRate']:.1f}%", axis=1)
        p_df_dict[t]['Plus-Minus'] = p_df.apply(lambda x: f"{x['plus']}-{x['minus']}", axis=1)

        p_df_dict[t].sort_values(by=['PTS', '+/-', 'REB', 'AST'], ascending=False, inplace=True)

    return [dbc.Table.from_dataframe(p_df_dict[t], striped=True, bordered=True, hover=True, class_name='text-nowrap') for t in p_df_dict]
