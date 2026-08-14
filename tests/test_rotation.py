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

        self.assertEqual([b['label'] for b in payload['buckets']], ['1Q', '1Q'])
        home_player = payload['teams'][0]['players'][0]
        self.assertEqual(home_player['cells'][0], 1.0)
        self.assertEqual(home_player['cells'][1], 0.5)
        self.assertEqual(home_player['seconds'], 90)

    def test_score_margin_is_home_minus_away(self):
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
                'eventType': '2pt',
                'subType': None,
                'success': 1,
                'entityId': home,
                'personId': 'p1',
                'scores': json.dumps({home: 2, away: 0}),
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
                'scores': json.dumps({home: 2, away: 5}),
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
        self.assertIn((60, 2), margins)
        self.assertIn((120, -3), margins)
        self.assertEqual(payload['scoring']['home'], [None, 2])
        self.assertEqual(payload['scoring']['away'], [None, None])

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

    def test_dnp_sorted_last_and_jersey_label(self):
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
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1'], away: []},
            id_table={home: 'Home', away: 'Away', 'p1': 'On Court', 'p2': 'Bench'},
            home_team_id=home,
            away_team_id=away,
            roster=[
                {
                    'personId': 'p1',
                    'entityId': home,
                    'starter': True,
                    'participated': True,
                    'shirtNumber': '12',
                },
                {
                    'personId': 'p2',
                    'entityId': home,
                    'starter': False,
                    'participated': False,
                    'shirtNumber': '7',
                },
            ],
        )
        labels = [p['label'] for p in payload['teams'][0]['players']]
        self.assertEqual(labels, ['#12 On Court', '#7 Bench'])
        self.assertTrue(payload['teams'][0]['players'][1]['dnp'])
        self.assertTrue(all(cell is None for cell in payload['teams'][0]['players'][1]['cells']))

    def test_players_sorted_by_first_on_then_jersey(self):
        home, away = 'home-id', 'away-id'
        df = _pbp([
            {
                'periodId': 1,
                'clock': 'PT02M00S',
                'eventType': 'period',
                'subType': 'start',
                'entityId': home,
                'personId': None,
                'scores': None,
                home: ['late-starter', 'early-starter'],
                away: [],
            },
            {
                'periodId': 1,
                'clock': 'PT01M00S',
                'eventType': 'substitution',
                'subType': 'in',
                'entityId': home,
                'personId': 'bench',
                'scores': None,
                home: ['late-starter', 'early-starter', 'bench'],
                away: [],
            },
        ])
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['late-starter', 'early-starter'], away: []},
            id_table={
                home: 'Home',
                away: 'Away',
                'early-starter': 'Early',
                'late-starter': 'Late',
                'bench': 'Bench',
            },
            home_team_id=home,
            away_team_id=away,
            roster=[
                {'personId': 'late-starter', 'entityId': home, 'starter': True, 'shirtNumber': '23'},
                {'personId': 'early-starter', 'entityId': home, 'starter': True, 'shirtNumber': '5'},
                {'personId': 'bench', 'entityId': home, 'starter': False, 'shirtNumber': '1'},
            ],
        )
        labels = [p['label'] for p in payload['teams'][0]['players']]
        self.assertEqual(labels, ['#5 Early', '#23 Late', '#1 Bench'])


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
                    'players': [{'label': 'A', 'cells': [1, None]}],
                },
                {
                    'team_id': 'a',
                    'team_name': 'Away',
                    'side': 'away',
                    'players': [{'label': 'B', 'cells': [None, 1]}],
                },
            ],
            'margin': [{'t': 0.0, 'margin': 0}, {'t': 120.0, 'margin': 4}],
            'scoring': {'home': [1, 12], 'away': [None, 2]},
        }

    def test_score_heatmap_sits_below_margin(self):
        fig = build_rotation_figure(self._payload())
        score = next(trace for trace in fig.data if trace.type == 'heatmap' and trace.yaxis == 'y3')
        margin = next(trace for trace in fig.data if trace.type == 'scatter' and trace.mode == 'lines')
        self.assertEqual(margin.yaxis, 'y2')
        self.assertEqual(score.yaxis, 'y3')
        self.assertEqual(list(fig.layout.yaxis2.range), [-5, 5])
        self.assertEqual(fig.layout.yaxis3.autorange, 'reversed')

    def test_score_text_is_larger_and_contrasts_with_cell(self):
        z = [[1, 12], [None, 2]]
        colors = score_text_colors(z, 12)
        self.assertEqual(colors[0][0], '#1e293b')
        self.assertEqual(colors[0][1], '#ffffff')
        fig = build_rotation_figure(self._payload())
        labels = [trace for trace in fig.data if trace.type == 'scatter' and trace.mode == 'text']
        self.assertTrue(labels)
        self.assertEqual({trace.textfont.size for trace in labels}, {14})
        by_color = {trace.textfont.color: list(trace.text) for trace in labels}
        self.assertIn('12', by_color['#ffffff'])
        self.assertIn('1', by_color['#1e293b'])


if __name__ == '__main__':
    unittest.main()
