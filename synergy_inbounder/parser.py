# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import numpy as np
import json

from synergy_inbounder.communicator import Communicator
from synergy_inbounder.runtime_cache import get_cached_id_table, get_cached_season_df

class Parser:
    @staticmethod
    def parse_season_game_list_df(org_id, season_id):
        return get_cached_season_df(org_id, season_id, lambda: Parser._load_season_game_list_df(org_id, season_id))

    @staticmethod
    def _load_season_game_list_df(org_id, season_id):
        season_game_list = Communicator.get_season_game_list(org_id, season_id)['data']
        df = pd.DataFrame(season_game_list)

        df[['teamAId', 'teamAIsHome', 'teamAScore']] = df['competitors'].apply(pd.Series)[0].apply(pd.Series)[['entityId', 'isHome', 'score']]
        df[['teamBId', 'teamBIsHome', 'teamBScore']] = df['competitors'].apply(pd.Series)[1].apply(pd.Series)[['entityId', 'isHome', 'score']]

        df['teamIdHome'] = df.apply(lambda x: x['teamAId'] if x['teamAIsHome'] else x['teamBId'], axis=1)
        df['teamScoreHome'] = df.apply(lambda x: x['teamAScore'] if x['teamAIsHome'] else x['teamBScore'], axis=1)
        df['teamIdAway'] = df.apply(lambda x: x['teamAId'] if not x['teamAIsHome'] else x['teamBId'], axis=1)
        df['teamScoreAway'] = df.apply(lambda x: x['teamAScore'] if not x['teamAIsHome'] else x['teamBScore'], axis=1)

        return df[['startTimeLocal', 'fixtureId', 'fixtureType', 'venueId', 'status', 'teamIdHome', 'teamScoreHome', 'teamIdAway', 'teamScoreAway']]

    @staticmethod
    def parse_game_pbp_df(org_id, game_id):
        return Parser._pbp_df_from_json(Communicator.get_game_play_by_play_synergy(org_id, game_id))

    @staticmethod
    def parse_game_stats_df(org_id, game_id):
        return Parser._stats_from_json(
            Communicator.get_game_team_stats_synergy(org_id, game_id),
            Communicator.get_game_team_stats_periods_synergy(org_id, game_id),
            Communicator.get_game_player_stats_synergy(org_id, game_id),
        )

    @staticmethod
    def _pbp_df_from_json(pbp_json):
        df = pd.DataFrame(pbp_json.get('data') or [])
        for col in ['entityId', 'personId', 'eventType', 'subType', 'timestamp',
                    'sequence', 'periodId', 'clock', 'success', 'options', 'scores']:
            if col not in df.columns:
                df[col] = np.nan
        df['options'] = df['options'].apply(lambda x: json.dumps(x) if pd.notna(x) else np.nan)
        df['scores'] = df['scores'].apply(lambda x: json.dumps(x) if pd.notna(x) else np.nan)
        return df

    @staticmethod
    def _stats_from_json(team_json, periods_json, player_json):
        def team_stats_row(t):
            t['statistics']['entityId'] = t['entityId']
            return t['statistics']
        team_stats_df = pd.DataFrame([team_stats_row(t) for t in team_json.get('data') or []])

        def team_stats_periods_row(t):
            t['statistics']['entityId'] = t['entityId']
            t['statistics']['periodId'] = t['periodId']
            return t['statistics']
        team_stats_periods_df = pd.DataFrame([team_stats_periods_row(t) for t in periods_json.get('data') or []])

        def player_stats_row(p):
            p['statistics']['entityId'] = p['entityId']
            p['statistics']['personId'] = p['personId']
            p['statistics']['starter'] = p['starter']
            return p['statistics']
        player_stats_list = [player_stats_row(p) for p in (player_json.get('data') or []) if p['participated']]
        player_stats_df = pd.DataFrame(player_stats_list)

        team_id_list = team_stats_df['entityId'].to_list() if not team_stats_df.empty else []
        starter_dict = {team_id: [p['personId'] for p in player_stats_list if p['starter'] and p['entityId'] == team_id]
                for team_id in team_id_list}

        return team_stats_df, team_stats_periods_df, player_stats_df, starter_dict

    @staticmethod
    def parse_game_bundle(org_id, game_id):
        with ThreadPoolExecutor(max_workers=5) as pool:
            f_team = pool.submit(Communicator.get_game_team_stats_synergy, org_id, game_id)
            f_periods = pool.submit(Communicator.get_game_team_stats_periods_synergy, org_id, game_id)
            f_player = pool.submit(Communicator.get_game_player_stats_synergy, org_id, game_id)
            f_pbp = pool.submit(Communicator.get_game_play_by_play_synergy, org_id, game_id)
            f_ids = pool.submit(Parser.parse_id_tables, org_id)
            team_json = f_team.result()
            periods_json = f_periods.result()
            player_json = f_player.result()
            pbp_json = f_pbp.result()
            id_table = f_ids.result()

        team_stats_df, team_stats_periods_df, player_stats_df, starter_dict = Parser._stats_from_json(
            team_json, periods_json, player_json)
        playbyplay_df = Parser._pbp_df_from_json(pbp_json)
        return team_stats_df, team_stats_periods_df, player_stats_df, starter_dict, playbyplay_df, id_table

    @staticmethod
    def parse_id_tables(org_id):
        return get_cached_id_table(org_id, lambda: Parser._load_id_tables(org_id))

    @staticmethod
    def _load_id_tables(org_id):
        persons_json_list = Communicator.get_org_persons_synergy(org_id)['data']
        id_table = {p['personId']: p['nameFullLocal'] for p in persons_json_list}

        entities_json_list = Communicator.get_org_entities_synergy(org_id)['data']
        id_table.update({t['entityId']: t['nameFullLocal'] for t in entities_json_list})

        venues_json_list = Communicator.get_org_venues_synergy(org_id)['data']
        id_table.update({t['venueId']: t['nameLocal'] for t in venues_json_list})
        
        return id_table
