import unittest

import pandas as pd

from synergy_inbounder.possessions import annotate_possessions, possession_counts
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats


def _row(**kwargs):
    base = {
        'eventType': '2pt',
        'subType': 'layup',
        'entityId': 'home',
        'periodId': 1,
        'clock': 'PT10M0S',
        'success': 0,
        'sequence': 1,
        'personId': None,
    }
    base.update(kwargs)
    return base


def _counts(rows):
    return possession_counts(pd.DataFrame(rows))


class PossessionWalkTests(unittest.TestCase):
    def test_made_field_goal_is_one_trip_and_api_possession_is_ignored(self):
        counts = _counts([
            _row(eventType='possession', subType=None, success=None, sequence=1),
            _row(eventType='2pt', success=1, sequence=2),
            _row(eventType='possession', subType=None, success=None, sequence=3),
        ])
        self.assertEqual(counts, {'home': 1})

    def test_and_one_free_throw_stays_in_the_field_goal_trip(self):
        counts = _counts([
            _row(eventType='2pt', success=1, sequence=1),
            _row(eventType='freeThrow', subType='1Of1', success=1, sequence=2),
        ])
        self.assertEqual(counts, {'home': 1})

    def test_offensive_rebound_does_not_start_a_new_trip(self):
        counts = _counts([
            _row(eventType='2pt', success=0, sequence=1),
            _row(eventType='rebound', subType='offensive', success=None, sequence=2),
            _row(eventType='2pt', success=1, sequence=3),
        ])
        self.assertEqual(counts, {'home': 1})

    def test_defensive_rebound_and_turnover_end_trips(self):
        counts = _counts([
            _row(eventType='2pt', success=0, sequence=1),
            _row(eventType='rebound', subType='defensive', entityId='away', success=None, sequence=2),
            _row(eventType='turnover', subType='badPass', entityId='away', success=None, sequence=3),
            _row(eventType='steal', subType=None, entityId='home', success=None, sequence=4),
        ])
        self.assertEqual(counts, {'home': 1, 'away': 1})

    def test_walks_frame_order_not_sequence(self):
        counts = _counts([
            _row(eventType='rebound', subType='defensive', entityId='away', success=None, sequence=20),
            _row(eventType='2pt', success=0, entityId='home', sequence=10),
        ])
        self.assertEqual(counts, {})

    def test_technical_free_throw_does_not_end_the_open_trip(self):
        counts = _counts([
            _row(eventType='2pt', success=0, sequence=1),
            _row(eventType='foul', subType='technical', entityId='away', success=None, sequence=2),
            _row(eventType='freeThrow', subType='1Of1', entityId='away', success=1, sequence=3),
            _row(eventType='2pt', success=1, sequence=4),
        ])
        self.assertEqual(counts, {'home': 1})

    def test_period_end_closes_a_used_trip(self):
        counts = _counts([
            _row(eventType='2pt', success=0, sequence=1),
            _row(eventType='period', subType='end', entityId=None, success=None, sequence=2, clock='PT0M0S'),
        ])
        self.assertEqual(counts, {'home': 1})

    def test_unused_trip_at_period_end_is_not_counted(self):
        counts = _counts([
            _row(eventType='rebound', subType='defensive', entityId='home', success=None, sequence=1),
            _row(eventType='period', subType='end', entityId=None, success=None, sequence=2, clock='PT0M0S'),
        ])
        self.assertEqual(counts, {})

    def test_same_team_defensive_rebound_keeps_the_used_trip(self):
        counts = _counts([
            _row(eventType='2pt', success=0, sequence=1),
            _row(eventType='rebound', subType='defensive', entityId='home', success=None, sequence=2),
            _row(eventType='period', subType='end', entityId=None, success=None, sequence=3, clock='PT0M0S'),
        ])
        self.assertEqual(counts, {'home': 1})

    def test_empty_frame_has_no_counts(self):
        self.assertEqual(possession_counts(pd.DataFrame()), {})


class LineupPossessionCreditTests(unittest.TestCase):
    def test_poss_is_credited_to_the_lineup_on_the_end_row(self):
        home = 'home'
        rows = [
            _row(eventType='period', subType='start', entityId=home, clock='PT12M0S', sequence=1),
            _row(eventType='possession', subType=None, success=None, clock='PT11M0S', sequence=2),
            _row(eventType='substitution', subType='out', personId='p1', clock='PT11M0S', sequence=3),
            _row(eventType='substitution', subType='in', personId='p6', clock='PT11M0S', sequence=4),
            _row(eventType='2pt', success=1, clock='PT10M0S', sequence=5),
            _row(eventType='period', subType='end', entityId=None, clock='PT9M0S', sequence=6),
        ]
        df = pd.DataFrame(rows)
        process_lineup_pbp(df, {home: ['p1', 'p2', 'p3', 'p4', 'p5']})
        stats = process_lineup_stats(df)[home]
        ended = stats[stats['POSS'] > 0]
        self.assertEqual(len(ended), 1)
        self.assertEqual(ended.iloc[0]['POSS'], 1)
        self.assertIn('p6', ended.iloc[0][home])
        self.assertNotIn('p1', ended.iloc[0][home])


class PossessionColumnTests(unittest.TestCase):
    def test_end_row_records_the_offense_not_the_rebounder(self):
        df = annotate_possessions(pd.DataFrame([
            _row(eventType='2pt', success=0, sequence=1),
            _row(eventType='rebound', subType='defensive', entityId='away', success=None, sequence=2),
        ]))
        end = df[df['poss_end']]
        self.assertEqual(len(end), 1)
        self.assertEqual(end.iloc[0]['poss_team_id'], 'home')
        self.assertEqual(end.iloc[0]['entityId'], 'away')
