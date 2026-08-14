import unittest
from unittest.mock import patch

import pandas as pd

from synergy_inbounder.parser import Parser
from synergy_reporter.post_game_report import PostGameReport


def _bundle():
    team_stats = pd.DataFrame([
        {'entityId': 'home', 'fieldGoalsAttempted': 50},
    ])
    periods = pd.DataFrame([
        {'entityId': 'home', 'periodId': 1, 'points': 20, 'foulsTotal': 3, 'timeoutsUsed': 1},
        {'entityId': 'home', 'periodId': 11, 'points': 8, 'foulsTotal': 1, 'timeoutsUsed': 0},
        {'entityId': 'away', 'periodId': 1, 'points': 18, 'foulsTotal': 2, 'timeoutsUsed': 0},
        {'entityId': 'away', 'periodId': 11, 'points': 10, 'foulsTotal': 2, 'timeoutsUsed': 1},
    ])
    players = pd.DataFrame([
        {'entityId': 'home', 'personId': 'p1', 'starter': True},
    ])
    return (
        team_stats,
        periods,
        players,
        {'home': ['p1'], 'away': []},
        pd.DataFrame(),
        {'home': 'Braves', 'away': 'Visitors', 'p1': 'Starter'},
        [],
    )


class PeriodTableTests(unittest.TestCase):
    def test_period_columns_use_official_labels(self):
        with patch.object(Parser, 'parse_game_bundle', return_value=_bundle()):
            report = PostGameReport('game-1')
        pts = report.get_period_team_pts_df()
        self.assertIn('1Q', pts.columns)
        self.assertIn('OT', pts.columns)
        self.assertIn('Total', pts.columns)
        braves = pts[pts['Team'] == 'Braves'].iloc[0]
        self.assertEqual(braves['1Q'], 20)
        self.assertEqual(braves['OT'], 8)
        self.assertEqual(braves['Total'], 28)
