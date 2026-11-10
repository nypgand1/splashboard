# -*- coding: utf-8 -*-
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

from synergy_inbounder.frame_store import (
    clear as clear_frames,
    peek,
    piece_fresh,
    pin_home,
    pin_open,
    pin_season,
    singleflight,
    store,
)
from synergy_inbounder.game_status import FINISHED_STATUSES
from synergy_inbounder.http_wave import run_wave
from synergy_inbounder.live_budget import LONG_CACHE_SECONDS, SHORT_CACHE_SECONDS
from synergy_inbounder.runtime_cache import (
    cached_fixture_status,
    cached_regulation_minutes,
    clear_runtime_caches,
    get_cached_season_df,
)
from synergy_inbounder.settings import (
    EASL_SEASONS,
    SYNERGY_EASL_ORGANIZATION_ID,
    SYNERGY_ORGANIZATION_ID,
    SYNERGY_SEASONS,
    regulation_minutes,
    selectable_seasons,
)
from synergy_reporter.post_game_report import PostGameReport
from synergy_reporter.team_season import (
    EMPTY_TEAM_STATS,
    EMPTY_TEAM_STATS_NEXT,
    _paint_pair,
    build_team_cards,
    choose_game_type,
    _finished_rows,
    fixture_type_options,
    period_chips_for_ids,
    plain_fixture_type,
    schedule_chrome,
    team_stats_payload,
    type_needs_download,
)
from ui_kit import ERROR_GAME


def _fixture(fixture_id, fixture_type, status, **extra):
    row = {
        'fixtureId': fixture_id,
        'fixtureType': fixture_type,
        'status': status,
        'startTimeLocal': extra.pop('startTimeLocal', '2026-01-01T12:00:00'),
    }
    row.update(extra)
    return row


def _total(fixture_id, entity_id, **stats):
    row = {
        'fixtureId': fixture_id,
        'entityId': entity_id,
        'minutes': 'PT10M',
        'points': 0,
        'pointsTwoMade': 0,
        'pointsTwoAttempted': 0,
        'pointsThreeMade': 0,
        'pointsThreeAttempted': 0,
        'freeThrowsMade': 0,
        'freeThrowsAttempted': 0,
        'reboundsOffensive': 0,
        'reboundsDefensive': 0,
        'rebounds': 0,
        'reboundsDefensiveAgainst': 0,
        'assists': 0,
        'turnovers': 0,
        'steals': 0,
        'blocks': 0,
        'foulsTotal': 0,
        'foulsDrawn': 0,
        'pointsInThePaintMade': 0,
        'pointsInThePaintAttempted': 0,
        'pointsInThePaint': 0,
        'pointsSecondChance': 0,
        'pointsFastBreak': 0,
        'pointsFromTurnover': 0,
        'pointsFromBench': 0,
        'fieldGoalsAttempted': 0,
        'fieldGoalsMade': 0,
    }
    row.update(stats)
    return row


def _period(fixture_id, entity_id, period_id, **stats):
    row = _total(fixture_id, entity_id, **stats)
    row['periodId'] = period_id
    return row


def _text(cards, card, team, column):
    for row in cards[card]['rows']:
        if row['Team']['text'] == team:
            return row[column]['text']
    raise AssertionError('{0} {1}'.format(card, team))


def _winner(cards, card, team, column):
    for row in cards[card]['rows']:
        if row['Team']['text'] == team:
            return row[column]['winner']
    raise AssertionError(team)


def _opp_cell(cards, card, index, column):
    return cards[card]['opp_rows'][index][column]


def _opp_text(cards, card, index, column):
    return _opp_cell(cards, card, index, column)['text']


def _opp_best(cards, card, index, column):
    return _opp_cell(cards, card, index, column)['opp_best']


class RegulationMinuteTests(unittest.TestCase):
    def test_minutes_follow_the_season_id(self):
        for _label, season_id in SYNERGY_SEASONS:
            self.assertEqual(regulation_minutes(season_id), 48)
        for _label, season_id in EASL_SEASONS:
            self.assertEqual(regulation_minutes(season_id), 40)
        self.assertIsNone(regulation_minutes('missing-season'))
        self.assertEqual(selectable_seasons('PLG')[0][0], '2026-27')
        self.assertEqual(selectable_seasons('easl')[0][0], '2026-27')

    def test_cached_season_row_supplies_minutes_and_status(self):
        clear_runtime_caches()
        season_id = dict(EASL_SEASONS)['2025-26']
        frame = pd.DataFrame([{'fixtureId': 'g-easl', 'status': 'CONFIRMED'}])
        get_cached_season_df(SYNERGY_EASL_ORGANIZATION_ID, season_id, lambda: frame)
        self.assertEqual(
            cached_regulation_minutes(SYNERGY_EASL_ORGANIZATION_ID, 'g-easl'),
            40,
        )
        self.assertEqual(
            cached_fixture_status(SYNERGY_EASL_ORGANIZATION_ID, 'g-easl'),
            'CONFIRMED',
        )
        self.assertEqual(cached_regulation_minutes(SYNERGY_ORGANIZATION_ID, 'missing'), 48)
        clear_runtime_caches()


