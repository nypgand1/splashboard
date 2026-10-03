# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

import pandas as pd

import app  # noqa: F401
from easl_inbounder.parser import TEAM_TBD, matches_to_frame
from easl_inbounder.settings import EASL_SEASON_ID, EASL_SEASONS
from pages import home as home_page
from synergy_inbounder.parser import Parser
from synergy_inbounder.settings import SYNERGY_SEASON_ID, SYNERGY_SEASONS


FINISHED_MATCH = {
    'fixtureId': '10af8fd4-106e-11f1-960b-5798087c7aa3',
    'fixtureType': 'FINAL',
    'status': 'CONFIRMED',
    'startTimeLocal': '2026-03-22T18:00:00',
    'venue': {'nameLocal': 'Studio City Event Center'},
    'competitors': [
        {
            'isHome': False,
            'score': '90',
            'nameFullLocal': 'Utsunomiya Brex',
            'nameFullLatin': '宇都宮ブレックス',
        },
        {
            'isHome': True,
            'score': '81',
            'nameFullLocal': 'Taoyuan Pauian Pilots',
        },
    ],
}

DRAFT_MATCH = {
    'fixtureId': 'cc824b99-b040-11f1-af4b-e3512c1cd523',
    'fixtureType': None,
    'status': 'DRAFT',
    'startTimeLocal': '2027-03-09T00:00:00',
    'venue': None,
    'competitors': [],
}


class EaslMatchFrameTests(unittest.TestCase):
    def test_finished_match_uses_local_names_and_home_flag(self):
        frame = matches_to_frame([FINISHED_MATCH])
        row = frame.iloc[0]
        self.assertEqual(row['Home Team'], 'Taoyuan Pauian Pilots')
        self.assertEqual(row['Away Team'], 'Utsunomiya Brex')
        self.assertEqual(row['teamScoreHome'], '81')
        self.assertEqual(row['teamScoreAway'], '90')
        self.assertEqual(row['Venue'], 'Studio City Event Center')
        self.assertEqual(row['fixtureType'], 'FINAL')
        self.assertEqual(row['status'], 'CONFIRMED')

    def test_empty_draft_is_tbd_without_a_venue_or_type(self):
        frame = matches_to_frame([DRAFT_MATCH])
        row = frame.iloc[0]
        self.assertEqual(row['Home Team'], TEAM_TBD)
        self.assertEqual(row['Away Team'], TEAM_TBD)
        self.assertIsNone(row['teamScoreHome'])
        self.assertIsNone(row['teamScoreAway'])
        self.assertEqual(row['Venue'], '')
        self.assertIsNone(row['fixtureType'])
        self.assertEqual(row['status'], 'DRAFT')

    def test_non_list_payload_is_an_error(self):
        with self.assertRaises(ValueError):
            matches_to_frame({'data': []})


class SeasonCatalogTests(unittest.TestCase):
    def test_plg_and_easl_catalogs_match_the_locked_ids(self):
        self.assertEqual(
            [label for label, _season_id in SYNERGY_SEASONS],
            ['2026-27', '2025-26', '2024-25', '2023-24', '2022-23', '2021-22', '2020-21'],
        )
        self.assertEqual(
            [season_id for _label, season_id in SYNERGY_SEASONS],
            [
                '94b08c7c-bb00-11f1-ba8e-bd03fe15a10b',
                '00ab711f-938c-11f0-91bb-4b1b779ef3d9',
                'ab495b22-7563-11ef-9992-67cb519a6043',
                'e54380a8-4318-11ee-aac9-833b08b75024',
                'e279bdcf-3e5b-11ed-83e3-977d7240edca',
                'b84d0073-3d8e-11ed-bbf9-2d934c23ac1b',
                'b6d36761-3d8e-11ed-a1f2-d5490a4ddc81',
            ],
        )
        self.assertEqual(SYNERGY_SEASON_ID, '00ab711f-938c-11f0-91bb-4b1b779ef3d9')
        self.assertEqual(
            [label for label, _season_id in EASL_SEASONS],
            ['2026-27', '2025-26', '2024-25', '2023-24'],
        )
        self.assertEqual(EASL_SEASON_ID, '1409787d-a683-11f1-aea7-b596f55be5ed')
        self.assertEqual(
            dict(EASL_SEASONS)['2025-26'],
            '77441bb3-9759-11f0-b659-0561c09a0222',
        )
        self.assertEqual(
            dict(EASL_SEASONS)['2024-25'],
            '57cefc32-5ace-11ef-81a0-3d1f6018efb7',
        )
        self.assertEqual(
            dict(EASL_SEASONS)['2023-24'],
            'c24ce68a-6420-11ee-9daf-6b6188281bd0',
        )


