# -*- coding: utf-8 -*-
import pandas as pd

from synergy_inbounder.communicator import Communicator

class Parser:
    @staticmethod
    def parse_game_pbp_df(org_id, game_id, period_id_list):
        pbp_json_list = [Communicator.get_game_play_by_play_synergy(org_id, game_id, p)['data'] for p in period_id_list]
        df = pd.DataFrame(sum(pbp_json_list, []))

        return df

    @staticmethod
    def parse_game_stats_df(org_id, game_id):
        #TODO get team stats
        
        player_stats_list = [p for p in Communicator.get_game_player_stats_synergy(org_id, game_id)['data'] if p['participated']]
        player_stats_df = pd.DataFrame(player_stats_list)
        
        #TODO parse player stats
        for p in player_stats_list:
            print p['statistics']['minutes']

        team_id_set = {p['entityId'] for p in player_stats_list}
        starter_dict = {team_id: {p['personId'] for p in player_stats_list if p['starter'] and p['entityId'] == team_id}
                for team_id in team_id_set}

        return player_stats_df, starter_dict

    @staticmethod
    def parse_id_tables(org_id):
        persons_json_list = Communicator.get_org_persons_synergy(org_id)['data']
        id_table = {p['personId']: p['nameFullLocal'] for p in persons_json_list}

        entities_json_list = Communicator.get_org_entities_synergy(org_id)['data']
        id_table.update({t['entityId']: t['nameFullLocal'] for t in entities_json_list})

        return id_table