class GameTypeTests(unittest.TestCase):
    def test_options_skip_blanks_and_prefer_regular(self):
        missing = float('nan')
        self.assertEqual(plain_fixture_type(missing), '')
        self.assertEqual(plain_fixture_type('NaN'), '')
        self.assertEqual(plain_fixture_type(' REGULAR '), 'REGULAR')
        options = fixture_type_options([
            {'fixtureType': 'PLAYOFF'},
            {'fixtureType': ''},
            {'fixtureType': 'REGULAR'},
            {'fixtureType': 'PLAYOFF'},
            {'fixtureType': None},
            {'fixtureType': missing},
            {'fixtureType': 'nan'},
            {'fixtureType': 1},
        ])
        self.assertEqual(
            [item['value'] for item in options],
            ['PLAYOFF', 'REGULAR'],
        )
        self.assertEqual(
            _finished_rows(
                [
                    {'fixtureId': 'g1', 'fixtureType': 'REGULAR', 'status': 'CONFIRMED'},
                    {'fixtureId': 'g-missing', 'fixtureType': missing, 'status': 'CONFIRMED'},
                ],
                'REGULAR',
            ),
            [{'fixtureId': 'g1', 'fixtureType': 'REGULAR', 'status': 'CONFIRMED'}],
        )
        self.assertEqual(options[0]['label'], 'Playoff')
        self.assertEqual(choose_game_type(options, None), 'REGULAR')
        self.assertEqual(choose_game_type(options, 'PLAYOFF'), 'PLAYOFF')
        self.assertEqual(choose_game_type(options[:1], 'REGULAR'), 'PLAYOFF')


class TeamCardTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = [
            _fixture('g1', 'REGULAR', 'CONFIRMED'),
            _fixture('g2', 'REGULAR', 'FINISHED'),
            _fixture('g3', 'REGULAR', 'SCHEDULED'),
            _fixture('g4', 'PLAYOFF', 'CONFIRMED'),
            _fixture('g5', 'REGULAR', 'IF_NEEDED'),
            _fixture('g6', '', 'CONFIRMED'),
        ]
        self.totals = pd.DataFrame([
            _total('g1', 'a', points=30, pointsTwoMade=9, pointsTwoAttempted=10, minutes='PT10M',
                   turnovers=2, foulsTotal=4, fieldGoalsAttempted=10, pointsThreeAttempted=4,
                   pointsSecondChance=5),
            _total('g1', 'b', points=10, pointsTwoMade=0, pointsTwoAttempted=100, minutes='PT10M',
                   turnovers=8, foulsTotal=1, fieldGoalsAttempted=100, pointsThreeAttempted=1),
            _total('g2', 'a', points=0, pointsTwoMade=1, pointsTwoAttempted=1, minutes='PT10M',
                   turnovers=0, foulsTotal=0, fieldGoalsAttempted=1),
            _total('g2', 'tbd', points=99, minutes='PT10M'),
            _total('g3', 'a', points=1000, minutes='PT10M'),
            _total('g4', 'a', points=7, minutes='PT10M'),
            _total('g5', 'a', points=8, minutes='PT10M'),
        ])
        self.periods = pd.DataFrame([
            _period('g1', 'a', 1, points=8, minutes='PT6M', pointsTwoMade=1, pointsTwoAttempted=2),
            _period('g1', 'b', 1, points=4, minutes='PT6M'),
            _period('g1', 'a', 2, points=6, minutes='PT6M'),
            _period('g1', 'b', 2, points=2, minutes='PT6M'),
            _period('g2', 'a', 1, points=1, minutes='PT6M'),
            _period('g1', 'a', 11, points=3, minutes='PT5M', fieldGoalsAttempted=1),
        ])
        self.names = {'a': 'Aces', 'b': 'Braves', 'tbd': 'TBD'}

    def _cards(self, pbp=None, period='all', game_type='REGULAR', minutes=48):
        return build_team_cards(
            self.fixtures, self.totals, self.periods, pbp or {}, self.names,
            minutes, game_type, period,
        )

    def test_finished_games_only_and_tbd_omitted(self):
        built = self._cards()
        self.assertFalse(built['empty'])
        names = [row['Team']['text'] for row in built['cards']['team']['rows']]
        self.assertEqual(names, ['Aces', 'Braves'])
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'GP'), '2')
        self.assertEqual(_text(built['cards'], 'team', 'Braves', 'GP'), '1')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'PTS'), '15.0')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'Min'), '10:00')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'TO'), '1.0')
        self.assertEqual(_text(built['cards'], 'team', 'Braves', 'TO'), '8.0')
        self.assertTrue(_winner(built['cards'], 'team', 'Aces', 'PTS'))
        self.assertFalse(_winner(built['cards'], 'team', 'Braves', 'PTS'))
        self.assertTrue(_winner(built['cards'], 'team', 'Aces', 'TO'))
        self.assertFalse(_winner(built['cards'], 'team', 'Aces', 'GP'))
        self.assertFalse(_winner(built['cards'], 'team', 'Aces', 'Min'))
        team = built['cards']['team']
        self.assertEqual(len(team['opp_rows']), len(team['rows']))
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Team'), 'Opp')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'GP'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Min'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 1, 'GP'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 1, 'Min'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'PTS'), '54.5')
        self.assertEqual(_opp_text(built['cards'], 'team', 1, 'PTS'), '30.0')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'TO'), '4.0')
        self.assertEqual(_opp_text(built['cards'], 'team', 1, 'TO'), '2.0')
        self.assertTrue(_opp_best(built['cards'], 'team', 0, 'PTS'))
        self.assertFalse(_opp_best(built['cards'], 'team', 1, 'PTS'))
        self.assertFalse(_opp_best(built['cards'], 'team', 0, 'TO'))
        self.assertTrue(_opp_best(built['cards'], 'team', 1, 'TO'))
        self.assertFalse(team['rows'][0]['PTS']['opp_best'])
        self.assertTrue(team['opp_rows'][0]['opp'])
        for key in ('pace', 'advanced', 'key', 'team'):
            card = built['cards'][key]
            self.assertEqual(len(card['opp_rows']), len(card['rows']))
            self.assertEqual(
                [row['Team']['text'] for row in card['opp_rows']],
                ['Opp', 'Opp'],
            )

    def test_shot_percentage_uses_season_makes_over_attempts(self):
        built = self._cards()
        self.assertEqual(_text(built['cards'], 'team', 'Aces', '2FG%'), '.909')
        self.assertEqual(_text(built['cards'], 'team', 'Braves', '2FG%'), '.000')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', '2M'), '5.0')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', '2A'), '5.5')

    def test_all_uses_full_game_totals_not_period_sums(self):
        built = self._cards(period='all')
        quarter = self._cards(period='1')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'PTS'), '15.0')
        self.assertEqual(_text(quarter['cards'], 'team', 'Aces', 'PTS'), '4.5')
        self.assertEqual(_text(quarter['cards'], 'team', 'Aces', 'GP'), '2')
        self.assertEqual(_opp_text(quarter['cards'], 'team', 0, 'PTS'), '2.0')
        self.assertEqual(_opp_text(quarter['cards'], 'team', 0, 'GP'), '')
        self.assertEqual(_opp_text(quarter['cards'], 'team', 1, 'PTS'), '8.0')

    def test_half_recomputes_the_rate_from_both_periods(self):
        built = self._cards(period='h1')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', '2FG%'), '.500')
        self.assertIn({'label': '1H', 'value': 'h1'}, built['period_chips'])
        self.assertIn({'label': 'OT', 'value': '11'}, built['period_chips'])
        self.assertEqual(built['period_chips'][0], {'label': 'All', 'value': 'all'})

    def test_overtime_omits_a_team_that_did_not_play_it(self):
        built = self._cards(period='11')
        names = [row['Team']['text'] for row in built['cards']['team']['rows']]
        self.assertEqual(names, ['Aces'])
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'GP'), '1')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'PTS'), '3.0')
        self.assertFalse(_winner(built['cards'], 'team', 'Aces', 'PTS'))
        self.assertEqual(len(built['cards']['team']['opp_rows']), 1)
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'GP'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Min'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'PTS'), '0.0')
        self.assertFalse(_opp_best(built['cards'], 'team', 0, 'PTS'))

    def test_each_team_keeps_its_own_pace(self):
        pbp = {
            'g1': pd.DataFrame([
                {'eventType': '2pt', 'entityId': 'a', 'success': 1, 'periodId': 1, 'subType': 'jump'},
                {'eventType': '2pt', 'entityId': 'a', 'success': 1, 'periodId': 1, 'subType': 'jump'},
                {'eventType': '2pt', 'entityId': 'b', 'success': 1, 'periodId': 1, 'subType': 'jump'},
                {'eventType': '2pt', 'entityId': 'b', 'success': 1, 'periodId': 1, 'subType': 'jump'},
                {'eventType': '2pt', 'entityId': 'b', 'success': 1, 'periodId': 1, 'subType': 'jump'},
                {'eventType': '2pt', 'entityId': 'b', 'success': 1, 'periodId': 1, 'subType': 'jump'},
            ]),
            'g2': None,
        }
        built = self._cards(pbp=pbp, minutes=48)
        self.assertEqual(_text(built['cards'], 'pace', 'Aces', 'Pace'), '36.0')
        self.assertEqual(_text(built['cards'], 'pace', 'Braves', 'Pace'), '96.0')
        shorter = self._cards(pbp=pbp, minutes=40)
        self.assertEqual(_text(shorter['cards'], 'pace', 'Braves', 'Pace'), '80.0')

    def test_failed_play_by_play_estimates_possessions_and_zero_leaves(self):
        shot = pd.DataFrame([
            {
                'eventType': '2pt', 'entityId': 'a', 'success': 1, 'periodId': 1,
                'subType': 'jump', 'options': {'secondChance': True},
            },
        ])
        built = self._cards(pbp={'g1': None, 'g2': shot})
        self.assertEqual(_text(built['cards'], 'key', 'Aces', 'SCP2M'), '0.5')
        self.assertEqual(_text(built['cards'], 'key', 'Aces', 'SCP'), '2.5')
        self.assertEqual(_text(built['cards'], 'key', 'Braves', 'SCP2M'), '0.0')
        failed = build_team_cards(
            [_fixture('g1', 'REGULAR', 'CONFIRMED')],
            pd.DataFrame([
                _total('g1', 'a', minutes='PT10M', fieldGoalsAttempted=10),
                _total('g1', 'b', minutes='PT10M'),
            ]),
            pd.DataFrame(),
            {'g1': None},
            {'a': 'Aces', 'b': 'Braves'},
            48,
            'REGULAR',
            'all',
        )
        self.assertEqual(_text(failed['cards'], 'pace', 'Aces', 'Pace'), '240.0')
        self.assertEqual(_text(failed['cards'], 'key', 'Aces', 'SCP2M'), '0.0')

    def test_playoff_is_separate_and_three_point_rate_is_not_colored(self):
        built = self._cards(game_type='PLAYOFF')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'GP'), '1')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'PTS'), '7.0')
        self.assertFalse(_winner(built['cards'], 'team', 'Aces', 'PTS'))
        self.assertEqual(len(built['cards']['team']['opp_rows']), 1)
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'GP'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Min'), '')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'PTS'), '0.0')
        self.assertFalse(_opp_best(built['cards'], 'team', 0, 'PTS'))
        regular = self._cards()
        self.assertFalse(_winner(regular['cards'], 'advanced', 'Aces', '3P-R'))
        self.assertFalse(_winner(regular['cards'], 'advanced', 'Braves', '3P-R'))
        self.assertNotEqual(
            _text(regular['cards'], 'advanced', 'Aces', '3P-R'),
            _text(regular['cards'], 'advanced', 'Braves', '3P-R'),
        )

    def test_equal_values_are_not_colored(self):
        totals = pd.DataFrame([
            _total('g1', 'a', points=10, turnovers=3),
            _total('g1', 'b', points=10, turnovers=3),
        ])
        built = build_team_cards(
            [_fixture('g1', 'REGULAR', 'FINISHED')],
            totals, pd.DataFrame(), {}, {'a': 'Aces', 'b': 'Braves'},
            48, 'REGULAR', 'all',
        )
        self.assertFalse(_winner(built['cards'], 'team', 'Aces', 'PTS'))
        self.assertFalse(_winner(built['cards'], 'team', 'Braves', 'TO'))
        self.assertFalse(_opp_best(built['cards'], 'team', 0, 'PTS'))
        self.assertFalse(_opp_best(built['cards'], 'team', 1, 'TO'))

    def test_shared_best_is_colored_and_a_blank_sits_out(self):
        shared = build_team_cards(
            [
                _fixture('g1', 'REGULAR', 'FINISHED'),
                _fixture('g2', 'REGULAR', 'FINISHED'),
            ],
            pd.DataFrame([
                _total('g1', 'a', points=20),
                _total('g1', 'b', points=20),
                _total('g2', 'a', points=20),
                _total('g2', 'c', points=18),
            ]),
            pd.DataFrame(),
            {},
            {'a': 'Aces', 'b': 'Braves', 'c': 'Clippers'},
            48,
            'REGULAR',
            'all',
        )
        self.assertTrue(_winner(shared['cards'], 'team', 'Aces', 'PTS'))
        self.assertTrue(_winner(shared['cards'], 'team', 'Braves', 'PTS'))
        self.assertFalse(_winner(shared['cards'], 'team', 'Clippers', 'PTS'))
        blank_tie = build_team_cards(
            [
                _fixture('g1', 'REGULAR', 'FINISHED'),
                _fixture('g2', 'REGULAR', 'FINISHED'),
            ],
            pd.DataFrame([
                _total('g1', 'a', pointsTwoMade=0, pointsTwoAttempted=0),
                _total('g1', 'b', pointsTwoMade=0, pointsTwoAttempted=2),
                _total('g2', 'a', pointsTwoMade=0, pointsTwoAttempted=0),
                _total('g2', 'c', pointsTwoMade=0, pointsTwoAttempted=4),
            ]),
            pd.DataFrame(),
            {},
            {'a': 'Aces', 'b': 'Braves', 'c': 'Clippers'},
            48,
            'REGULAR',
            'all',
        )
        self.assertEqual(_text(blank_tie['cards'], 'team', 'Aces', '2FG%'), '')
        self.assertEqual(_text(blank_tie['cards'], 'team', 'Braves', '2FG%'), '.000')
        self.assertEqual(_text(blank_tie['cards'], 'team', 'Clippers', '2FG%'), '.000')
        self.assertFalse(_winner(blank_tie['cards'], 'team', 'Aces', '2FG%'))
        self.assertFalse(_winner(blank_tie['cards'], 'team', 'Braves', '2FG%'))
        self.assertFalse(_winner(blank_tie['cards'], 'team', 'Clippers', '2FG%'))
        partial = build_team_cards(
            [
                _fixture('g1', 'REGULAR', 'FINISHED'),
                _fixture('g2', 'REGULAR', 'FINISHED'),
            ],
            pd.DataFrame([
                _total('g1', 'a', pointsTwoMade=0, pointsTwoAttempted=0),
                _total('g1', 'b', pointsTwoMade=1, pointsTwoAttempted=2),
                _total('g2', 'a', pointsTwoMade=0, pointsTwoAttempted=0),
                _total('g2', 'c', pointsTwoMade=1, pointsTwoAttempted=4),
            ]),
            pd.DataFrame(),
            {},
            {'a': 'Aces', 'b': 'Braves', 'c': 'Clippers'},
            48,
            'REGULAR',
            'all',
        )
        self.assertEqual(_text(partial['cards'], 'team', 'Braves', '2FG%'), '.500')
        self.assertEqual(_text(partial['cards'], 'team', 'Clippers', '2FG%'), '.250')
        self.assertFalse(_winner(partial['cards'], 'team', 'Aces', '2FG%'))
        self.assertTrue(_winner(partial['cards'], 'team', 'Braves', '2FG%'))
        self.assertFalse(_winner(partial['cards'], 'team', 'Clippers', '2FG%'))

    def test_empty_type_has_the_switch_copy_inputs(self):
        built = build_team_cards([], pd.DataFrame(), pd.DataFrame(), {}, {}, 48, None, 'all')
        self.assertTrue(built['empty'])
        self.assertFalse(built['period_visible'])
        self.assertEqual(EMPTY_TEAM_STATS, 'No games in this view.')
        self.assertEqual(
            EMPTY_TEAM_STATS_NEXT,
            'Switch Game Type, Team, Opponent, Stadium, or Home/Away.',
        )

    def test_chips_do_not_use_a_person_period_gate(self):
        chips = period_chips_for_ids([1, 2, 11])
        self.assertEqual(
            [item['value'] for item in chips],
            ['all', '1', '2', 'h1', '11'],
        )
        self.assertNotIn('h2', [item['value'] for item in chips])


