import json
import unittest

import pandas as pd

from synergy_reporter.rotation import (
    build_rotation_figure,
    build_rotation_payload,
    clock_to_seconds,
    contrast_text_color,
    margin_tick_span,
    period_label,
    relative_luminance,
    score_text_colors,
)


def _pbp(rows):
    return pd.DataFrame(rows)


class MarginTickTests(unittest.TestCase):
    def test_span_is_multiple_of_five(self):
        self.assertEqual(margin_tick_span([0]), 5)
        self.assertEqual(margin_tick_span([3, -2]), 5)
        self.assertEqual(margin_tick_span([19]), 20)
        self.assertEqual(margin_tick_span([-20, 11]), 20)
        self.assertEqual(margin_tick_span([21]), 25)


class PeriodLabelTests(unittest.TestCase):
    def test_regulation_and_official_overtime(self):
        self.assertEqual(period_label(1), '1Q')
        self.assertEqual(period_label(4), '4Q')
        self.assertEqual(period_label(11), 'OT')
        self.assertEqual(period_label(12), '2OT')

    def test_legacy_period_five_still_reads_as_ot(self):
        self.assertEqual(period_label(5), 'OT')


class ClockTests(unittest.TestCase):
    def test_parses_synergy_clock(self):
        self.assertEqual(clock_to_seconds('PT10M00S'), 600)
        self.assertEqual(clock_to_seconds('PT00M30S'), 30)
        self.assertEqual(clock_to_seconds('PT09M05S'), 545)


class RotationPayloadTests(unittest.TestCase):
    def test_full_and_partial_minute_play_time(self):
        home, away = 'home-id', 'away-id'
        p1 = 'p1'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT02M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': None,
                home: [p1],
                away: [],
            },
            {
                'periodId': 1,
                'clock': 'PT00M30S',
                'eventType': 'substitution',
                'subType': 'out',
                'entityId': home,
                'personId': p1,
                'scores': None,
                home: [],
                away: [],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: [p1], away: []},
            id_table={home: 'Home', away: 'Away', p1: 'Starter'},
            home_team_id=home,
            away_team_id=away,
        )

        home_player = payload['teams'][0]['players'][0]
        self.assertEqual(len(home_player['stints']), 1)
        self.assertEqual(home_player['stints'][0], {'start': 0.0, 'end': 90.0, 'pm': 0})
        self.assertEqual(home_player['seconds'], 90)


    def test_score_margin_and_run_detection(self):
        home, away = 'home-id', 'away-id'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT02M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': json.dumps({home: 0, away: 0}),
                home: ['p1'],
                away: ['p2'],
            },
            {
                'periodId': 1,
                'clock': 'PT01M00S',
                'eventType': '3pt',
                'subType': None,
                'success': 1,
                'entityId': home,
                'personId': 'p1',
                'scores': json.dumps({home: 10, away: 2}),
                home: ['p1'],
                away: ['p2'],
            },
            {
                'periodId': 1,
                'clock': 'PT00M00S',
                'eventType': 'period',
                'subType': 'end',
                'entityId': None,
                'personId': None,
                'scores': json.dumps({home: 10, away: 2}),
                home: ['p1'],
                away: ['p2'],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1'], away: ['p2']},
            id_table={home: 'Home', away: 'Away', 'p1': 'A', 'p2': 'B'},
            home_team_id=home,
            away_team_id=away,
        )
        margins = {(round(p['t']), p['margin']) for p in payload['margin']}
        self.assertIn((0, 0), margins)
        self.assertIn((60, 8), margins)
        self.assertTrue(len(payload['runs']) >= 1)
        self.assertEqual(payload['runs'][0]['side'], 'home')
        self.assertEqual(payload['runs'][0]['home_pts'], 10)
        self.assertEqual(payload['runs'][0]['away_pts'], 2)

    def test_ot_appends_buckets_after_regulation(self):
        home, away = 'home-id', 'away-id'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT01M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': None,
                home: ['p1'],
                away: [],
            },
            {
                'periodId': 5,
                'clock': 'PT01M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': None,
                home: ['p1'],
                away: [],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1'], away: []},
            id_table={home: 'Home', away: 'Away', 'p1': 'A'},
            home_team_id=home,
            away_team_id=away,
        )
        self.assertEqual([b['period_label'] for b in payload['buckets']], ['1Q', 'OT'])

    def test_official_overtime_period_eleven_is_ot(self):
        home, away = 'home-id', 'away-id'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT01M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': None,
                home: ['p1'],
                away: [],
            },
            {
                'periodId': 11,
                'clock': 'PT01M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': None,
                home: ['p1'],
                away: [],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1'], away: []},
            id_table={home: 'Home', away: 'Away', 'p1': 'A'},
            home_team_id=home,
            away_team_id=away,
        )
        self.assertEqual([b['period_label'] for b in payload['buckets']], ['1Q', 'OT'])
        self.assertEqual(payload['teams'][0]['side'], 'home')
        self.assertEqual(payload['teams'][1]['side'], 'away')

    def test_players_sorted_by_first_on_then_jersey(self):
        home, away = 'home-id', 'away-id'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT10M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': None,
                'personId': None,
                'scores': None,
                home: ['p1', 'p2'],
                away: [],
            },
            {
                'periodId': 1,
                'clock': 'PT06M00S',
                'eventType': 'substitution',
                'subType': 'in',
                'entityId': home,
                'personId': 'p3',
                'scores': None,
                home: ['p1', 'p3'],
                away: [],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1', 'p2'], away: []},
            id_table={home: 'Home', away: 'Away', 'p1': 'Late', 'p2': 'Early', 'p3': 'Bench'},
            home_team_id=home,
            away_team_id=away,
            roster=[
                {'entityId': home, 'personId': 'p1', 'shirtNumber': 23, 'starter': True},
                {'entityId': home, 'personId': 'p2', 'shirtNumber': 5, 'starter': True},
                {'entityId': home, 'personId': 'p3', 'shirtNumber': 1, 'starter': False},
            ],
        )
        labels = [p['label'] for p in payload['teams'][0]['players']]
        self.assertEqual(labels, ['#5 Early', '#23 Late', '#1 Bench'])

    def test_dnp_sorted_last_and_jersey_label(self):
        home, away = 'home-id', 'away-id'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT10M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': None,
                'personId': None,
                'scores': None,
                home: ['p1'],
                away: [],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1'], away: []},
            id_table={home: 'Home', away: 'Away', 'p1': 'Active', 'p2': 'DNP'},
            home_team_id=home,
            away_team_id=away,
            roster=[
                {'entityId': home, 'personId': 'p1', 'shirtNumber': 10, 'starter': True},
                {'entityId': home, 'personId': 'p2', 'shirtNumber': 2, 'starter': False},
            ],
        )
        players = payload['teams'][0]['players']
        self.assertEqual([p['label'] for p in players], ['#10 Active', '#2 DNP'])
        self.assertFalse(players[0]['dnp'])
        self.assertTrue(players[1]['dnp'])


