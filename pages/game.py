from dash import html, dash_table, register_page
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
    t_df, k_df = df_data(game_id)
    layout = html.Div([
        dbc.Table.from_dataframe(t_df, striped=True, bordered=True, hover=True),
        dbc.Table.from_dataframe(k_df, striped=True, bordered=True, hover=True)
    ])
    return layout

def df_data(game_id):
    team_stats_df, player_stats_df, starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    t_df = pd.DataFrame()
    t_df['Team'] = team_stats_df.apply(lambda x: id_table.get(x['entityId'], x['entityId']), axis=1)
    t_df['Min'] = team_stats_df['minutes']
    t_df['2PM-A (%)'] = team_stats_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:.1f}%)", axis=1)
    t_df['3PM-A (%)'] = team_stats_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:.1f}%)", axis=1)
    t_df['FTM-A (%)'] = team_stats_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:.1f}%)", axis=1)
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
    k_df['PIPM-A'] = team_stats_df.apply(lambda x: f"{x['pointsInThePaintMade']}-{x['pointsInThePaintAttempted']}", axis=1)
    k_df['PIP'] = team_stats_df['pointsInThePaint']
    k_df['SCPM-A'] = team_stats_df.apply(lambda x: f"{x['pointsSecondChanceMade']}-{x['pointsSecondChanceAttempted']}", axis=1)
    k_df['SCP'] = team_stats_df['pointsSecondChance']
    k_df['FBP'] = team_stats_df['pointsFastBreak']
    k_df['POT'] = team_stats_df['pointsFromTurnover']
    k_df['BP'] = team_stats_df['pointsFromBench']
    """
    turnoversTeam
    reboundsTeamDefensive	reboundsTeamOffensive	reboundsTeamTotal
    """
    return t_df, k_df