class SliceFilterTests(unittest.TestCase):
    def _built(self, **kwargs):
        fixtures = [
            _fixture('g1', 'REGULAR', 'CONFIRMED', venueId='v1', teamIdHome='a', teamIdAway='b'),
            _fixture('g2', 'REGULAR', 'FINISHED', venueId='v2', teamIdHome='b', teamIdAway='a'),
            _fixture('g3', 'REGULAR', 'CONFIRMED', venueId='v1', teamIdHome='a', teamIdAway='c'),
            _fixture('g4', 'PLAYOFF', 'CONFIRMED', venueId='v3', teamIdHome='a', teamIdAway='d'),
            _fixture('g5', 'REGULAR', 'SCHEDULED', venueId='v9', teamIdHome='a', teamIdAway='e'),
        ]
        totals = pd.DataFrame([
            _total('g1', 'a', points=10),
            _total('g1', 'b', points=4),
            _total('g2', 'a', points=8),
            _total('g2', 'b', points=6),
            _total('g3', 'a', points=30),
            _total('g3', 'c', points=2),
            _total('g4', 'a', points=100),
            _total('g4', 'd', points=1),
        ])
        periods = pd.DataFrame([
            _period('g1', 'a', 1, points=10),
            _period('g1', 'b', 1, points=4),
            _period('g2', 'a', 3, points=8),
            _period('g2', 'b', 3, points=6),
            _period('g3', 'a', 2, points=30),
            _period('g3', 'c', 2, points=2),
        ])
        names = {
            'a': 'Aces', 'b': 'Braves', 'c': 'Clippers', 'd': 'Dragons', 'e': 'Eagles',
            'v1': 'Arena One', 'v2': 'Arena Two', 'v3': 'Arena Three', 'v9': 'TBD',
        }
        return build_team_cards(
            fixtures, totals, periods, {}, names, 48, 'REGULAR', kwargs.get('period', 'all'),
            opponent=kwargs.get('opponent', 'all'),
            stadium=kwargs.get('stadium', 'all'),
            site=kwargs.get('site', 'all'),
            team=kwargs.get('team', 'all'),
        )

    def test_opponent_drops_that_team_and_renames_opp(self):
        built = self._built(opponent='b')
        names = [row['Team']['text'] for row in built['cards']['team']['rows']]
        self.assertEqual(names, ['Aces'])
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'GP'), '2')
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'PTS'), '9.0')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Team'), 'Braves')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'PTS'), '5.0')
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'GP'), '')
        self.assertNotIn('2', [item['value'] for item in built['period_chips']])
        self.assertIn('3', [item['value'] for item in built['period_chips']])
        labels = [item['label'] for item in built['opponent_options']]
        self.assertEqual(labels[0], 'vs All Teams')
        self.assertEqual(labels[1:], [
            'vs Aces', 'vs Braves', 'vs Clippers', 'vs Eagles',
        ])
        self.assertTrue(built['opponent_visible'])

    def test_game_type_menu_lists_unplayed_clubs_and_drops_other_types(self):
        fixtures = [
            _fixture('reg', 'REGULAR', 'FINISHED', venueId='v1', teamIdHome='a', teamIdAway='b'),
            _fixture('fin-later', 'FINAL', 'SCHEDULED', venueId='v9', teamIdHome='a', teamIdAway='d'),
            _fixture('fin-done', 'FINAL', 'CONFIRMED', venueId='v3', teamIdHome='d', teamIdAway='a'),
        ]
        names = {
            'a': 'Aces', 'b': 'Braves', 'd': 'Dragons',
            'v1': 'Arena One', 'v3': 'Arena Three', 'v9': 'Future Hall',
        }
        built = build_team_cards(
            fixtures,
            pd.DataFrame([
                _total('fin-done', 'a', points=4),
                _total('fin-done', 'd', points=2),
            ]),
            pd.DataFrame(),
            {},
            names,
            48,
            'FINAL',
            'all',
            team='b',
        )
        self.assertEqual(
            [item['label'] for item in built['team_options']],
            ['All Teams', 'Aces', 'Dragons'],
        )
        self.assertTrue(built['team_visible'])
        self.assertEqual(built['team'], 'all')
        self.assertEqual(
            [item['label'] for item in built['opponent_options']],
            ['vs All Teams', 'vs Aces', 'vs Dragons'],
        )
        self.assertEqual(
            [item['label'] for item in built['stadium_options']],
            ['All Stadiums', 'Arena Three'],
        )
        self.assertNotIn('Braves', [item['label'] for item in built['team_options']])
        self.assertNotIn('Future Hall', [item['label'] for item in built['stadium_options']])

    def test_stadium_and_site_stack_and_site_does_not_change_chips(self):
        stadium = self._built(stadium='v1')
        self.assertEqual(_text(stadium['cards'], 'team', 'Aces', 'GP'), '2')
        self.assertEqual(_text(stadium['cards'], 'team', 'Braves', 'GP'), '1')
        self.assertEqual(_text(stadium['cards'], 'team', 'Clippers', 'GP'), '1')
        both = self._built(opponent='b', stadium='v1')
        self.assertEqual(
            [row['Team']['text'] for row in both['cards']['team']['rows']],
            ['Aces'],
        )
        self.assertEqual(_text(both['cards'], 'team', 'Aces', 'PTS'), '10.0')
        self.assertEqual(_opp_text(both['cards'], 'team', 0, 'Team'), 'Braves')
        home = self._built(site='home')
        away = self._built(site='away')
        self.assertEqual(_text(home['cards'], 'team', 'Aces', 'GP'), '2')
        self.assertEqual(_text(home['cards'], 'team', 'Braves', 'GP'), '1')
        self.assertNotIn('Clippers', [row['Team']['text'] for row in home['cards']['team']['rows']])
        self.assertEqual(_text(away['cards'], 'team', 'Aces', 'GP'), '1')
        self.assertEqual(_text(away['cards'], 'team', 'Aces', 'PTS'), '8.0')
        self.assertEqual(home['period_chips'], away['period_chips'])
        self.assertIn('2', [item['value'] for item in home['period_chips']])
        self.assertEqual(
            [item['label'] for item in home['stadium_options']],
            ['All Stadiums', 'Arena One', 'Arena Two'],
        )
        self.assertNotIn('Arena Three', [item['label'] for item in home['stadium_options']])
        self.assertTrue(home['stadium_visible'])

    def test_unknown_opponent_falls_back_to_every_team(self):
        built = self._built(opponent='missing')
        self.assertEqual(built['opponent'], 'all')
        self.assertEqual(
            [row['Team']['text'] for row in built['cards']['team']['rows']],
            ['Aces', 'Braves', 'Clippers'],
        )
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Team'), 'Opp')

    def test_one_named_team_hides_the_opponent_menu(self):
        built = build_team_cards(
            [_fixture('g1', 'REGULAR', 'CONFIRMED', venueId='v1', teamIdHome='a', teamIdAway='a')],
            pd.DataFrame([_total('g1', 'a', points=3)]),
            pd.DataFrame(),
            {},
            {'a': 'Aces', 'v1': 'Arena One'},
            48,
            'REGULAR',
            'all',
            opponent='a',
        )
        self.assertFalse(built['opponent_visible'])
        self.assertEqual(built['opponent'], 'all')
        self.assertFalse(built['team_visible'])
        self.assertFalse(built['stadium_visible'])
        self.assertEqual(_opp_text(built['cards'], 'team', 0, 'Team'), 'Opp')

    def test_one_team_pins_a_summary_then_each_opponent(self):
        built = self._built(team='a')
        rows = built['cards']['team']['rows']
        opp = built['cards']['team']['opp_rows']
        self.assertEqual([row['Team']['text'] for row in rows], [
            'Aces', 'Aces vs', 'Aces vs',
        ])
        self.assertEqual([row['Team']['text'] for row in opp], [
            'Opp', 'Braves', 'Clippers',
        ])
        self.assertTrue(rows[0]['summary'])
        self.assertFalse(rows[1].get('summary'))
        self.assertEqual(_text(built['cards'], 'team', 'Aces', 'GP'), '3')
        self.assertEqual(_text(built['cards'], 'team', 'Aces vs', 'GP'), '2')
        self.assertTrue(built['show_opp_locked'])
        self.assertNotIn('a', [item['value'] for item in built['opponent_options']])
        self.assertIn('vs Aces', built['opponent_width_labels'])
        self.assertIn('3', [item['value'] for item in built['period_chips']])

    def test_named_opponent_is_one_matchup_without_a_summary(self):
        built = self._built(team='a', opponent='b')
        rows = built['cards']['team']['rows']
        self.assertEqual([row['Team']['text'] for row in rows], ['Aces vs'])
        self.assertFalse(rows[0].get('summary'))
        self.assertEqual(built['cards']['team']['opp_rows'][0]['Team']['text'], 'Braves')
        self.assertEqual(_text(built['cards'], 'team', 'Aces vs', 'GP'), '2')

    def test_one_opponent_keeps_the_summary_beside_that_matchup(self):
        built = self._built(team='a', stadium='v2')
        rows = built['cards']['team']['rows']
        self.assertEqual([row['Team']['text'] for row in rows], ['Aces', 'Aces vs'])
        self.assertTrue(rows[0]['summary'])
        self.assertEqual(rows[0]['PTS']['text'], rows[1]['PTS']['text'])
        self.assertFalse(rows[0]['PTS']['winner'])
        self.assertFalse(rows[1]['PTS']['winner'])

    def test_summary_does_not_take_column_best(self):
        summary = {'PTS': {'text': '30.0', 'winner': False}, 'summary': True}
        low = {'PTS': {'text': '10.0', 'winner': False}}
        high = {'PTS': {'text': '12.0', 'winner': False}}
        _paint_pair([summary, low, high], [], ['PTS'])
        self.assertFalse(summary['PTS']['winner'])
        self.assertFalse(low['PTS']['winner'])
        self.assertTrue(high['PTS']['winner'])

    def test_team_chips_ignore_home_away(self):
        home = self._built(team='a', site='home')
        self.assertIn('3', [item['value'] for item in home['period_chips']])
        self.assertEqual(_text(home['cards'], 'team', 'Aces', 'GP'), '2')


