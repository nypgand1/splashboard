# -*- coding: utf-8 -*-
import json
import pandas as pd
import numpy as np
from synergy_inbounder.settings import LOGGER

def process_lineup_pbp(df, starter_dict):
    for t in starter_dict.keys():
        df[t] = None
        df.at[0, t] = starter_dict[t]
        for i in range(1, len(df)):
            if df.at[i, 'eventType'] == 'substitution' and df.at[i, 'entityId'] == t:
                lineup = list(df.at[i-1, t])
                if df.at[i, 'subType'] == 'in':
                    if df.at[i, 'personId'] in lineup:
                        df.at[i, 'ERROR'] = 'ERROR'
                    else:
                        lineup.append(df.at[i, 'personId'])
                elif df.at[i, 'subType'] == 'out':
                    if df.at[i, 'personId'] not in lineup:
                        df.at[i, 'ERROR'] = 'ERROR'
                    else:
                        lineup.remove(df.at[i, 'personId'])
                df.at[i, t] = list(set(lineup))
            else:
                df.at[i, t] = list(df.at[i-1, t])

def process_lineup_stats(df):
    #lineup_df = df.dropna(subset=['.atk'])
    lineup_df = df
    lineup_df['clock'] = pd.to_datetime(lineup_df['clock'], format='PT%MM%SS')
    lineup_df['periodId_next'] = lineup_df['periodId'].shift(-1)
    lineup_df['clock_next'] = lineup_df['clock'].shift(-1)
    lineup_df['duration'] = lineup_df.apply(lambda x: 0 if x['periodId']!= x['periodId_next'] else (x['clock']-x['clock_next']).total_seconds(), axis=1)
   
    lineup_df_dict = dict()
    for t in lineup_df['entityId'].dropna().unique():
        lineup_df['POSS'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='possession')  else 0, axis=1)
        lineup_df['2M'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='2pt' and x['success']==1) else 0, axis=1)
        lineup_df['2A'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='2pt') else 0, axis=1)
        lineup_df['3M'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='3pt' and x['success']==1) else 0, axis=1)
        lineup_df['3A'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='3pt') else 0, axis=1)
        lineup_df['1M'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='freeThrow' and x['success']==1) else 0, axis=1)
        lineup_df['1A'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='freeThrow') else 0, axis=1)

        lineup_df['OR'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='rebound' and x['subType']=='offensive') else np.nan, axis=1)
        lineup_df['DR'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='rebound' and x['subType']=='defensive') else np.nan, axis=1)
        lineup_df['REB'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='rebound') else np.nan, axis=1)
        lineup_df['AST'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='assist') else np.nan, axis=1)
        lineup_df['TOV'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='turnover') else np.nan, axis=1)
        lineup_df['STL'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='steal') else np.nan, axis=1)
        lineup_df['BLK'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='block') else np.nan, axis=1)
        lineup_df['PF'] = lineup_df.apply(lambda x: 1 if (x['entityId']==t and x['eventType']=='foul' and x['subType']!='drawn') else np.nan, axis=1)
        lineup_df['PTS'] = 2*lineup_df.loc[:, '2M'] + 3*lineup_df.loc[:, '3M'] + lineup_df.loc[:, '1M']
 
        lineup_df['Opp_POSS'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='possession')  else 0, axis=1)
        lineup_df['Opp_2M'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='2pt' and x['success']==1) else 0, axis=1)
        lineup_df['Opp_2A'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='2pt') else 0, axis=1)
        lineup_df['Opp_3M'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='3pt' and x['success']==1) else 0, axis=1)
        lineup_df['Opp_3A'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='3pt') else 0, axis=1)
        lineup_df['Opp_1M'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='freeThrow' and x['success']==1) else 0, axis=1)
        lineup_df['Opp_1A'] = lineup_df.apply(lambda x: 1 if (x['entityId']!=t and x['eventType']=='freeThrow') else 0, axis=1)
        lineup_df['Opp_PTS'] = 2*lineup_df.loc[:, 'Opp_2M'] + 3*lineup_df.loc[:, 'Opp_3M'] + lineup_df.loc[:, 'Opp_1M']
       
        lineup_df[t] = lineup_df.apply(lambda x: json.dumps(sorted(list(x[t]))), axis=1)
        col_list = [t]
        col_list.extend(['duration', 'POSS', 'Opp_POSS', '2M', '2A', '3M', '3A', '1M', '1A', 'OR', 'DR', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'PTS', 'Opp_PTS'])
        lineup_df_t = lineup_df[col_list]

        team_lineup_df = lineup_df_t.groupby(t, as_index=False).sum(min_count=1)
        team_lineup_df[t] = team_lineup_df.apply(lambda x: json.loads(x[t]), axis=1)
        lineup_df_dict[t] = team_lineup_df[team_lineup_df['duration'] > 0]

    return lineup_df_dict

