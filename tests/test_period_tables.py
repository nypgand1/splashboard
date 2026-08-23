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


class MinutesFormatTests(unittest.TestCase):
    def test_pt_duration_becomes_mmss(self):
        from synergy_reporter.post_game_report import minutes_to_mmss
        self.assertEqual(minutes_to_mmss('PT38M12S'), '38:12')
        self.assertEqual(minutes_to_mmss('PT0M05S'), '00:05')
        self.assertEqual(minutes_to_mmss('PT12M'), '12:00')
        self.assertEqual(minutes_to_mmss('PT00M30.4S'), '00:30')
        self.assertEqual(minutes_to_mmss(None), '')
        self.assertNotIn('PT', minutes_to_mmss('PT38M12S'))

    def test_team_stats_min_column_is_mmss(self):
        team_stats = pd.DataFrame([{
            'entityId': 'home',
            'minutes': 'PT38M12S',
            'pointsTwoMade': 10,
            'pointsTwoAttempted': 20,
            'pointsTwoPercentage': 50.0,
            'pointsThreeMade': 5,
            'pointsThreeAttempted': 15,
            'pointsThreePercentage': 33.3,
            'freeThrowsMade': 8,
            'freeThrowsAttempted': 10,
            'freeThrowsPercentage': 80.0,
            'reboundsOffensive': 8,
            'reboundsDefensive': 20,
            'rebounds': 28,
            'assists': 18,
            'turnovers': 12,
            'steals': 6,
            'blocks': 3,
            'foulsTotal': 19,
            'points': 90,
        }])
        players = pd.DataFrame([{
            'entityId': 'home',
            'personId': 'p1',
            'minutes': 'PT32M04S',
            'plusMinus': 5,
            'pointsTwoMade': 4,
            'pointsTwoAttempted': 8,
            'pointsTwoPercentage': 50.0,
            'pointsThreeMade': 1,
            'pointsThreeAttempted': 4,
            'pointsThreePercentage': 25.0,
            'freeThrowsMade': 2,
            'freeThrowsAttempted': 2,
            'freeThrowsPercentage': 100.0,
            'reboundsOffensive': 1,
            'reboundsDefensive': 4,
            'rebounds': 5,
            'assists': 3,
            'turnovers': 2,
            'steals': 1,
            'blocks': 0,
            'foulsTotal': 2,
            'points': 13,
            'fieldGoalsEffectivePercentage': 50.0,
            'usageRate': 20.0,
            'plus': 20,
            'minus': 15,
            'starter': True,
        }])
        bundle = (
            team_stats,
            pd.DataFrame([{'entityId': 'home', 'periodId': 1, 'points': 20}]),
            players,
            {'home': ['p1']},
            pd.DataFrame(),
            {'home': 'Braves', 'p1': 'Starter'},
            [],
        )
        with patch.object(Parser, 'parse_game_bundle', return_value=bundle):
            report = PostGameReport('game-1')
        team = report.get_team_stats_df()
        self.assertEqual(team.iloc[0]['Min'], '38:12')
        self.assertNotIn('PT', str(team.iloc[0]['Min']))
        players_out = report._get_player_stats_df_dict()['Braves']
        self.assertEqual(players_out.iloc[0]['Min'], '32:04')
        self.assertEqual(list(players_out.sort_values(by=['PTS'], ascending=False)['PTS']), list(players_out['PTS']))