class ColumnWinnerTests(unittest.TestCase):
    def test_shared_best_and_blanks(self):
        from synergy_reporter.column_winners import winning_indexes
        self.assertEqual(winning_indexes([20, 20, 20]), [])
        self.assertEqual(winning_indexes([20, 18, 20]), [0, 2])
        self.assertEqual(winning_indexes([None, 20, 20]), [])
        self.assertEqual(winning_indexes([None, 20, 18]), [1])
        self.assertEqual(winning_indexes([None, 20, None]), [])
        self.assertEqual(winning_indexes([20]), [])
        self.assertEqual(winning_indexes([4, 1, 1], lower=True), [1, 2])
        self.assertEqual(winning_indexes([None, 0.0, 1.0]), [2])


class PaceBaseTests(unittest.TestCase):
    def test_one_game_still_shares_the_mean_pace(self):
        source = pd.DataFrame([
            {
                'entityId': 'home', 'minutes': 'PT60M', 'points': 20,
                'fieldGoalsAttempted': 10, 'freeThrowsAttempted': 0, 'turnovers': 0,
                'reboundsOffensive': 0, 'reboundsDefensiveAgainst': 0,
                'fieldGoalsEffectivePercentage': None, 'assists': 0, 'fieldGoalsMade': 0,
                'pointsThreeAttempted': 0,
            },
            {
                'entityId': 'away', 'minutes': 'PT60M', 'points': 16,
                'fieldGoalsAttempted': 20, 'freeThrowsAttempted': 0, 'turnovers': 0,
                'reboundsOffensive': 0, 'reboundsDefensiveAgainst': 0,
                'fieldGoalsEffectivePercentage': None, 'assists': 0, 'fieldGoalsMade': 0,
                'pointsThreeAttempted': 0,
            },
        ])
        report = PostGameReport.__new__(PostGameReport)
        report.id_table = {'home': 'Home', 'away': 'Away'}
        report.team_stats_df = source
        report.playbyplay_df = pd.DataFrame()
        report.regulation_minutes = 48
        pace = set(report.get_team_advance_stats_df(source)['Pace'])
        self.assertEqual(pace, {'60.0'})
        report.regulation_minutes = 40
        pace = set(report.get_team_advance_stats_df(source)['Pace'])
        self.assertEqual(pace, {'50.0'})