def get_sub_map(df): 
    result_list = list()
    for t in [t for t in df['entityId'].unique() if not pd.isna(t)]:
        df_team = df[(df['entityId']==t) | ((df['eventType']=='period') & (df['subType'].isin(['pending', 'confirmed'])))]
        for p in [p for p in df_team['personId'].unique() if not pd.isna(p)]:
            df_team['selected'] = df_team.apply(lambda x: (x['personId']==p) or ((x['eventType']=='period') and (p in x[t])), axis=1)
            df_player = df_team[df_team['selected']].reindex()
            
            df_player['.atk'] = pd.to_datetime(df_player['clock'], format='PT%MM%SS')
            df_player['.atk_prev'] = df_player['clock'].shift(1)
            df_duration = df_player[df_player['subType'].isin(['out', 'confirmed'])]

            player_sub_map = {'entityId': t, 'personId': p, 'fixtureId': [f for f in df['fixtureId'] if not pd.isna(f)][0]}
            for i, r in df_duration.iterrows():
                #TODO: if it's not 12-min period
                if r['periodId'] not in [1, 2, 3, 4]: #overtime
                    player_sub_map['OT'] = player_sub_map.get('OT', 0) + (r['.atk_prev']-r['clock']).seconds
                elif r['.atk'].minute == r['clock_prev'].minute:
                    if r['.atk'].second != r['clock_prev'].second: #not same
                        pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['.atk'].minute)
                        player_sub_map[pm_str] = player_sub_map.get(pm_str, 0) + r['.atk_prev'].second - r['clock'].second
                else:
                    if r['.atk_prev'].second: #not 0 Seconds
                        pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['.atk_prev'].minute)
                        player_sub_map[pm_str] = player_sub_map.get(pm_str, 0) + r['.atk_prev'].second
                    pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['.atk'].minute)
                    player_sub_map[pm_str] = player_sub_map.get(pm_str, 0) + 60 - r['.atk'].second
                    for m in range(r['.atk_prev'].minute-1, r['clock'].minute, -1):
                        pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-m)
                        player_sub_map[pm_str] = 60
            result_list.append(player_sub_map)
        
    result_df = pd.DataFrame(result_list)
    return result_df

def get_score_map(df): 
    result_list = list()
    point_map = {'freeThrow': 1, '2pt': 2, '3pt': 3}
    
    for t in [t for t in df['entityId'].unique() if not pd.isna(t)]:
        df_team = df[(df['entityId']==t) & (df['success'])]
        df_team['score_point'] = df_team['eventType'].apply(lambda x: point_map[x])
        df_team['.atk'] = pd.to_datetime(df_team['clock'], format='PT%MM%SS')
        
        team_score_map = {'{period}Q{minute:0>2d}M'.format(period=p, minute=m): 0 for p in [1, 2, 3, 4] for m in range(0, 12)}
        team_score_map['entityId'] = t
        team_score_map['fixtureId'] = [f for f in df['fixtureId'] if not pd.isna(f)][0]
        
        for i, r in df_team.iterrows():
            if r['periodId'] not in [1, 2, 3, 4]: #overtime
                team_score_map['OT'] = team_score_map.get('OT', 0) + r['score_point']
            else:
                pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['.atk'].minute)
                team_score_map[pm_str] = team_score_map[pm_str] + r['score_point']
        result_list.append(team_score_map)

    result_df = pd.DataFrame(result_list)
    return result_df
