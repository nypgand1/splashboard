import unittest
from unittest.mock import patch

import pandas as pd

from synergy_inbounder.parser import Parser


def _empty_stats():
    return {'data': []}


def _team_stats():
    return {'data': [{'entityId': 'home', 'statistics': {'points': 0}}]}


def _player_stats():
    return {'data': [{
        'personId': 'p1',
        'entityId': 'home',
        'starter': False,
        'participated': True,
        'shirtNumber': '99',
        'statistics': {'points': 0},
    }]}


def _player_periods():
    return {'data': [{
        'entityId': 'home',
        'personId': 'p1',
        'periodId': 1,
        'statistics': {'points': 4},
    }]}


class PbpFrameTests(unittest.TestCase):
    def test_missing_columns_are_filled(self):
        df = Parser._pbp_df_from_json({'data': [{'periodId': 1}]})
        for col in ['entityId', 'personId', 'eventType', 'subType', 'clock', 'scores', 'x', 'y']:
            self.assertIn(col, df.columns)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['periodId'], 1)

    def test_shot_coordinates_are_kept(self):
        df = Parser._pbp_df_from_json({'data': [{
            'eventType': '2pt', 'x': 12.5, 'y': 40, 'periodId': 1,
        }]})
        self.assertEqual(df.iloc[0]['x'], 12.5)
        self.assertEqual(df.iloc[0]['y'], 40)
        self.assertEqual(df.iloc[0]['eventType'], '2pt')

    def test_empty_payload_returns_empty_frame(self):
        df = Parser._pbp_df_from_json({'data': []})
        self.assertTrue(df.empty)
        self.assertIn('clock', df.columns)


class SeasonListTests(unittest.TestCase):
    def test_flattens_home_and_away_competitors(self):
        payload = {'data': [{
            'startTimeLocal': '2026-01-01T19:00:00',
            'fixtureId': 'g1',
            'fixtureType': 'REGULAR',
            'venueId': 'v1',
            'status': 'FINISHED',
            'competitors': [
                {'entityId': 'home', 'isHome': True, 'score': 80},
                {'entityId': 'away', 'isHome': False, 'score': 70},
            ],
        }]}
        with patch(
            'synergy_inbounder.parser.Communicator.get_season_game_list',
            return_value=payload,
        ):
            df = Parser._load_season_game_list_df('org', 'season')
        self.assertEqual(list(df.columns), [
            'startTimeLocal', 'fixtureId', 'fixtureType', 'venueId', 'status',
            'teamIdHome', 'teamScoreHome', 'teamIdAway', 'teamScoreAway',
        ])
        self.assertEqual(df.iloc[0]['teamIdHome'], 'home')
        self.assertEqual(df.iloc[0]['teamScoreHome'], 80)
        self.assertEqual(df.iloc[0]['teamIdAway'], 'away')
        self.assertEqual(df.iloc[0]['teamScoreAway'], 70)


class ParseGameBundleTests(unittest.TestCase):
    def _run_bundle(self, live_flag):
        seen = []

        def record(name, payload):
            def _call(org_id, game_id, live=True, *args, **kwargs):
                seen.append((name, live))
                return payload
            return _call

        def roster(org_id, game_id):
            seen.append(('roster', None))
            return {'data': [{
                'personId': 'p1',
                'entityId': 'home',
                'starter': True,
                'bib': '10',
            }]}

        with patch(
            'synergy_inbounder.parser.should_use_live_endpoints',
            return_value=live_flag,
        ), patch.object(Parser, 'parse_id_tables', return_value={'home': 'Home'}), \
                patch(
                    'synergy_inbounder.parser.Communicator.get_game_team_stats_synergy',
                    side_effect=record('team', _team_stats()),
                ), patch(
                    'synergy_inbounder.parser.Communicator.get_game_team_stats_periods_synergy',
                    side_effect=record('periods', _empty_stats()),
                ), patch(
                    'synergy_inbounder.parser.Communicator.get_game_player_stats_synergy',
                    side_effect=record('player', _player_stats()),
                ), patch(
                    'synergy_inbounder.parser.Communicator.get_game_player_stats_periods_synergy',
                    side_effect=record('player_periods', _player_periods()),
                ), patch(
                    'synergy_inbounder.parser.Communicator.get_game_play_by_play_synergy',
                    side_effect=lambda org, game, period_id=None, live=True: (
                        seen.append(('pbp', live)) or _empty_stats()
                    ),
                ), patch(
                    'synergy_inbounder.parser.Communicator.get_fixture_roster_synergy',
                    side_effect=roster,
                ):
            result = Parser.parse_game_bundle('org', 'game-1')
        return seen, result

    def test_finished_games_request_official_routes(self):
        seen, _result = self._run_bundle(False)
        live_calls = [live for name, live in seen if name != 'roster']
        self.assertTrue(live_calls)
        self.assertTrue(all(live is False for live in live_calls))
        self.assertIn(('roster', None), seen)

    def test_live_games_request_live_routes(self):
        seen, _result = self._run_bundle(True)
        live_calls = [live for name, live in seen if name != 'roster']
        self.assertTrue(all(live is True for live in live_calls))

    def test_fixture_roster_supplies_bib_and_starters(self):
        _seen, result = self._run_bundle(False)
        _team, _periods, _player, starter_dict, pbp_df, id_table, roster, player_periods = result
        self.assertTrue(pbp_df.empty)
        self.assertEqual(id_table['home'], 'Home')
        self.assertEqual(roster[0]['shirtNumber'], '10')
        self.assertTrue(roster[0]['starter'])
        self.assertEqual(starter_dict.get('home'), ['p1'])
        self.assertEqual(int(player_periods.iloc[0]['periodId']), 1)
        self.assertEqual(player_periods.iloc[0]['points'], 4)