class FrameStoreTests(unittest.TestCase):
    def setUp(self):
        clear_frames()

    def test_season_pin_keeps_the_open_game_and_home_prefetch(self):
        for fixture_id in ('g1', 'g2', 'g3', 'g4'):
            store('org', fixture_id, status='CONFIRMED', team_df=pd.DataFrame({'fixtureId': [fixture_id]}), touch=('team_df',))
        pin_open('org', 'g1')
        pin_home('org', ['g2'])
        pin_season('org', 'old', ['g3'])
        pin_season('org', 'new', ['g4'])
        self.assertIsNotNone(peek('org', 'g1'))
        self.assertIsNotNone(peek('org', 'g2'))
        self.assertIsNone(peek('org', 'g3'))
        self.assertIsNotNone(peek('org', 'g4'))

    def test_confirmed_stays_and_finished_expires(self):
        confirmed = store(
            'org', 'c', status='CONFIRMED',
            playbyplay_df=pd.DataFrame({'eventType': ['2pt']}),
            touch=('playbyplay_df',),
        )
        confirmed.times['playbyplay_df'] = time.monotonic() - 100
        self.assertTrue(piece_fresh(confirmed, 'playbyplay_df'))
        finished = store(
            'org', 'f', status='FINISHED',
            playbyplay_df=pd.DataFrame({'eventType': ['2pt']}),
            touch=('playbyplay_df',),
        )
        finished.times['playbyplay_df'] = time.monotonic() - (SHORT_CACHE_SECONDS + 1)
        self.assertFalse(piece_fresh(finished, 'playbyplay_df'))
        self.assertIn('CONFIRMED', FINISHED_STATUSES)

    def test_singleflight_runs_the_builder_once(self):
        calls = []

        def _build():
            calls.append(1)
            time.sleep(0.05)
            return 'ok'

        results = []

        def _run():
            results.append(singleflight('same', _build))

        threads = [threading.Thread(target=_run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(calls, [1])
        self.assertEqual(results, ['ok', 'ok', 'ok', 'ok'])


class WaveTests(unittest.TestCase):
    def test_pool_size_matches_the_call_count(self):
        from synergy_inbounder.communicator import _wave_local

        def _grab():
            adapter = _wave_local.session.get_adapter('https://example.com')
            return adapter._pool_maxsize

        self.assertEqual(run_wave([_grab, _grab, _grab]), [3, 3, 3])

    def test_confirmed_body_gets_the_long_ttl(self):
        from synergy_inbounder.communicator import fixture_body_expire
        self.assertEqual(fixture_body_expire('CONFIRMED', False), LONG_CACHE_SECONDS)
        self.assertIsNone(fixture_body_expire('FINISHED', False))
        self.assertIsNone(fixture_body_expire('CONFIRMED', True))


class PayloadCacheTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()
        self.pbp_calls = []

    def _patches(self):
        season = pd.DataFrame([
            _fixture('g1', 'REGULAR', 'CONFIRMED'),
            _fixture('g2', 'PLAYOFF', 'CONFIRMED'),
        ])
        totals = [
            {'fixtureId': 'g1', 'entityId': 'a', 'statistics': _total('g1', 'a', points=10)},
            {'fixtureId': 'g2', 'entityId': 'a', 'statistics': _total('g2', 'a', points=4)},
        ]
        periods = [
            {'fixtureId': 'g1', 'entityId': 'a', 'periodId': 1, 'statistics': _period('g1', 'a', 1, points=3)},
        ]

        def _pbp(org_id, fixture_id, status):
            self.pbp_calls.append(fixture_id)
            return {'data': []}

        return patch.multiple(
            'synergy_reporter.team_season.Parser',
            parse_season_game_list_df=lambda org, season_id: season,
            parse_id_tables=lambda org: {'a': 'Aces'},
        ), patch(
            'synergy_reporter.team_season.Communicator_totals',
            return_value=totals,
        ), patch(
            'synergy_reporter.team_season.Communicator_periods',
            return_value=periods,
        ), patch(
            'synergy_reporter.team_season.Communicator_pbp',
            side_effect=_pbp,
        )

    def test_chip_does_not_refetch_or_move_the_stamp(self):
        season_patch, totals_patch, periods_patch, pbp_patch = self._patches()
        with season_patch, totals_patch, periods_patch, pbp_patch:
            first = team_stats_payload('PLG', dict(SYNERGY_SEASONS)['2025-26'], None, 'all', 'scope')
            stamp = first['stamp']
            self.assertEqual(self.pbp_calls, ['g1'])
            second = team_stats_payload(
                'PLG', dict(SYNERGY_SEASONS)['2025-26'], 'REGULAR', '1', 'chip',
            )
            third = team_stats_payload(
                'PLG', dict(SYNERGY_SEASONS)['2025-26'], 'REGULAR', '1', 'slice',
            )
        self.assertTrue(first['ok'])
        self.assertEqual(second['stamp'], stamp)
        self.assertEqual(second['period'], '1')
        self.assertEqual(third['stamp'], stamp)
        self.assertEqual(third['period'], '1')
        self.assertEqual(self.pbp_calls, ['g1'])
        self.assertEqual(_text(second['cards'], 'team', 'Aces', 'PTS'), '3.0')
        season_id = dict(SYNERGY_SEASONS)['2025-26']
        self.assertFalse(type_needs_download('PLG', season_id, 'REGULAR'))
        self.assertTrue(type_needs_download('PLG', season_id, 'PLAYOFF'))
        self.assertFalse(type_needs_download('PLG', season_id, None))
        self.assertFalse(type_needs_download('PLG', season_id, float('nan')))
        self.assertTrue(type_needs_download('PLG', 'missing-season', 'REGULAR'))
        self.assertTrue(type_needs_download('nope', season_id, 'REGULAR'))

    def test_error_hides_the_traceback(self):
        with patch(
            'synergy_reporter.team_season.Parser.parse_season_game_list_df',
            side_effect=RuntimeError('secret token'),
        ), patch(
            'synergy_reporter.team_season.Communicator_totals',
            return_value=[],
        ), patch(
            'synergy_reporter.team_season.Communicator_periods',
            return_value=[],
        ), patch(
            'synergy_reporter.team_season.Parser.parse_id_tables',
            return_value={},
        ):
            payload = team_stats_payload('PLG', None, None, 'all', 'scope')
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['message'], ERROR_GAME)
        self.assertNotIn('secret', payload['message'])
        self.assertFalse(payload['period_visible'])
        clear_runtime_caches()

    def test_schedule_chrome_skips_totals_and_play_by_play(self):
        season_patch, totals_patch, periods_patch, pbp_patch = self._patches()
        season_id = dict(SYNERGY_SEASONS)['2025-26']
        with season_patch, totals_patch as totals, periods_patch as periods, pbp_patch:
            chrome = schedule_chrome('PLG', season_id, reset=True)
        self.assertTrue(chrome['ok'])
        self.assertTrue(chrome['needs_cards'])
        self.assertEqual(chrome['team'], 'all')
        self.assertEqual(self.pbp_calls, [])
        self.assertFalse(totals.called)
        self.assertFalse(periods.called)
