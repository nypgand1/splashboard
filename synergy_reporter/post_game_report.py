import pandas as pd
import json
import os

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats

class PostGameReport():
    def __init__(self, game_id):
        
        self.team_stats_df, self.team_stats_periods_df, self.player_stats_df, self.starter_dict = Parser.parse_game_stats_df(SYNERGY_ORGANIZATION_ID, game_id)
        self.playbyplay_df = Parser.parse_game_pbp_df(SYNERGY_ORGANIZATION_ID, game_id)
        self.id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    def get_period_team_pts_df(self):
        qt_pts_df = pd.DataFrame()
        qt_pts_df['Team'] = self.team_stats_periods_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        qt_pts_df['Period'] = self.team_stats_periods_df['periodId']
        qt_pts_df['PTS'] = self.team_stats_periods_df['points']
        qt_pts_df = qt_pts_df.pivot(index='Team', columns='Period', values='PTS').reset_index()
        qt_pts_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_pts_df
    
    def get_period_team_fouls_df(self):
        qt_foul_df = pd.DataFrame()
        qt_foul_df['Team'] = self.team_stats_periods_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        qt_foul_df['Period'] = self.team_stats_periods_df['periodId']
        qt_foul_df['Foul'] = self.team_stats_periods_df.get('foulsTotal', '')
        qt_foul_df = qt_foul_df.pivot(index='Team', columns='Period', values='Foul').reset_index()
        qt_foul_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_foul_df
        
    def get_period_team_timeout_df(self):
        qt_tout_df = pd.DataFrame()
        qt_tout_df['Team'] = self.team_stats_periods_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        qt_tout_df['Period'] = self.team_stats_periods_df['periodId']
        qt_tout_df['TOut'] = self.team_stats_periods_df.get('timeoutsUsed', '')
        qt_tout_df = qt_tout_df.pivot(index='Team', columns='Period', values='TOut').reset_index()
        qt_tout_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_tout_df

    def get_team_advance_stats_df(self):
        t_adv_df = pd.DataFrame()
        t_adv_df['Team'] = self.team_stats_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        self.team_stats_df['poss'] = self.team_stats_df['fieldGoalsAttempted'] + 0.4 * self.team_stats_df['freeThrowsAttempted'] + self.team_stats_df['turnovers'] - self.team_stats_df['reboundsOffensive']
        self.team_stats_df['duration'] = pd.to_timedelta(self.team_stats_df['minutes'].str.replace('PT', '', regex=False) \
                                                                                    .str.replace('M', ' min ', regex=False) \
                                                                                    .str.replace('S', 'sec', regex=False)).dt.total_seconds()/5
        t_adv_df['Poss'] = self.team_stats_df.apply(lambda x: f"{x['poss']:0.1f}", axis=1)
        #TODO: assume a 48 mins game
        t_adv_df['Pace'] = self.team_stats_df.apply(lambda x: f"{48*60*x['poss']/x['duration']:0.1f}" if pd.notnull(x['duration']) else '', axis=1)
        t_adv_df['PPP'] = self.team_stats_df.apply(lambda x: f"{(x['points']/x['poss']):0.2f}" if pd.notnull(x['poss']) else '', axis=1)
        t_adv_df['eFG%'] = self.team_stats_df.apply(lambda x: f"{x['fieldGoalsEffectivePercentage']:0.1f}%" if pd.notnull(x['fieldGoalsEffectivePercentage']) else '', axis=1)
        t_adv_df['TOV%'] = self.team_stats_df.apply(lambda x: f"{(100*x['turnovers']/x['poss']):0.1f}%" if pd.notnull(x['poss']) else '', axis=1)
        t_adv_df['ORB%'] = self.team_stats_df.apply(lambda x: f"{(100*x['reboundsOffensive']/(x['reboundsOffensive']+x['reboundsDefensiveAgainst'])):0.1f}%" if pd.notnull(x['reboundsOffensive']+x['reboundsDefensiveAgainst']) else '', axis=1)
        t_adv_df['FT-R'] = self.team_stats_df.apply(lambda x: f"{(100*x['freeThrowsAttempted']/x['fieldGoalsAttempted']):0.1f}%" if pd.notnull(x['fieldGoalsAttempted']) else '', axis=1)
        t_adv_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return t_adv_df

    def get_team_stats_df(self):
        t_df = pd.DataFrame()
        t_df['Team'] = self.team_stats_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        t_df['Min'] = self.team_stats_df['minutes']
        t_df['2PM-A (%)'] = self.team_stats_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:0.1f}%)" if x['pointsTwoAttempted'] else '', axis=1)
        t_df['3PM-A (%)'] = self.team_stats_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:0.1f}%)" if x['pointsThreeAttempted'] else '', axis=1)
        t_df['FTM-A (%)'] = self.team_stats_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:0.1f}%)"if x['freeThrowsAttempted'] else '', axis=1)
        t_df['OR'] = self.team_stats_df['reboundsOffensive']
        t_df['DR'] = self.team_stats_df['reboundsDefensive']
        t_df['REB'] = self.team_stats_df['rebounds']
        t_df['AST'] = self.team_stats_df['assists']
        t_df['TOV'] = self.team_stats_df['turnovers']
        t_df['STL'] = self.team_stats_df['steals']
        t_df['BLK'] = self.team_stats_df['blocks']
        t_df['PF'] = self.team_stats_df['foulsTotal']
        t_df['PTS'] = self.team_stats_df['points']
        t_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return t_df
            
    def get_team_key_stats_df(self):
        k_df = pd.DataFrame()
        k_df['Team'] = self.team_stats_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        k_df['PIPM-A'] = self.team_stats_df.apply(lambda x: f"{x['pointsInThePaintMade']}-{x['pointsInThePaintAttempted']}" if x['pointsInThePaintAttempted'] else '', axis=1)
        k_df['PIP'] = self.team_stats_df['pointsInThePaint']
        k_df['SCPM-A'] = self.team_stats_df.apply(lambda x: f"{x['pointsSecondChanceMade']}-{x['pointsSecondChanceAttempted']}" if x['pointsSecondChanceAttempted'] else '', axis=1)
        k_df['SCP'] = self.team_stats_df['pointsSecondChance']
        k_df['FBP'] = self.team_stats_df['pointsFastBreak']
        k_df['POT'] = self.team_stats_df['pointsFromTurnover']
        k_df['BP'] = self.team_stats_df['pointsFromBench']
        k_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return k_df
    
    def _get_player_stats_df_dict(self):
        p_df_dict = dict()
        for t in self.team_stats_df['entityId'].to_list():
            team_name = self.id_table.get(t, t)
            p_df = self.player_stats_df[self.player_stats_df['entityId']==t]
            p_df_t = pd.DataFrame()
            p_df_t['Player'] = p_df.apply(lambda x: self.id_table.get(x['personId'], x['personId']), axis=1)
            p_df_t['Min'] = p_df['minutes']
            p_df_t['+/-'] = p_df['plusMinus']
            p_df_t['2PM-A (%)'] = p_df.apply(lambda x: f"{x['pointsTwoMade']}-{x['pointsTwoAttempted']} ({x['pointsTwoPercentage']:0.1f}%)" if x['pointsTwoAttempted']!=0 else '', axis=1)
            p_df_t['3PM-A (%)'] = p_df.apply(lambda x: f"{x['pointsThreeMade']}-{x['pointsThreeAttempted']} ({x['pointsThreePercentage']:0.1f}%)" if x['pointsThreeAttempted'] !=0 else '', axis=1)
            p_df_t['FTM-A (%)'] = p_df.apply(lambda x: f"{x['freeThrowsMade']}-{x['freeThrowsAttempted']} ({x['freeThrowsPercentage']:0.1f}%)" if x['freeThrowsAttempted']!=0 else '', axis=1)
            p_df_t['OR'] = p_df['reboundsOffensive']
            p_df_t['DR'] = p_df['reboundsDefensive']
            p_df_t['REB'] = p_df['rebounds']
            p_df_t['AST'] = p_df['assists']
            p_df_t['TOV'] = p_df['turnovers']
            p_df_t['STL'] = p_df['steals']
            p_df_t['BLK'] = p_df['blocks']
            p_df_t['PF'] = p_df['foulsTotal']
            p_df_t['PTS'] = p_df['points']
            p_df_t['eFG%'] = p_df.apply(lambda x: f"{x['fieldGoalsEffectivePercentage']:0.1f}%" if pd.notnull(x['fieldGoalsEffectivePercentage']) else '', axis=1)
            p_df_t['USG%'] = p_df.apply(lambda x: f"{x['usageRate']:0.1f}%", axis=1)
            p_df_t['Plus-Minus'] = p_df.apply(lambda x: f"{x['plus']}-{x['minus']}", axis=1)
    
            p_df_t.sort_values(by=['PTS', '+/-', 'REB', 'AST'], ascending=False, inplace=True)
            p_df_dict[team_name] = p_df_t
        return p_df_dict

    def _get_lineup_stats_df_dict(self):
        pbp_df = self.get_play_by_play_df()
        lineup_df_dict = process_lineup_stats(pbp_df)
    
        def decode_lineup(lineup):
            return str(sorted([self.id_table.get(p ,p) for p in lineup]))[1:-1].replace('\'', '')
    
        u_df_dict = dict()
        for t in lineup_df_dict:
            team_name = self.id_table.get(t, t)
            team_lineup_df = lineup_df_dict[t]
            team_lineup_df['Lineup'] = team_lineup_df[t].apply(lambda x: decode_lineup(x))
    
            team_lineup_df['Min'] = team_lineup_df.apply(lambda x: f"{x['duration']//60:02.0f}:{x['duration']%60:02.0f}", axis=1)
            team_lineup_df['+/-'] = team_lineup_df['PTS']-team_lineup_df['Opp_PTS']
            team_lineup_df['2PM-A (%)'] = team_lineup_df.apply(lambda x: f"{x['2M']}-{x['2A']} ({x['2M']/x['2A']:.1%})" if x['2A'] else None, axis=1)
            team_lineup_df['3PM-A (%)'] = team_lineup_df.apply(lambda x: f"{x['3M']}-{x['3A']} ({x['3M']/x['3A']:.1%})" if x['3A'] else None, axis=1)
            team_lineup_df['FTM-A (%)'] = team_lineup_df.apply(lambda x: f"{x['1M']}-{x['1A']} ({x['1M']/x['1A']:.1%})" if x['1A'] else None, axis=1)
            team_lineup_df['Plus-Minus'] = team_lineup_df.apply(lambda x: f"{x['PTS']}-{x['Opp_PTS']}", axis=1)
            
            team_lineup_df = team_lineup_df[['Lineup', 'Min', '+/-', '2PM-A (%)', '3PM-A (%)', 'FTM-A (%)', 'OR', 'DR', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'PTS', 'Plus-Minus']].copy()
            team_lineup_df.sort_values(by=['+/-', 'PTS', 'REB', 'AST'], ascending=False, inplace=True)
            u_df_dict[team_name] = team_lineup_df

        return u_df_dict
    
    def get_player_stats_json_dict(self):
        player_stats_df_dict = self._get_player_stats_df_dict()
        return {team_name: df.to_json(date_format='iso', orient='split') for team_name, df in player_stats_df_dict.items()}

    def get_lineup_stats_json_dict(self):
        lineup_stats_df_dict = self._get_lineup_stats_df_dict()
        return {team_name: df.to_json(date_format='iso', orient='split') for team_name, df in lineup_stats_df_dict.items()}
   
    def get_play_by_play_df(self):
        process_lineup_pbp(self.playbyplay_df, self.starter_dict)
        team_id_list = self.playbyplay_df['entityId'].dropna().unique()
        
        self.playbyplay_df['Team'] = self.playbyplay_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        self.playbyplay_df['Player'] = self.playbyplay_df.apply(lambda x: self.id_table.get(x['personId'], x['personId']), axis=1)
        team_name_list = self.playbyplay_df['Team'].dropna().unique()
        
        def decode_scores(scores):
            d = json.loads(scores)
            return str({self.id_table.get(t ,t):  d[t] for t in d})[1:-1].replace('\'', '')
        self.playbyplay_df['scores'] = self.playbyplay_df['scores'].apply(lambda x: decode_scores(x))
    
        def decode_lineup(lineup):
            return str(sorted([self.id_table.get(p ,p) for p in lineup]))[1:-1].replace('\'', '')
        for t in team_id_list:
            self.playbyplay_df[self.id_table.get(t, f"name_{t}")] = self.playbyplay_df[t].apply(lambda x: decode_lineup(x))
        
        col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'entityId', 'Team', 'personId', 'Player', 'eventType', 'subType', 'success', 'scores', 'options'] 
        col_list.extend(team_name_list)
        col_list.extend(team_id_list)
        if 'ERROR' in self.playbyplay_df:
            col_list.append('ERROR')
    
        return self.playbyplay_df[col_list]
 
    def save_all_reports_to_csv(self):
        if not os.path.exists('csv_output'):
            os.makedirs('csv_output')
        self.get_period_team_pts_df().to_csv('csv_output/period_team_pts.csv', index=False)
        self.get_period_team_fouls_df().to_csv('csv_output/period_team_fouls.csv', index=False)
        self.get_period_team_timeout_df().to_csv('csv_output/period_team_timeout.csv', index=False)
        self.get_team_advance_stats_df().to_csv('csv_output/team_advance_stats.csv', index=False)
        self.get_team_stats_df().to_csv('csv_output/team_stats.csv', index=False)
        self.get_team_key_stats_df().to_csv('csv_output/team_key_stats.csv', index=False)

        player_stats_dfs = self._get_player_stats_df_dict()
        for team_name, df in player_stats_dfs.items():
            df.to_csv(f'csv_output/player_stats_{team_name}.csv', index=False)

        lineup_stats_dfs = self._get_lineup_stats_df_dict()
        for team_name, df in lineup_stats_dfs.items():
            df.to_csv(f'csv_output/lineup_stats_{team_name}.csv', index=False)
 
def main():
    game_id = input('Game Id? ')
    r = PostGameReport(str(game_id))
    r.save_all_reports_to_csv()

if __name__ == '__main__':
    main()
