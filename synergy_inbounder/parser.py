# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import json

from synergy_inbounder.communicator import Communicator

class Parser:
    @staticmethod
    def parse_season_game_list_df(org_id, season_id):
        season_game_list = Communicator.get_season_game_list(org_id, season_id)['data']
        df = pd.DataFrame(season_game_list)

        df[['teamAId', 'teamAIsHome', 'teamAScore']] = df['competitors'].apply(pd.Series)[0].apply(pd.Series)[['entityId', 'isHome', 'score']]
        df[['teamBId', 'teamBIsHome', 'teamBScore']] = df['competitors'].apply(pd.Series)[1].apply(pd.Series)[['entityId', 'isHome', 'score']]

        df['teamIdHome'] = df.apply(lambda x: x['teamAId'] if x['teamAIsHome'] else x['teamBId'], axis=1)
        df['teamScoreHome'] = df.apply(lambda x: x['teamAScore'] if x['teamAIsHome'] else x['teamBScore'], axis=1)
        df['teamIdAway'] = df.apply(lambda x: x['teamAId'] if not x['teamAIsHome'] else x['teamBId'], axis=1)
        df['teamScoreAway'] = df.apply(lambda x: x['teamAScore'] if not x['teamAIsHome'] else x['teamBScore'], axis=1)

        return df[['startTimeLocal', 'fixtureId', 'venueId', 'status', 'teamIdHome', 'teamScoreHome', 'teamIdAway', 'teamScoreAway']]

    @staticmethod
    def parse_game_pbp_df(org_id, game_id):
        pbp_json_list = Communicator.get_game_play_by_play_synergy(org_id, game_id)['data']
        df = pd.DataFrame(pbp_json_list)
        df['success'] = df.apply(lambda x: x['success'] if 'success' in x else np.nan, axis=1)
        df['options'] = df.apply(lambda x: json.dumps(x['options']) if (('options' in x) and (not pd.isna(x['options']))) else np.nan, axis=1)
        df['scores'] = df.apply(lambda x: json.dumps(x['scores']), axis=1)

        return df

    @staticmethod
    def parse_game_stats_df(org_id, game_id):
        def team_stats_row(t):
            t['statistics']['entityId'] = t['entityId']
            return t['statistics']
        team_stats_list = [team_stats_row(t) for t in Communicator.get_game_team_stats_synergy(org_id, game_id)['data']]
        team_stats_df = pd.DataFrame(team_stats_list)

        def player_stats_row(p):
            p['statistics']['entityId'] = p['entityId']
            p['statistics']['personId'] = p['personId']
            p['statistics']['starter'] = p['starter']
            return p['statistics']
        player_stats_list = [player_stats_row(p) for p in Communicator.get_game_player_stats_synergy(org_id, game_id)['data'] if p['participated']]
        player_stats_df = pd.DataFrame(player_stats_list)

        team_id_list = team_stats_df['entityId'].to_list()
        starter_dict = {team_id: {p['personId'] for p in player_stats_list if p['starter'] and p['entityId'] == team_id}
                for team_id in team_id_list}

        return team_stats_df, player_stats_df, starter_dict

    @staticmethod
    def parse_id_tables(org_id):
        persons_json_list = Communicator.get_org_persons_synergy(org_id)['data']
        id_table = {p['personId']: p['nameFullLocal'] for p in persons_json_list}

        entities_json_list = Communicator.get_org_entities_synergy(org_id)['data']
        id_table.update({t['entityId']: t['nameFullLocal'] for t in entities_json_list})

        venues_json_list = Communicator.get_org_venues_synergy(org_id)['data']
        id_table.update({t['venueId']: t['nameLocal'] for t in venues_json_list})
        
        return id_table
