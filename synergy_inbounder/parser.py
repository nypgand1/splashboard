# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import numpy as np
import json

from synergy_inbounder.communicator import Communicator
from synergy_inbounder.settings import LOGGER
from synergy_inbounder.runtime_cache import (
    get_cached_id_table,
    get_cached_season_df,
    should_use_live_endpoints,
)

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
        live = should_use_live_endpoints(game_id=game_id)
        return Parser._pbp_df_from_json(Communicator.get_game_play_by_play_synergy(org_id, game_id, live=live))

    @staticmethod
    def parse_game_stats_df(org_id, game_id):
        live = should_use_live_endpoints(game_id=game_id)
        return Parser._stats_from_json(
            Communicator.get_game_team_stats_synergy(org_id, game_id, live=live),
            Communicator.get_game_team_stats_periods_synergy(org_id, game_id, live=live),
            Communicator.get_game_player_stats_synergy(org_id, game_id, live=live),
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
            stats = dict(p.get('statistics') or {})
            stats['entityId'] = p.get('entityId')
            stats['personId'] = p.get('personId')
            stats['starter'] = bool(p.get('starter'))
            stats['participated'] = bool(p.get('participated'))
            return stats
        player_stats_list = [player_stats_row(p) for p in (player_json.get('data') or [])]
        player_stats_df = pd.DataFrame(player_stats_list)

        team_id_list = team_stats_df['entityId'].to_list() if not team_stats_df.empty else []
        starter_dict = {team_id: [p['personId'] for p in player_stats_list if p.get('starter') and p.get('entityId') == team_id]
                for team_id in team_id_list}

        return team_stats_df, team_stats_periods_df, player_stats_df, starter_dict

    @staticmethod
    def _shirt_number(person):
        nested = person.get('person') if isinstance(person.get('person'), dict) else {}
        stats = person.get('statistics') or {}
        for key in ('bib', 'shirtNumber', 'jerseyNumber', 'number'):
            for source in (person, nested, stats):
                value = source.get(key) if isinstance(source, dict) else None
                if value not in (None, ''):
                    return str(value)
        return None

    @staticmethod
    def _roster_from_json(player_json):
        roster = []
        for person in player_json.get('data') or []:
            if not person.get('personId'):
                continue
            roster.append({
                'personId': person.get('personId'),
                'entityId': person.get('entityId'),
                'starter': bool(person.get('starter')),
                'participated': bool(person.get('participated')),
                'shirtNumber': Parser._shirt_number(person),
            })
        return roster

    @staticmethod
    def _roster_from_fixture_json(roster_json):
        roster = []
        for person in roster_json.get('data') or []:
            person_id = person.get('personId')
            if not person_id and isinstance(person.get('person'), dict):
                person_id = person['person'].get('personId')
            if not person_id:
                continue
            entity_id = person.get('entityId')
            if not entity_id and isinstance(person.get('entity'), dict):
                entity_id = person['entity'].get('entityId')
            roster.append({
                'personId': person_id,
                'entityId': entity_id,
                'starter': bool(person.get('starter')),
                'participated': True,
                'shirtNumber': Parser._shirt_number(person),
            })
        return roster

    @staticmethod
    def _merge_roster(fixture_roster, stats_roster):
        if not fixture_roster:
            return stats_roster
        by_id = {row['personId']: row for row in stats_roster}
        merged = []
        seen = set()
        for row in fixture_roster:
            person_id = row['personId']
            seen.add(person_id)
            extra = by_id.get(person_id, {})
            merged.append({
                'personId': person_id,
                'entityId': row.get('entityId') or extra.get('entityId'),
                'starter': bool(row.get('starter') or extra.get('starter')),
                'participated': extra.get('participated', True),
                'shirtNumber': row.get('shirtNumber') or extra.get('shirtNumber'),
            })
        for person_id, extra in by_id.items():
            if person_id not in seen:
                merged.append(extra)
        return merged

    @staticmethod
    def parse_game_bundle(org_id, game_id):
        live = should_use_live_endpoints(game_id=game_id)
        with ThreadPoolExecutor(max_workers=7) as pool:
            f_team = pool.submit(Communicator.get_game_team_stats_synergy, org_id, game_id, live)
            f_periods = pool.submit(Communicator.get_game_team_stats_periods_synergy, org_id, game_id, live)
            f_player = pool.submit(Communicator.get_game_player_stats_synergy, org_id, game_id, live)
            f_player_periods = pool.submit(Parser._load_player_periods, org_id, game_id, live)
            f_pbp = pool.submit(Communicator.get_game_play_by_play_synergy, org_id, game_id, None, live)
            f_roster = pool.submit(Communicator.get_fixture_roster_synergy, org_id, game_id)
            f_ids = pool.submit(Parser.parse_id_tables, org_id)
            team_json = f_team.result()
            periods_json = f_periods.result()
            player_json = f_player.result()
            player_periods_json = f_player_periods.result()
            pbp_json = f_pbp.result()
            try:
                roster_json = f_roster.result()
            except Exception:
                roster_json = {'data': []}
            id_table = f_ids.result()

        team_stats_df, team_stats_periods_df, player_stats_df, starter_dict = Parser._stats_from_json(
            team_json, periods_json, player_json)
        playbyplay_df = Parser._pbp_df_from_json(pbp_json)
        roster = Parser._merge_roster(
            Parser._roster_from_fixture_json(roster_json),
            Parser._roster_from_json(player_json),
        )
        if roster:
            team_ids = team_stats_df['entityId'].to_list() if not team_stats_df.empty else []
            roster_starters = {
                team_id: [row['personId'] for row in roster if row.get('starter') and row.get('entityId') == team_id]
                for team_id in team_ids
            }
            if any(roster_starters.values()):
                starter_dict = roster_starters
        player_periods_df = Parser._player_periods_from_json(player_periods_json)
        return (
            team_stats_df, team_stats_periods_df, player_stats_df, starter_dict,
            playbyplay_df, id_table, roster, player_periods_df,
        )

    @staticmethod
    def _load_player_periods(org_id, game_id, live):
        try:
            return Communicator.get_game_player_stats_periods_synergy(org_id, game_id, live)
        except Exception:
            LOGGER.warning('player period stats unavailable')
            return {'data': []}

    @staticmethod
    def _player_periods_from_json(payload):
        rows = []
        for item in (payload or {}).get('data') or []:
            stats = dict(item.get('statistics') or {})
            stats['entityId'] = item.get('entityId')
            stats['personId'] = item.get('personId')
            stats['periodId'] = item.get('periodId')
            rows.append(stats)
        return pd.DataFrame(rows)

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
