# -*- coding: utf-8 -*-

import pandas as pd
from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import update_lineup_pbp

class PostGameReport():
    def __init__(self, game_id):
        #TODO get period_id_list
        period_id_list = [1, 2, 3, 4]
        
        org_id = SYNERGY_ORGANIZATION_ID
        self.id_table = Parser.parse_id_tables(org_id)
        self.team_stats_df, self.player_stats_df, self.starter_dict = Parser.parse_game_stats_df(org_id, game_id)
        
        self.pbp_df = Parser.parse_game_pbp_df(org_id, game_id, period_id_list)
        update_lineup_pbp(self.pbp_df, self.starter_dict, self.id_table)

        self.sub_df = self.pbp_df[self.pbp_df['eventType'].isin(['substitution', 'period'])]
        self.shot_df = self.pbp_df[self.pbp_df['eventType'].isin(['2pt', '3pt', 'freeThrow'])]

def main():
    game_id = raw_input('Game Id? ')
    r = PostGameReport(str(game_id))

if __name__ == '__main__':
    main()
