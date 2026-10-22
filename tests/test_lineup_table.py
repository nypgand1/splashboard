import json
import unittest
from unittest.mock import patch

import pandas as pd

from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats
from synergy_reporter.post_game_report import (
    PostGameReport,
    lineup_ppp_display,
    shot_pct_display,
    sort_lineup_table,
)


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


class LineupOrderTests(unittest.TestCase):
    def test_rows_sort_by_plus_minus_then_ppp_then_minutes_then_name(self):
        frame = pd.DataFrame([
            {'Lineup': 'B', '+/-': 1, 'PPP': '0.50', 'duration': 100, 'Min': '1:40'},
            {'Lineup': 'A', '+/-': 1, 'PPP': '1.00', 'duration': 30, 'Min': '0:30'},
            {'Lineup': 'C', '+/-': 1, 'PPP': '1.00', 'duration': 90, 'Min': '1:30'},
            {'Lineup': 'D', '+/-': 4, 'PPP': '', 'duration': 10, 'Min': '0:10'},
            {'Lineup': 'E', '+/-': 1, 'PPP': '', 'duration': 500, 'Min': '8:20'},
        ])
        self.assertEqual(
            sort_lineup_table(frame)['Lineup'].tolist(),
            ['D', 'C', 'A', 'B', 'E'],
        )

    def test_displayed_minutes_sort_as_seconds_when_duration_is_absent(self):
        frame = pd.DataFrame([
            {'Lineup': 'Short', '+/-': 0, 'PPP': '1.00', 'Min': '9:00'},
            {'Lineup': 'Long', '+/-': 0, 'PPP': '1.00', 'Min': '10:00'},
        ])
        self.assertEqual(sort_lineup_table(frame)['Lineup'].tolist(), ['Long', 'Short'])