class HomeLeagueScheduleTests(unittest.TestCase):
    def _filters(self):
        return home_page.initial_home_filters()

    def test_switching_league_remembers_each_season_and_clears_game_type(self):
        stored = self._filters()
        stored['show'] = 'finished'
        stored['game_type'] = 'PLAYOFF'
        stored['seasons']['PLG'] = dict(SYNERGY_SEASONS)['2024-25']
        plg_season_control = stored['seasons']['PLG']

        data, scope = home_page.apply_home_filters(
            'finished', 'PLAYOFF', 'EASL', plg_season_control, stored, 'home-league',
        )
        self.assertEqual(data['show'], 'finished')
        self.assertIsNone(data['game_type'])
        self.assertEqual(data['league'], 'EASL')
        self.assertEqual(data['seasons']['PLG'], dict(SYNERGY_SEASONS)['2024-25'])
        self.assertEqual(scope, {'league': 'EASL', 'season_id': EASL_SEASON_ID})

        data, scope = home_page.apply_home_filters(
            'finished', None, 'EASL', dict(EASL_SEASONS)['2025-26'], data, 'home-season',
        )
        self.assertEqual(data['seasons']['EASL'], dict(EASL_SEASONS)['2025-26'])
        self.assertEqual(scope['season_id'], dict(EASL_SEASONS)['2025-26'])

        data, scope = home_page.apply_home_filters(
            'finished', None, 'PLG', dict(EASL_SEASONS)['2025-26'], data, 'home-league',
        )
        self.assertEqual(scope, {
            'league': 'PLG',
            'season_id': dict(SYNERGY_SEASONS)['2024-25'],
        })

    def test_easl_confirmed_row_shows_the_score_and_is_not_a_link(self):
        records = home_page.schedule_records(
            home_page._decorate_schedule(matches_to_frame([FINISHED_MATCH, DRAFT_MATCH])),
            league='EASL',
        )
        confirmed = next(row for row in records if row['status'] == 'CONFIRMED')
        draft = next(row for row in records if row['status'] == 'DRAFT')
        self.assertEqual(confirmed['score'], '90 : 81')
        self.assertFalse(confirmed['scoreClickable'])
        self.assertEqual(draft['score'], '@')
        self.assertEqual(draft['homeTeam'], TEAM_TBD)
        self.assertEqual(draft['venue'], '')
        tree = home_page.render_home_page(
            records,
            show='all',
            game_type=None,
            league='EASL',
            season_id=EASL_SEASON_ID,
        )
        from tests.test_dmc_ui import _anchors, _node_id, walk
        hrefs = [node.href for node in _anchors(tree)]
        self.assertFalse(any('/game/' in href for href in hrefs))
        self.assertIn('TBD', str(tree))
        self.assertIn('DRAFT', str(tree))
        season = next(node for node in walk(tree) if _node_id(node) == 'home-season')
        self.assertEqual(season.value, EASL_SEASON_ID)
        self.assertEqual(
            [item['label'] for item in season.data],
            ['2026-27', '2025-26', '2024-25', '2023-24'],
        )
        league = next(node for node in walk(tree) if _node_id(node) == 'home-league')
        self.assertEqual(league.value, 'EASL')

    def test_easl_load_does_not_prefetch_synergy_reports(self):
        frame = matches_to_frame([FINISHED_MATCH])
        with patch('easl_inbounder.parser.Parser.parse_season_game_list_df', return_value=frame), \
                patch('synergy_inbounder.runtime_cache.prefetch_latest_games') as prefetch:
            loaded = home_page.df_data(
                prefetch=True,
                league='EASL',
                season_id=dict(EASL_SEASONS)['2025-26'],
            )
        prefetch.assert_not_called()
        self.assertEqual(loaded.iloc[0]['Home Team'], 'Taoyuan Pauian Pilots')

    def test_scope_change_requests_that_league_and_clears_game_type(self):
        seen = {}

        def _df(prefetch=True, league='PLG', season_id=None):
            seen['prefetch'] = prefetch
            seen['league'] = league
            seen['season_id'] = season_id
            return matches_to_frame([FINISHED_MATCH, DRAFT_MATCH])

        with patch.object(home_page, 'df_data', side_effect=_df), \
                patch.object(home_page, '_triggered_id', return_value='home-scope-store'):
            tree = home_page.load_home_game_list(
                3,
                {'league': 'EASL', 'season_id': dict(EASL_SEASONS)['2025-26']},
                {'show': 'all', 'game_type': 'REGULAR', 'league': 'PLG'},
            )
        self.assertEqual(seen['league'], 'EASL')
        self.assertEqual(seen['season_id'], dict(EASL_SEASONS)['2025-26'])
        self.assertFalse(seen['prefetch'])
        markup = str(tree)
        self.assertIn('Utsunomiya Brex', markup)
        self.assertIn(TEAM_TBD, markup)


class PlgGameLookupTests(unittest.TestCase):
    def test_find_game_row_checks_the_later_season(self):
        frames = {
            'season-a': pd.DataFrame([{'fixtureId': 'other', 'status': 'CONFIRMED'}]),
            'season-b': pd.DataFrame([{'fixtureId': 'wanted', 'status': 'IN_PROGRESS'}]),
        }

        def _frame(_org, season_id):
            return frames[season_id]

        with patch.object(Parser, 'parse_season_game_list_df', side_effect=_frame):
            row = Parser.find_game_row('b1vqz', 'wanted', ['season-a', 'season-b'])
        self.assertEqual(row['status'], 'IN_PROGRESS')

    def test_lookup_game_status_tries_the_default_season_first(self):
        from synergy_inbounder.runtime_cache import lookup_game_status

        calls = []
        later_id = SYNERGY_SEASONS[0][1]

        def _frame(_org, season_id):
            calls.append(season_id)
            if season_id == later_id:
                return pd.DataFrame([{'fixtureId': 'later', 'status': 'DRAFT'}])
            return pd.DataFrame([{'fixtureId': 'nope', 'status': 'CONFIRMED'}])

        with patch.object(Parser, 'parse_season_game_list_df', side_effect=_frame):
            status = lookup_game_status('later')
        self.assertEqual(status, 'DRAFT')
        self.assertEqual(calls[0], SYNERGY_SEASON_ID)
        self.assertIn(later_id, calls)
