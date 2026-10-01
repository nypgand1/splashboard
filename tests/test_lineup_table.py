import json
import unittest
from unittest.mock import patch

import pandas as pd

from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats
from synergy_reporter.post_game_report import PostGameReport, lineup_ppp_display, shot_pct_display


def _event(**kwargs):
    row = {
        'timestamp': None,
        'eventType': '2pt',
        'subType': 'jumpshot',
        'entityId': 'home',
        'periodId': 1,
        'clock': 'PT10M0S',
        'success': 1,
        'sequence': 1,
        'personId': None,
        'scores': None,
        'options': None,
    }
    row.update(kwargs)
    return row


class LineupPointTests(unittest.TestCase):
    def test_one_make_can_count_in_more_than_one_bucket(self):
        home = 'home'
        rows = [
            _event(eventType='period', subType='start', clock='PT12M0S', success=None, sequence=1),
            _event(
                clock='PT11M0S',
                sequence=2,
                options={'pointsInThePaint': True, 'fastBreak': True, 'secondChance': True},
            ),
            _event(eventType='2pt', success=0, clock='PT10M0S', sequence=3, options={'pointsInThePaint': True}),
            _event(eventType='period', subType='end', entityId=None, clock='PT9M0S', success=None, sequence=4),
        ]
        df = pd.DataFrame(rows)
        process_lineup_pbp(df, {home: ['p1', 'p2', 'p3', 'p4', 'p5']})
        stats = process_lineup_stats(df)[home]
        self.assertEqual(int(stats['PIP'].sum()), 2)
        self.assertEqual(int(stats['FBP'].sum()), 2)
        self.assertEqual(int(stats['SCP'].sum()), 2)
        self.assertEqual(int(stats['POT'].sum()), 0)

    def test_flagged_free_throw_counts_and_a_scoreless_trip_is_zero_ppp(self):
        self.assertEqual(lineup_ppp_display(0, 2), '0.00')
        self.assertEqual(lineup_ppp_display(3, 0), '')
        self.assertEqual(shot_pct_display(5, 6, 83.3), '.833')
        self.assertEqual(shot_pct_display(4, 4, 100.0), '1.000')
        self.assertEqual(shot_pct_display(0, 3), '.000')