class ContrastTextTests(unittest.TestCase):
    def test_luminance_black_is_zero_white_is_one(self):
        self.assertAlmostEqual(relative_luminance('#000000'), 0.0, places=4)
        self.assertAlmostEqual(relative_luminance('#ffffff'), 1.0, places=4)

    def test_dark_fill_uses_white_text(self):
        self.assertEqual(contrast_text_color('rgb(8,48,107)'), '#ffffff')
        self.assertEqual(contrast_text_color('#1e293b'), '#ffffff')

    def test_light_fill_uses_dark_text(self):
        self.assertEqual(contrast_text_color('rgb(255,247,251)'), '#1e293b')
        self.assertEqual(contrast_text_color('#f8fafc'), '#1e293b')


class RotationFigureTests(unittest.TestCase):
    def _payload(self):
        return {
            'periods': [{'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0}],
            'buckets': [
                {'periodId': 1, 'period_label': '1Q', 'minute': 0, 'label': '1Q', 'start': 0.0, 'end': 60.0},
                {'periodId': 1, 'period_label': '1Q', 'minute': 1, 'label': '1Q', 'start': 60.0, 'end': 120.0},
            ],
            'teams': [
                {
                    'team_id': 'h',
                    'team_name': 'Home',
                    'side': 'home',
                    'players': [{'label': 'A', 'stints': [{'start': 0.0, 'end': 60.0}]}],
                },
                {
                    'team_id': 'a',
                    'team_name': 'Away',
                    'side': 'away',
                    'players': [{'label': 'B', 'stints': [{'start': 60.0, 'end': 120.0}]}],
                },
            ],
            'margin': [{'t': 0.0, 'margin': 0}, {'t': 120.0, 'margin': 4}],
            'runs': [{'side': 'home', 'home_pts': 10, 'away_pts': 2, 'start': 0.0, 'end': 60.0, 'delta': 8}],
        }

    def test_figure_structure_is_3_subpanels(self):
        payload = self._payload()
        payload['runs'] = [
            {'side': 'home', 'home_pts': 10, 'away_pts': 2, 'start': 0.0, 'end': 60.0, 'delta': 8},
            {'side': 'away', 'home_pts': 0, 'away_pts': 8, 'start': 60.0, 'end': 120.0, 'delta': 8},
        ]
        fig = build_rotation_figure(payload)
        # Y-axes: y (home gantt), y2 (margin), y3 (away gantt)
        margin_traces = [trace for trace in fig.data if trace.type == 'scatter' and trace.yaxis == 'y2']
        self.assertTrue(len(margin_traces) >= 3)  # positive fill, negative fill, and main step-line
        self.assertEqual(list(fig.layout.yaxis2.range), [-5, 5])
        bars = [trace for trace in fig.data if trace.type == 'bar']
        self.assertTrue(len(bars) >= 2)
        
        # Verify Home run annotation at top (y=5) and Away run annotation at bottom (y=-5)
        annotations = [ann for ann in fig.layout.annotations if ann.text in ('<b>10-2</b>', '<b>8-0</b>')]
        self.assertEqual(len(annotations), 2)
        home_ann = next(ann for ann in annotations if ann.text == '<b>10-2</b>')
        away_ann = next(ann for ann in annotations if ann.text == '<b>8-0</b>')
        self.assertEqual(home_ann.y, 5)
        self.assertEqual(home_ann.yanchor, 'bottom')
        self.assertEqual(away_ann.y, -5)
        self.assertEqual(away_ann.yanchor, 'top')



    def test_momentum_run_breaks_when_opponent_answers_with_4_pts(self):
        home, away = 'home-id', 'away-id'
        # Home goes on 8-0 run, then away scores 4 consecutive points
        events = [
            (0.0, 0, 0),
            (30.0, 3, 0),
            (60.0, 6, 0),
            (90.0, 8, 0),    # Home 8-0 run (delta=8)
            (120.0, 8, 2),   # Away +2
            (150.0, 8, 5),   # Away +3 (total 5 consecutive -> momentum broken!)
            (180.0, 11, 5),
        ]
        from synergy_reporter.rotation import detect_runs
        runs = detect_runs(events, min_delta=8)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['side'], 'home')
        self.assertEqual(runs[0]['home_pts'], 8)
        self.assertEqual(runs[0]['away_pts'], 0)
        self.assertEqual(runs[0]['end'], 90.0)

    def test_run_excludes_slow_blowout_with_high_opponent_scoring(self):
        # 27-18 (delta=9, but opponent scored 18 points) should NOT be considered a Run
        events = [
            (0.0, 0, 0),
            (60.0, 3, 2),
            (120.0, 6, 4),
            (180.0, 9, 6),
            (240.0, 12, 8),
            (300.0, 15, 10),
            (360.0, 18, 12),
            (420.0, 21, 14),
            (480.0, 24, 16),
            (540.0, 27, 18),
        ]
        from synergy_reporter.rotation import detect_runs
        runs = detect_runs(events, min_delta=8)
        self.assertEqual(len(runs), 0)


    def test_figure_autosizes_without_fixed_width(self):
        fig = build_rotation_figure(self._payload())
        self.assertTrue(fig.layout.autosize)
        self.assertNotEqual(fig.layout.width, 1220)
        self.assertTrue(fig.layout.width in (None, 0) or fig.layout.width is False)
        self.assertEqual(fig.layout.dragmode, 'pan')
        self.assertEqual(fig.layout.xaxis.minallowed, 0)
        self.assertEqual(fig.layout.xaxis.maxallowed, 135)
        self.assertTrue(fig.layout.yaxis.fixedrange)
        self.assertTrue(fig.layout.yaxis2.fixedrange)
        self.assertTrue(fig.layout.yaxis3.fixedrange)


if __name__ == '__main__':
    unittest.main()


