# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

import pandas as pd

from domain.lineups import (
    add_buckets,
    empty_side,
    expand_subsets,
    lineup_records,
    matchup_records,
)
from inbound.cache.frame_store import (
    clear_rotation_cache,
    get_lineup_summary,
    set_lineup_summary,
)
from synergy_reporter import team_lineups


def _bucket(ids, seconds, points, possessions=1):
    own = empty_side()
    own['PTS'] = points
    own['POSS'] = possessions
    if points:
        own['2M'] = points // 2
        own['2A'] = points // 2
    return {'ids': tuple(ids), 'duration': seconds, 'own': own, 'opp': empty_side()}


def _five(prefix):
    return tuple('{0}{1}'.format(prefix, index) for index in range(1, 6))


class LineupDomainTests(unittest.TestCase):
    def test_two_games_sum_once_and_recompute_rates(self):
        five = _five('h')
        summed = add_buckets([
            {five: _bucket(five, 60, 2)},
            {five: _bucket(five, 30, 4, possessions=2)},
        ])
        records = lineup_records(expand_subsets(summed, 5), lambda ids: '-'.join(ids))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['Min'], '1:30')
        self.assertEqual(records[0]['PTS'], 6)
        self.assertEqual(records[0]['+/-'], 6)
        self.assertEqual(records[0]['2FG%'], '1.000')
        self.assertEqual(records[0]['PPP'], '2.00')
        self.assertEqual(records[1]['Min'], '')
        self.assertEqual(records[1]['+/-'], '')
        self.assertTrue(records[1]['_opp'])
        self.assertEqual(records[0]['_own']['+/-'], records[1]['_own']['+/-'])

    def test_size_two_adds_a_shared_pair_from_summed_fives(self):
        first = _five('h')
        second = ('h1', 'h2', 'h3', 'h4', 'h6')
        summed = add_buckets([
            {first: _bucket(first, 60, 2), second: _bucket(second, 60, 4)},
        ])
        expanded = expand_subsets(summed, 2)
        shared = expanded[('h1', 'h2')]
        self.assertEqual(shared['duration'], 120)
        self.assertEqual(shared['own']['PTS'], 6)
        self.assertEqual(len(expanded), 14)
        records = lineup_records(expanded, lambda ids: '-'.join(ids))
        self.assertEqual(len(records), 28)

    def test_zero_duration_drops_and_blank_ppp_ranks_after_a_tie(self):
        kept = add_buckets([{
            ('a', 'b'): {'ids': ('a', 'b'), 'duration': 0, 'own': empty_side(), 'opp': empty_side()},
        }])
        self.assertEqual(kept, {})
        blank = _bucket(('c', 'd'), 10, 2, possessions=0)
        scored = _bucket(('e', 'f'), 10, 2, possessions=2)
        records = lineup_records(
            {('e', 'f'): scored, ('c', 'd'): blank},
            lambda ids: '-'.join(ids),
        )
        self.assertEqual(records[0]['Lineup'], 'e-f')
        self.assertEqual(records[0]['PPP'], '1.00')
        self.assertEqual(records[2]['Lineup'], 'c-d')
        self.assertEqual(records[2]['PPP'], '')

    def test_matchup_puts_the_selected_five_on_top(self):
        aces = _five('h')
        bears = _five('b')
        own = empty_side()
        own['PTS'] = 4
        own['POSS'] = 2
        other = empty_side()
        other['PTS'] = 1
        other['POSS'] = 1
        pairs = [
            {
                'home_team': 'bears',
                'away_team': 'aces',
                'home': bears,
                'away': aces,
                'duration': 90,
                'home_stats': other,
                'away_stats': own,
            },
            {
                'home_team': 'bears',
                'away_team': 'aces',
                'home': bears,
                'away': aces,
                'duration': 0,
                'home_stats': other,
                'away_stats': own,
            },
            {
                'home_team': 'cubs',
                'away_team': 'foxes',
                'home': _five('c'),
                'away': _five('f'),
                'duration': 40,
                'home_stats': own,
                'away_stats': other,
            },
        ]
        records = matchup_records(pairs, 'aces', lambda team_id, ids: '-'.join(ids))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['Lineup'], 'h1-h2-h3-h4-h5')
        self.assertEqual(records[0]['Min'], '1:30')
        self.assertEqual(records[0]['+/-'], 3)
        self.assertEqual(records[0]['PPP'], '2.00')
        self.assertEqual(records[1]['Lineup'], 'b1-b2-b3-b4-b5')
        self.assertEqual(records[1]['Min'], '')
        self.assertEqual(records[1]['+/-'], '')
        self.assertTrue(records[1]['_opp'])
        self.assertIn('h1-h2-h3-h4-h5', records[0]['_filter'])
        self.assertIn('b1-b2-b3-b4-b5', records[0]['_filter'])