class LineupTableTests(unittest.TestCase):
    def _report(self, rows, starters):
        bundle = (
            pd.DataFrame([{'entityId': 'home'}]),
            pd.DataFrame(),
            pd.DataFrame(),
            starters,
            pd.DataFrame(),
            {
                'home': 'Braves',
                'p1': 'A', 'p2': 'B', 'p3': 'C', 'p4': 'D', 'p5': 'E', 'p6': 'F',
            },
            [{'personId': f'p{i}', 'shirtNumber': str(i)} for i in range(1, 7)],
            pd.DataFrame(),
        )
        with patch.object(Parser, 'parse_game_bundle', return_value=bundle):
            report = PostGameReport('game-1')
        report.playbyplay_df = pd.DataFrame(rows)
        report._play_by_play_view = None
        report._raw_lineup_df_dict = None
        report._lineup_json_by_size = None
        return report

    def _rows(self, payload_json):
        payload = json.loads(payload_json)
        columns = payload['columns']
        rows = [dict(zip(columns, row)) for row in payload['data']]
        return columns, rows

    def test_lineup_table_drops_efg_and_pm_and_adds_key_points(self):
        rows = [
            _event(eventType='period', subType='start', clock='PT12M0S', success=None, sequence=1),
            _event(clock='PT11M0S', sequence=2, options={'pointsInThePaint': True, 'fastBreak': True}),
            _event(
                eventType='freeThrow', subType='1Of1', clock='PT10M30S', sequence=3,
                options={'fastBreak': True},
            ),
            _event(eventType='substitution', subType='out', personId='p1', clock='PT10M0S', success=None, sequence=4),
            _event(eventType='substitution', subType='in', personId='p6', clock='PT10M0S', success=None, sequence=5),
            _event(
                eventType='3pt', clock='PT9M0S', sequence=6,
                options={'secondChance': True, 'fromTurnover': True},
            ),
            _event(eventType='substitution', subType='out', personId='p2', clock='PT8M0S', success=None, sequence=7),
            _event(eventType='substitution', subType='in', personId='p1', clock='PT8M0S', success=None, sequence=8),
            _event(eventType='turnover', subType='badPass', clock='PT7M0S', success=None, sequence=9),
            _event(eventType='period', subType='end', entityId=None, clock='PT6M0S', success=None, sequence=10),
        ]
        report = self._report(rows, {'home': ['p1', 'p2', 'p3', 'p4', 'p5']})
        columns, rows_out = self._rows(report.get_lineup_stats_json_dict()['Braves'])
        self.assertEqual(
            columns,
            [
                'Lineup', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
                'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BL',
                'PF', 'FD', 'PTS', 'PIP', 'SCP', 'FBP', 'POT', 'PPP',
            ],
        )
        by_name = {row['Lineup']: row for row in rows_out}
        first = by_name['A-B-C-D-E']
        self.assertEqual(first['PTS'], 3)
        self.assertEqual(first['PIP'], 2)
        self.assertEqual(first['FBP'], 3)
        self.assertEqual(first['SCP'], '')
        self.assertEqual(first['POT'], '')
        self.assertEqual(first['PPP'], '3.00')
        self.assertEqual(first['2FG%'], '1.000')
        second = by_name['B-C-D-E-F']
        self.assertEqual(second['SCP'], 3)
        self.assertEqual(second['POT'], 3)
        self.assertEqual(second['PIP'], '')
        self.assertEqual(second['PPP'], '3.00')
        scoreless = by_name['A-C-D-E-F']
        self.assertEqual(scoreless['PTS'], '')
        self.assertEqual(scoreless['PPP'], '0.00')

    def test_smaller_lineups_recompute_ppp_from_the_sum(self):
        rows = [
            _event(eventType='period', subType='start', clock='PT12M0S', success=None, sequence=1),
            _event(clock='PT11M0S', sequence=2),
            _event(eventType='turnover', subType='badPass', clock='PT10M0S', success=None, sequence=3),
            _event(eventType='substitution', subType='out', personId='p1', clock='PT9M0S', success=None, sequence=4),
            _event(eventType='substitution', subType='in', personId='p6', clock='PT9M0S', success=None, sequence=5),
            _event(eventType='3pt', clock='PT8M0S', sequence=6),
            _event(eventType='period', subType='end', entityId=None, clock='PT7M0S', success=None, sequence=7),
        ]
        report = self._report(rows, {'home': ['p1', 'p2', 'p3', 'p4', 'p5']})
        _, rows_out = self._rows(report.get_lineup_stats_json_dict(4)['Braves'])
        shared = next(row for row in rows_out if row['Lineup'] == 'B-C-D-E')
        self.assertEqual(shared['PTS'], 5)
        self.assertEqual(shared['PPP'], '1.67')

    def test_display_text_survives_the_table_readers(self):
        from synergy_reporter.report_components import _sorted_player_split, read_split_frame

        player = pd.DataFrame([{
            '#': 1,
            'Player': 'Lin',
            'Min': '20:00',
            '+/-': 1,
            'PTS': 0,
            '2FG%': '.000',
            '3FG%': '.330',
            'FT%': '1.000',
            'eFG%': '0.0%',
        }])
        painted = json.loads(_sorted_player_split(
            {'p_df_dict': {'Braves': player.to_json(orient='split')}},
            {'home_team': 'Braves'},
            'home',
        ))
        row = dict(zip(painted['columns'], painted['data'][0]))
        self.assertEqual(row['2FG%'], '.000')
        self.assertEqual(row['3FG%'], '.330')
        self.assertEqual(row['FT%'], '1.000')
        self.assertEqual(row['eFG%'], '0.0%')

        lineup = read_split_frame(pd.DataFrame([{
            'Lineup': 'A-B-C-D-E',
            'PTS': '',
            '2FG%': '.000',
            'PPP': '0.00',
        }]).to_json(orient='split'))
        self.assertEqual(lineup.iloc[0]['PPP'], '0.00')
        self.assertEqual(lineup.iloc[0]['2FG%'], '.000')
        self.assertEqual(lineup.iloc[0]['PTS'], '')
