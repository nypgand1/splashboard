import unittest

import pandas as pd

from synergy_inbounder.pre_processing_func import process_lineup_pbp


class LineupOnCourtTests(unittest.TestCase):
    def test_starters_then_substitution_update_on_court(self):
        home = 'home'
        df = pd.DataFrame([
            {
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
            },
            {
                'eventType': 'substitution',
                'subType': 'out',
                'entityId': home,
                'personId': 'p1',
            },
            {
                'eventType': 'substitution',
                'subType': 'in',
                'entityId': home,
                'personId': 'p6',
            },
        ])
        process_lineup_pbp(df, {home: ['p1', 'p2', 'p3', 'p4', 'p5']})
        self.assertEqual(sorted(df.at[0, home]), ['p1', 'p2', 'p3', 'p4', 'p5'])
        self.assertEqual(sorted(df.at[1, home]), ['p2', 'p3', 'p4', 'p5'])
        self.assertEqual(sorted(df.at[2, home]), ['p2', 'p3', 'p4', 'p5', 'p6'])

    def test_empty_frame_is_a_no_op(self):
        df = pd.DataFrame()
        self.assertIsNone(process_lineup_pbp(df, {'home': ['p1']}))
        self.assertTrue(df.empty)