class SeasonLineupTests(unittest.TestCase):
    def tearDown(self):
        clear_rotation_cache()

    def test_clear_rotation_cache_drops_the_lineup_summary(self):
        set_lineup_summary('org', 'fix', 7, {'fives': {}, 'pairs': []})
        self.assertEqual(get_lineup_summary('org', 'fix', 7)['pairs'], [])
        clear_rotation_cache()
        self.assertIsNone(get_lineup_summary('org', 'fix', 7))

    def test_a_raised_walk_is_not_cached(self):
        frame = pd.DataFrame([{'periodId': 1}])
        game = {'fixture_id': 'g', 'home': 'home', 'away': 'away', 'pbp': frame}
        with patch.object(team_lineups, '_starters_for', return_value={'home': ['h'], 'away': ['a']}):
            self.assertIsNone(team_lineups.summary_for('org', game))
        self.assertIsNone(get_lineup_summary('org', 'g', id(frame)))

    def test_non_five_stints_are_omitted_and_an_empty_walk_is_cached(self):
        frame = pd.DataFrame([
            {
                'periodId': 1, 'clock': 'PT10M00S', 'eventType': '2pt',
                'entityId': 'home', 'personId': 'h1', 'subType': 'jump',
                'success': 1, 'options': None,
            },
            {
                'periodId': 1, 'clock': 'PT09M00S', 'eventType': 'period',
                'entityId': None, 'personId': None, 'subType': 'end',
                'success': 0, 'options': None,
            },
        ])
        game = {'fixture_id': 'g', 'home': 'home', 'away': 'away', 'pbp': frame}
        starters = {
            'home': ['h1', 'h2', 'h3', 'h4'],
            'away': ['a1', 'a2', 'a3', 'a4'],
        }
        with patch.object(team_lineups, '_starters_for', return_value=starters):
            built = team_lineups.summary_for('org', game)
        self.assertEqual(built['fives'], {})
        self.assertEqual(built['pairs'], [])
        self.assertIs(get_lineup_summary('org', 'g', id(frame)), built)

    def test_a_five_keeps_points_and_the_same_frame_is_not_walked_again(self):
        frame = pd.DataFrame([
            {
                'periodId': 1, 'clock': 'PT10M00S', 'eventType': '2pt',
                'entityId': 'home', 'personId': 'h1', 'subType': 'jump',
                'success': 1, 'options': {'pointsInThePaint': True},
            },
            {
                'periodId': 1, 'clock': 'PT09M00S', 'eventType': 'period',
                'entityId': None, 'personId': None, 'subType': 'end',
                'success': 0, 'options': None,
            },
        ])
        game = {'fixture_id': 'g', 'home': 'home', 'away': 'away', 'pbp': frame}
        starters = {'home': list(_five('h')), 'away': list(_five('a'))}
        with patch.object(team_lineups, '_starters_for', return_value=starters) as seeded:
            first = team_lineups.summary_for('org', game)
            second = team_lineups.summary_for('org', game)
        self.assertIs(first, second)
        self.assertEqual(seeded.call_count, 1)
        home = first['fives']['home'][_five('h')]
        self.assertEqual(home['duration'], 60)
        self.assertEqual(home['own']['PTS'], 2)
        self.assertEqual(home['own']['2M'], 1)
        self.assertEqual(len(first['pairs']), 1)
        self.assertEqual(first['pairs'][0]['home'], _five('h'))
        self.assertEqual(first['pairs'][0]['duration'], 60)

    def test_names_see_the_bench_twin_before_the_first_label(self):
        five = _five('h')
        summary = {
            'fives': {'aces': {five: _bucket(five, 60, 2)}},
            'pairs': [],
        }
        source = {
            'org_id': 'o',
            'team': 'aces',
            'games': [{'fixture_id': 'g1'}],
            'id_table': {
                'h1': 'Lin', 'h2': 'Wu', 'h3': 'Ho', 'h4': 'Kuo', 'h5': 'Yeh', 'h6': 'Lin',
            },
        }
        shirts = {'h1': 7, 'h2': 1, 'h3': 4, 'h4': 11, 'h5': 3, 'h6': 20}
        with patch.object(team_lineups, '_prepare', return_value=[summary]), \
                patch.object(
                    team_lineups, 'get_fixture_facts',
                    return_value=[{'entityId': 'aces', 'personId': 'h6'}],
                ), \
                patch.object(team_lineups, 'get_team_shirts', return_value=shirts):
            records = team_lineups.season_lineup_records(source, 5)
        self.assertEqual(records[0]['Lineup'], 'Wu-Yeh-Ho-Lin#7-Kuo')