class LineupTableTests(unittest.TestCase):
    def _report(self, rows, starters, id_table=None, roster=None):
        names = {
            'home': 'Braves',
            'away': 'Dreamers',
            'p1': 'A', 'p2': 'B', 'p3': 'C', 'p4': 'D', 'p5': 'E', 'p6': 'F',
        }
        if id_table:
            names.update(id_table)
        people = roster or [{'personId': f'p{i}', 'shirtNumber': str(i)} for i in range(1, 7)]
        bundle = (
            pd.DataFrame([{'entityId': 'home'}]),
            pd.DataFrame(),
            pd.DataFrame(),
            starters,
            pd.DataFrame(),
            names,
            people,
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
                'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS',
                'PF', 'FD', 'PTS', 'PIP', 'SCP', 'FBP', 'POT', 'PPP',
                'Opp_2M', 'Opp_2A', 'Opp_2FG%', 'Opp_3M', 'Opp_3A', 'Opp_3FG%',
                'Opp_FTM', 'Opp_FTA', 'Opp_FT%', 'Opp_OR', 'Opp_DR', 'Opp_REB',
                'Opp_AST', 'Opp_TO', 'Opp_ST', 'Opp_BS', 'Opp_PF', 'Opp_FD',
                'Opp_PTS', 'Opp_PIP', 'Opp_SCP', 'Opp_FBP', 'Opp_POT', 'Opp_PPP',
                '_lineup_key',
            ],
        )
        keys = [row['_lineup_key'] for row in rows_out]
        self.assertEqual(len(keys), len(set(keys)))
        by_name = {row['Lineup']: row for row in rows_out}
        first = by_name['A-B-C-D-E']
        self.assertEqual(first['_lineup_key'], 'p1|p2|p3|p4|p5')
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

    def test_same_short_label_keeps_a_key_per_id_set(self):
        rows = [
            _event(eventType='period', subType='start', clock='PT12M0S', success=None, sequence=1),
            _event(clock='PT11M0S', sequence=2),
            _event(eventType='substitution', subType='out', personId='p1', clock='PT10M0S', success=None, sequence=3),
            _event(eventType='substitution', subType='in', personId='p7', clock='PT10M0S', success=None, sequence=4),
            _event(clock='PT9M0S', sequence=5),
            _event(eventType='period', subType='end', entityId=None, clock='PT8M0S', success=None, sequence=6),
        ]
        roster = [{'personId': f'p{i}', 'shirtNumber': str(i)} for i in range(1, 7)]
        roster.append({'personId': 'p7', 'shirtNumber': '7'})
        report = self._report(
            rows,
            {'home': ['p1', 'p2', 'p3', 'p4', 'p5']},
            id_table={'p7': 'A'},
            roster=roster,
        )
        _, rows_out = self._rows(report.get_lineup_stats_json_dict()['Braves'])
        by_key = {row['_lineup_key']: row['Lineup'] for row in rows_out}
        self.assertEqual(by_key['p1|p2|p3|p4|p5'], 'A#1-B-C-D-E')
        self.assertEqual(by_key['p2|p3|p4|p5|p7'], 'B-C-D-E-A#7')
        _, fours = self._rows(report.get_lineup_stats_json_dict(4)['Braves'])
        four_names = {row['Lineup'] for row in fours}
        self.assertIn('A#1-B-C-D', four_names)
        self.assertIn('B-C-D-A#7', four_names)
        view = report.get_play_by_play_df()
        self.assertIn('A#1, B, C, D, E', view['Braves'].tolist())
        self.assertIn('A#7, B, C, D, E', view['Braves'].tolist())
        entered = view[view['personId'] == 'p7'].iloc[0]
        self.assertEqual(entered['Player'], 'A')

    def test_dnp_teammate_suffixes_and_the_other_team_does_not(self):
        rows = [
            _event(eventType='period', subType='start', clock='PT12M0S', success=None, sequence=1),
            _event(clock='PT11M0S', sequence=2),
            _event(eventType='period', subType='end', entityId=None, clock='PT10M0S', success=None, sequence=3),
        ]
        roster = [
            {'personId': f'p{i}', 'shirtNumber': str(i), 'entityId': 'home'}
            for i in range(1, 6)
        ]
        roster.append({'personId': 'p8', 'shirtNumber': '8', 'entityId': 'home'})
        report = self._report(
            rows,
            {'home': ['p1', 'p2', 'p3', 'p4', 'p5']},
            id_table={'p8': 'A'},
            roster=roster,
        )
        _, rows_out = self._rows(report.get_lineup_stats_json_dict()['Braves'])
        self.assertEqual(rows_out[0]['Lineup'], 'A#1-B-C-D-E')

        other = [
            {'personId': f'p{i}', 'shirtNumber': str(i), 'entityId': 'home'}
            for i in range(1, 6)
        ]
        other.append({'personId': 'a9', 'shirtNumber': '9', 'entityId': 'away'})
        report = self._report(
            rows,
            {'home': ['p1', 'p2', 'p3', 'p4', 'p5']},
            id_table={'a9': 'A'},
            roster=other,
        )
        _, rows_out = self._rows(report.get_lineup_stats_json_dict()['Braves'])
        self.assertEqual(rows_out[0]['Lineup'], 'A-B-C-D-E')

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

    def test_opponent_totals_follow_the_lineup_on_the_floor(self):
        rows = [
            _event(eventType='period', subType='start', clock='PT12M0S', success=None, sequence=1),
            _event(clock='PT11M0S', sequence=2),
            _event(
                entityId='away', clock='PT10M0S', sequence=3,
                options={'pointsInThePaint': True, 'fastBreak': True},
            ),
            _event(
                entityId='away', eventType='rebound', subType='defensive',
                clock='PT9M30S', success=None, sequence=4,
            ),
            _event(
                entityId='away', eventType='assist', subType=None,
                clock='PT9M0S', success=None, sequence=5,
            ),
            _event(
                entityId='away', eventType='turnover', subType='badPass',
                clock='PT8M30S', success=None, sequence=6,
            ),
            _event(
                entityId='away', eventType='foul', subType='personal',
                clock='PT8M0S', success=None, sequence=7,
            ),
            _event(
                entityId='away', eventType='foul', subType='drawn',
                clock='PT7M30S', success=None, sequence=8,
            ),
            _event(eventType='period', subType='end', entityId=None, clock='PT7M0S', success=None, sequence=9),
        ]
        report = self._report(rows, {
            'home': ['p1', 'p2', 'p3', 'p4', 'p5'],
            'away': ['a1', 'a2', 'a3', 'a4', 'a5'],
        })
        _, rows_out = self._rows(report.get_lineup_stats_json_dict()['Braves'])
        first = next(row for row in rows_out if row['Lineup'] == 'A-B-C-D-E')
        self.assertEqual(first['Min'], '5:00')
        self.assertEqual(first['PTS'], 2)
        self.assertEqual(first['+/-'], 0)
        self.assertEqual(first['Opp_PTS'], 2)
        self.assertEqual(first['Opp_2M'], 1)
        self.assertEqual(first['Opp_2A'], 1)
        self.assertEqual(first['Opp_2FG%'], '1.000')
        self.assertEqual(first['Opp_3M'], '')
        self.assertEqual(first['Opp_FT%'], '')
        self.assertEqual(first['Opp_OR'], '')
        self.assertEqual(first['Opp_DR'], 1)
        self.assertEqual(first['Opp_REB'], 1)
        self.assertEqual(first['Opp_AST'], 1)
        self.assertEqual(first['Opp_TO'], 1)
        self.assertEqual(first['Opp_ST'], '')
        self.assertEqual(first['Opp_BS'], '')
        self.assertEqual(first['Opp_PF'], 1)
        self.assertEqual(first['Opp_FD'], 1)
        self.assertEqual(first['Opp_PIP'], 2)
        self.assertEqual(first['Opp_FBP'], 2)
        self.assertEqual(first['Opp_SCP'], '')
        self.assertEqual(first['Opp_POT'], '')
        self.assertEqual(first['Opp_PPP'], '1.00')

        _, fours = self._rows(report.get_lineup_stats_json_dict(4)['Braves'])
        shared = next(row for row in fours if row['Lineup'] == 'B-C-D-E')
        self.assertEqual(shared['Opp_PTS'], 2)
        self.assertEqual(shared['Opp_PPP'], '1.00')
        self.assertEqual(shared['Opp_AST'], 1)

    def test_report_lineup_payload_drops_opponent_columns(self):
        from synergy_reporter.report_components import report_table_payload

        plain = pd.DataFrame([{
            'Lineup': '林志傑-張宗憲',
            'PTS': '',
            '2FG%': '.000',
            'PPP': '0.00',
        }]).to_json(orient='split')
        kept = report_table_payload(
            {},
            {'Braves': plain},
            {'home_team': 'Braves', 'away_team': 'Dreamers'},
        )['lineup_home']
        self.assertEqual(kept, plain)

        wide = pd.DataFrame([{
            'Lineup': '林志傑-張宗憲',
            'PTS': 2,
            '2FG%': '.000',
            'PPP': '0.00',
            'Opp_PTS': 4,
            'Opp_PPP': '2.00',
        }]).to_json(orient='split')
        stripped_text = report_table_payload(
            {},
            {'5': {'Braves': wide}},
            {'home_team': 'Braves'},
        )['lineup_home']
        self.assertIn('林志傑', stripped_text)
        self.assertNotIn('\\u6797', stripped_text)
        stripped = json.loads(stripped_text)
        self.assertEqual(
            stripped['columns'],
            ['Lineup', 'PTS', '2FG%', 'PPP'],
        )
        keyed = pd.DataFrame([{
            'Lineup': '林志傑-張宗憲',
            'PTS': '',
            '2FG%': '.000',
            'PPP': '0.00',
            '_lineup_key': 'p1|p2',
        }]).to_json(orient='split')
        keyed_text = report_table_payload(
            {},
            {'5': {'Braves': keyed}},
            {'home_team': 'Braves'},
        )['lineup_home']
        keyed_payload = json.loads(keyed_text)
        self.assertEqual(keyed_payload['columns'], ['Lineup', 'PTS', '2FG%', 'PPP'])
        keyed_row = dict(zip(keyed_payload['columns'], keyed_payload['data'][0]))
        self.assertEqual(keyed_row['2FG%'], '.000')
        self.assertEqual(keyed_row['PPP'], '0.00')
        self.assertNotIn('_lineup_key', keyed_text)
        row = dict(zip(stripped['columns'], stripped['data'][0]))
        self.assertEqual(row['PTS'], 2)
        self.assertEqual(row['2FG%'], '.000')
        self.assertEqual(row['PPP'], '0.00')
        self.assertNotIn('Opp_PTS', row)

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
