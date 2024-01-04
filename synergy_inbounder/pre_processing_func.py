# -*- coding: utf-8 -*-
import pandas as pd
from synergy_inbounder.settings import LOGGER

def process_lineup_pbp(df, starter_dict):
    for t in starter_dict.keys():
        df.loc[0, t] = [starter_dict[t]]
        for i in range(1, len(df)):
            if df.loc[i, 'eventType'] == 'substitution' and df.loc[i, 'entityId'] == t:
                lineup = list(df.loc[i-1, t])
                if df.loc[i, 'subType'] == 'in':
                    if df.loc[i, 'personId'] in lineup:
                        df.loc[i, 'ERROR'] = 'ERROR'
                    else:
                        lineup.append(df.loc[i, 'personId'])
                elif df.loc[i, 'subType'] == 'out':
                    if df.loc[i, 'personId'] not in lineup:
                        df.loc[i, 'ERROR'] = 'ERROR'
                    else:
                        lineup.remove(df.loc[i, 'personId'])
                df.loc[i, t] = [set(lineup)]
            else:
                df.loc[i, t] = [df.loc[i-1, t]]

def get_sub_map(df): 
    result_list = list()
    for t in [t for t in df['entityId'].unique() if not pd.isna(t)]:
        df_team = df[(df['entityId']==t) | ((df['eventType']=='period') & (df['subType'].isin(['pending', 'confirmed'])))]
        for p in [p for p in df_team['personId'].unique() if not pd.isna(p)]:
            df_team['selected'] = df_team.apply(lambda x: (x['personId']==p) or ((x['eventType']=='period') and (p in x[t])), axis=1)
            df_player = df_team[df_team['selected']].reindex()
            
            df_player['clock'] = pd.to_datetime(df_player['clock'], format='PT%MM%SS')
            df_player['clock_prev'] = df_player['clock'].shift(1)
            df_duration = df_player[df_player['subType'].isin(['out', 'confirmed'])]

            player_sub_map = {'entityId': t, 'personId': p, 'fixtureId': [f for f in df['fixtureId'] if not pd.isna(f)][0]}
            for i, r in df_duration.iterrows():
                #TODO: if it's not 12-min period
                if r['periodId'] not in [1, 2, 3, 4]: #overtime
                    player_sub_map['OT'] = player_sub_map.get('OT', 0) + (r['clock_prev']-r['clock']).seconds
                elif r['clock'].minute == r['clock_prev'].minute:
                    if r['clock'].second != r['clock_prev'].second: #not same
                        pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['clock'].minute)
                        player_sub_map[pm_str] = player_sub_map.get(pm_str, 0) + r['clock_prev'].second - r['clock'].second
                else:
                    if r['clock_prev'].second: #not 0 Seconds
                        pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['clock_prev'].minute)
                        player_sub_map[pm_str] = player_sub_map.get(pm_str, 0) + r['clock_prev'].second
                    pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['clock'].minute)
                    player_sub_map[pm_str] = player_sub_map.get(pm_str, 0) + 60 - r['clock'].second
                    for m in range(r['clock_prev'].minute-1, r['clock'].minute, -1):
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
        df_team['clock'] = pd.to_datetime(df_team['clock'], format='PT%MM%SS')
        
        team_score_map = {'{period}Q{minute:0>2d}M'.format(period=p, minute=m): 0 for p in [1, 2, 3, 4] for m in range(0, 12)}
        team_score_map['entityId'] = t
        team_score_map['fixtureId'] = [f for f in df['fixtureId'] if not pd.isna(f)][0]
        
        for i, r in df_team.iterrows():
            if r['periodId'] not in [1, 2, 3, 4]: #overtime
                team_score_map['OT'] = team_score_map.get('OT', 0) + r['score_point']
            else:
                pm_str = '{period}Q{minute:0>2d}M'.format(period=r['periodId'], minute=11-r['clock'].minute)
                team_score_map[pm_str] = team_score_map[pm_str] + r['score_point']
        result_list.append(team_score_map)

    result_df = pd.DataFrame(result_list)
    return result_df
