import json
import unittest

import pandas as pd

from synergy_reporter.rotation import (
    KILL_COLOR,
    KILL_ROW,
    LOWER_SEAM_INK,
    apply_camera_relayout,
    away_lane_height,
    build_rotation_figure,
    build_rotation_payload,
    report_rotation_figure,
    stop_seam_spacing,
    clamp_time_window,
    clock_to_seconds,
    contrast_text_color,
    detect_runs,
    format_kill_label,
    format_run_label,
    live_playhead_t,
    margin_tick_span,
    period_clock_label,
    period_for_window,
    period_label,
    relative_luminance,
    score_text_colors,
)


def _pbp(rows):
    return pd.DataFrame(rows)


def _kill_frame(home, away, rows):
    frame = []
    for row in rows:
        item = {
            'periodId': 1,
            'subType': None,
            'success': None,
            'entityId': home,
            'personId': None,
            'scores': None,
            home: ['p1'],
            away: ['p2'],
        }
        item.update(row)
        frame.append(item)
    return _pbp(frame)


def _kill_payload(home, away, rows):
    return build_rotation_payload(
        _kill_frame(home, away, rows),
        starter_dict={home: ['p1'], away: ['p2']},
        id_table={home: 'Home', away: 'Away', 'p1': 'A', 'p2': 'B'},
        home_team_id=home,
        away_team_id=away,
    )


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

    def test_score_label_uses_event_type_when_subtype_is_missing(self):
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
                'clock': 'PT01M30S',
                'eventType': '3pt',
                'success': 1,
                'entityId': home,
                'personId': 'p1',
                'scores': json.dumps({home: 3, away: 0}),
                home: ['p1'],
                away: ['p2'],
            },
            {
                'periodId': 1,
                'clock': 'PT01M00S',
                'eventType': 'freeThrow',
                'success': 1,
                'entityId': home,
                'personId': 'p1',
                'scores': json.dumps({home: 4, away: 0}),
                home: ['p1'],
                away: ['p2'],
            },
        ])
        missing = df.loc[df['eventType'].isin(['3pt', 'freeThrow']), 'subType']
        self.assertTrue(missing.map(lambda value: isinstance(value, float) and pd.isna(value)).all())
        payload = build_rotation_payload(
            df,
            starter_dict={home: ['p1'], away: ['p2']},
            id_table={home: 'Home', away: 'Away', 'p1': 'A', 'p2': 'B'},
            home_team_id=home,
            away_team_id=away,
        )
        descs = [point['desc'] for point in payload['margin']]
        self.assertIn('A 3PT', descs)
        self.assertIn('A FT', descs)

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


class KillDetectionTests(unittest.TestCase):
    def test_three_empty_opponent_trips_are_one_kill_when_we_score(self):
        home, away = 'home-id', 'away-id'
        payload = _kill_payload(home, away, [
            {'clock': 'PT02M00S', 'eventType': 'period', 'subType': 'start'},
            {'clock': 'PT01M40S', 'eventType': '2pt', 'success': 0, 'entityId': away},
            {'clock': 'PT01M30S', 'eventType': 'rebound', 'subType': 'defensive', 'entityId': home},
            {'clock': 'PT01M10S', 'eventType': '2pt', 'success': 1, 'entityId': home},
            {'clock': 'PT00M50S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'clock': 'PT00M30S', 'eventType': '2pt', 'success': 0, 'entityId': away},
            {'clock': 'PT00M10S', 'eventType': 'rebound', 'subType': 'defensive', 'entityId': home},
            {'clock': 'PT00M00S', 'eventType': 'period', 'subType': 'end', 'entityId': None},
        ])
        self.assertEqual(len(payload['kills']), 1)
        kill = payload['kills'][0]
        self.assertEqual(kill['side'], 'home')
        self.assertEqual(kill['stops'], 3)
        self.assertAlmostEqual(kill['start'], 20.0)
        self.assertAlmostEqual(kill['end'], 110.0)

    def test_one_made_free_throw_breaks_the_streak(self):
        home, away = 'home-id', 'away-id'
        payload = _kill_payload(home, away, [
            {'clock': 'PT02M00S', 'eventType': 'period', 'subType': 'start'},
            {'clock': 'PT01M50S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'clock': 'PT01M40S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'clock': 'PT01M20S', 'eventType': 'freeThrow', 'subType': '1Of1', 'success': 1, 'entityId': away},
            {'clock': 'PT01M00S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'clock': 'PT00M40S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
        ])
        self.assertEqual(payload['kills'], [])

    def test_five_stops_stay_one_kill_across_the_quarter(self):
        home, away = 'home-id', 'away-id'
        payload = _kill_payload(home, away, [
            {'periodId': 1, 'clock': 'PT01M00S', 'eventType': 'period', 'subType': 'start'},
            {'periodId': 1, 'clock': 'PT00M40S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'periodId': 1, 'clock': 'PT00M20S', 'eventType': '2pt', 'success': 1, 'entityId': home},
            {'periodId': 1, 'clock': 'PT00M05S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'periodId': 1, 'clock': 'PT00M00S', 'eventType': 'period', 'subType': 'end', 'entityId': None},
            {'periodId': 2, 'clock': 'PT01M00S', 'eventType': 'period', 'subType': 'start'},
            {'periodId': 2, 'clock': 'PT00M50S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'periodId': 2, 'clock': 'PT00M40S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'periodId': 2, 'clock': 'PT00M20S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
        ])
        self.assertEqual(len(payload['kills']), 1)
        kill = payload['kills'][0]
        self.assertEqual(kill['side'], 'home')
        self.assertEqual(kill['stops'], 5)
        self.assertAlmostEqual(kill['start'], 20.0)
        self.assertAlmostEqual(kill['end'], 100.0)

    def test_technical_free_throw_does_not_break_or_count(self):
        home, away = 'home-id', 'away-id'
        payload = _kill_payload(home, away, [
            {'clock': 'PT02M00S', 'eventType': 'period', 'subType': 'start'},
            {'clock': 'PT01M40S', 'eventType': '2pt', 'success': 0, 'entityId': away},
            {'clock': 'PT01M30S', 'eventType': 'rebound', 'subType': 'defensive', 'entityId': home},
            {'clock': 'PT01M10S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
            {'clock': 'PT01M00S', 'eventType': 'foul', 'subType': 'technical', 'entityId': home},
            {'clock': 'PT00M55S', 'eventType': 'freeThrow', 'subType': '1Of1', 'success': 1, 'entityId': away},
            {'clock': 'PT00M40S', 'eventType': 'turnover', 'subType': 'badPass', 'entityId': away},
        ])
        self.assertEqual(len(payload['kills']), 1)
        self.assertEqual(payload['kills'][0]['stops'], 3)
        self.assertEqual(payload['kills'][0]['side'], 'home')


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
        runs = detect_runs(events, min_delta=8)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['side'], 'home')
        self.assertEqual(runs[0]['home_pts'], 8)
        self.assertEqual(runs[0]['away_pts'], 0)
        self.assertEqual(runs[0]['end'], 90.0)

    def test_run_end_is_max_delta_not_trailing_opponent_points(self):
        events = [
            (0.0, 0, 0),
            (30.0, 8, 0),
            (60.0, 8, 2),
            (90.0, 8, 4),
        ]
        runs = detect_runs(events, min_delta=8)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['home_pts'], 8)
        self.assertEqual(runs[0]['away_pts'], 0)
        self.assertEqual(runs[0]['end'], 30.0)
        self.assertEqual(runs[0]['start'], 30.0)

    def test_run_start_trims_to_first_scorer_of_tight_window(self):
        events = [
            (0.0, 0, 0),
            (30.0, 3, 0),
            (230.0, 6, 0),
            (260.0, 11, 0),
        ]
        runs = detect_runs(events, min_delta=8)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['home_pts'], 8)
        self.assertEqual(runs[0]['away_pts'], 0)
        self.assertEqual(runs[0]['start'], 230.0)
        self.assertEqual(runs[0]['end'], 260.0)

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
        runs = detect_runs(events, min_delta=8)
        self.assertEqual(len(runs), 0)


    def test_figure_autosizes_without_fixed_width(self):
        fig = build_rotation_figure(self._payload())
        self.assertTrue(fig.layout.autosize)
        self.assertNotEqual(fig.layout.width, 1220)
        self.assertTrue(fig.layout.width in (None, 0) or fig.layout.width is False)
        self.assertEqual(fig.layout.dragmode, 'pan')
        self.assertEqual(fig.layout.xaxis.minallowed, 0)
        self.assertEqual(fig.layout.xaxis.maxallowed, 120)
        self.assertTrue(fig.layout.yaxis.fixedrange)
        self.assertTrue(fig.layout.yaxis2.fixedrange)
        self.assertTrue(fig.layout.yaxis3.fixedrange)

    def test_report_rotation_figure_has_no_playhead(self):
        fig = report_rotation_figure(self._payload())
        bar_y = [trace.y[0] for trace in fig.data if trace.type == 'bar']
        self.assertFalse(any(str(label).startswith('● ') for label in bar_y))
        vlines = [
            shape for shape in (fig.layout.shapes or [])
            if abs(float(getattr(shape, 'x0', -1)) - float(getattr(shape, 'x1', -2))) < 1e-6
        ]
        playhead_lines = [
            shape for shape in vlines
            if shape.line.color == '#0077b6' or shape.line.width == 2
        ]
        self.assertEqual(playhead_lines, [])
        opacities = [
            trace.marker.opacity for trace in fig.data
            if trace.type == 'bar' and getattr(trace, 'marker', None)
        ]
        self.assertTrue(opacities)
        self.assertTrue(all(opacity == 1.0 for opacity in opacities))
        self.assertEqual(fig.layout.font.size, 12)
        for ann in fig.layout.annotations or []:
            self.assertEqual(ann.font.size, 12)
        self.assertEqual(fig.layout.yaxis2.tickfont.size, 12)

    def test_report_rotation_right_margin_matches_name_lane(self):
        report = report_rotation_figure(self._payload())
        tab = build_rotation_figure(self._payload())
        self.assertEqual(report.layout.margin.l, 112)
        self.assertEqual(report.layout.margin.r, 112)
        self.assertEqual(report.layout.margin.t, 40)
        self.assertEqual(report.layout.margin.b, 48)
        self.assertEqual(list(report.layout.xaxis.range), [0, 120])
        self.assertEqual(tab.layout.margin.l, 112)
        self.assertEqual(tab.layout.margin.r, 112)

    def test_row_labels_repeat_on_the_right(self):
        fig = build_rotation_figure(self._payload(), playhead=30)
        report = report_rotation_figure(self._payload())

        def categories(axis):
            return list(axis.categoryarray or [])

        def numbers(axis):
            return [str(item) for item in (axis.ticktext or [])]

        self.assertEqual(fig.layout.yaxis4.side, 'right')
        self.assertEqual(fig.layout.yaxis4.overlaying, 'y')
        self.assertEqual(categories(fig.layout.yaxis4), ['3+ STOPS', '● A'])
        self.assertEqual(fig.layout.yaxis6.side, 'right')
        self.assertEqual(fig.layout.yaxis6.overlaying, 'y3')
        self.assertEqual(categories(fig.layout.yaxis6), ['  B', '3+ STOPS'])
        self.assertEqual(numbers(fig.layout.yaxis5), numbers(fig.layout.yaxis2))
        self.assertEqual(fig.layout.yaxis5.side, 'right')
        self.assertEqual(fig.layout.yaxis5.overlaying, 'y2')
        self.assertTrue(any(getattr(trace, 'yaxis', None) == 'y5' for trace in fig.data))
        self.assertTrue(any(getattr(trace, 'yaxis', None) == 'y5' for trace in report.data))
        self.assertEqual(categories(report.layout.yaxis4), ['3+ STOPS', 'A'])
        self.assertEqual(categories(report.layout.yaxis6), ['B', '3+ STOPS'])
        self.assertFalse(any('●' in label for label in categories(report.layout.yaxis4)))
        self.assertEqual(numbers(report.layout.yaxis5), numbers(report.layout.yaxis2))
        self.assertEqual(report.layout.yaxis5.tickfont.size, 12)
        self.assertEqual(fig.layout.yaxis5.tickfont.size, 10)

    def test_playhead_dims_bench_and_marks_on_court(self):
        payload = self._payload()
        fig = build_rotation_figure(payload, playhead=30.0)
        shapes = list(fig.layout.shapes or [])
        self.assertTrue(any(
            abs(getattr(shape, 'x0', -1) - 30.0) < 1e-6
            and abs(getattr(shape, 'x1', -1) - 30.0) < 1e-6
            for shape in shapes
        ))
        bar_y = [trace.y[0] for trace in fig.data if trace.type == 'bar']
        self.assertTrue(any(str(label).startswith('● ') for label in bar_y))

    def test_hides_dnp_rows_unless_requested(self):
        payload = self._payload()
        payload['teams'][0]['players'].append({
            'label': '#2 Sit',
            'dnp': True,
            'stints': [],
        })
        hidden = build_rotation_figure(payload, show_dnp=False)
        shown = build_rotation_figure(payload, show_dnp=True)
        def labels(fig):
            found = []
            for trace in fig.data:
                if getattr(trace, 'y', None):
                    found.extend(str(item) for item in trace.y)
            return found

        self.assertFalse(any('Sit' in label for label in labels(hidden)))
        self.assertTrue(any('Sit' in label for label in labels(shown)))

    def test_zoom_range_sets_xaxis(self):
        fig = build_rotation_figure(self._payload(), x_range=(10, 50))
        self.assertEqual(list(fig.layout.xaxis.range), [10, 50])

    def test_game_end_line_matches_quarter_dividers(self):
        payload = self._payload()
        payload['periods'] = [
            {'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0},
            {'id': 2, 'label': '2Q', 'seconds': 120, 'start': 120.0, 'end': 240.0},
        ]
        fig = build_rotation_figure(payload)
        report = report_rotation_figure(payload)

        def marks(figure):
            found = []
            for shape in figure.layout.shapes or []:
                x0 = float(getattr(shape, 'x0', -1))
                x1 = float(getattr(shape, 'x1', -2))
                if abs(x0 - x1) >= 1e-6:
                    continue
                found.append((
                    round(x0, 3),
                    shape.line.color,
                    shape.line.width,
                ))
            return found

        def at(figure, x):
            return [
                (color, width)
                for xpos, color, width in marks(figure)
                if xpos == x
            ]

        for figure in (fig, report):
            quarter = at(figure, 120.0)
            end = at(figure, 240.0)
            self.assertTrue(quarter)
            self.assertEqual(end, quarter)
            self.assertEqual(list(figure.layout.xaxis.range), [0, 240])


class KillFigureTests(unittest.TestCase):
    def _payload(self):
        return {
            'periods': [{'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0}],
            'teams': [
                {
                    'team_id': 'h',
                    'team_name': 'Home',
                    'side': 'home',
                    'players': [
                        {'label': 'A', 'stints': [{'start': 0.0, 'end': 40.0, 'pm': 2}]},
                        {'label': '#2 Sit', 'dnp': True, 'stints': []},
                    ],
                },
                {
                    'team_id': 'a',
                    'team_name': 'Away',
                    'side': 'away',
                    'players': [
                        {'label': 'B', 'stints': [{'start': 40.0, 'end': 120.0, 'pm': -2}]},
                        {'label': '#3 Sit', 'dnp': True, 'stints': []},
                    ],
                },
            ],
            'margin': [{'t': 0.0, 'margin': 0}, {'t': 120.0, 'margin': 4}],
            'runs': [{'side': 'home', 'home_pts': 10, 'away_pts': 0, 'start': 10.0, 'end': 100.0, 'delta': 10}],
            'kills': [
                {'side': 'home', 'stops': 3, 'start': 10.0, 'end': 50.0},
                {'side': 'home', 'stops': 4, 'start': 60.0, 'end': 80.0},
                {'side': 'away', 'stops': 3, 'start': 20.0, 'end': 70.0},
            ],
        }

    def _categories(self, fig, axis):
        return list(getattr(fig.layout[axis], 'categoryarray', None) or [])

    def _kill_bars(self, fig):
        return [
            trace for trace in fig.data
            if trace.type == 'bar' and trace.marker.color == KILL_COLOR
        ]

    def test_kill_rows_face_the_margin_and_keep_dnp_on_the_player_side(self):
        fig = build_rotation_figure(self._payload(), show_dnp=True, playhead=100.0)
        home = self._categories(fig, 'yaxis')
        away = self._categories(fig, 'yaxis3')
        self.assertEqual(home[0], KILL_ROW)
        self.assertIn('Sit', home[1])
        self.assertNotIn('●', home[0])
        self.assertEqual(away[-1], KILL_ROW)
        self.assertIn('Sit', away[0])
        self.assertEqual(self._categories(fig, 'yaxis4')[0], KILL_ROW)
        self.assertEqual(self._categories(fig, 'yaxis6')[-1], KILL_ROW)

    def test_kill_bars_are_red_above_the_run_and_do_not_dim(self):
        payload = self._payload()
        fig = build_rotation_figure(payload, playhead=100.0)
        bars = self._kill_bars(fig)
        self.assertEqual(len(bars), 3)
        for bar in bars:
            self.assertEqual(bar.marker.opacity, 1.0)
            self.assertEqual(bar.marker.line.width, 0)
        for bar in bars:
            self.assertFalse(bar.text)
        away_bar = next(bar for bar in bars if bar.yaxis == 'y3')
        self.assertIn('3 STOPS', away_bar.hovertext)
        counts = {
            round(float(ann.x), 5): ann
            for ann in fig.layout.annotations or []
            if ann.yref == 'paper' and str(ann.text or '').isdigit()
        }
        self.assertEqual(counts[30.0].text, '3')
        self.assertEqual(counts[70.0].text, '4')
        self.assertEqual(counts[45.0].text, '3')
        self.assertEqual(counts[30.0].font.color, KILL_COLOR)
        self.assertEqual(counts[30.0].font.size, 11)
        self.assertEqual(counts[30.0].yanchor, 'top')
        self.assertAlmostEqual(float(counts[30.0].y), fig.layout.yaxis.domain[0])
        self.assertEqual(counts[45.0].yanchor, 'bottom')
        self.assertAlmostEqual(float(counts[45.0].y), fig.layout.yaxis3.domain[1])
        run_labels = [
            ann for ann in fig.layout.annotations or []
            if ann.yref == 'y2' and ann.text and '10' in str(ann.text)
        ]
        self.assertEqual(run_labels[0].yanchor, 'bottom')
        self.assertEqual(run_labels[0].yshift, 2)
        washes = [
            shape for shape in fig.layout.shapes or []
            if getattr(shape, 'fillcolor', None) and shape.fillcolor.startswith('rgba(0, 119, 182')
        ]
        self.assertTrue(washes)
        player_bars = [
            trace for trace in fig.data
            if trace.type == 'bar' and trace.marker.color != KILL_COLOR and trace.y and 'A' in str(trace.y[0])
        ]
        self.assertTrue(player_bars)
        self.assertEqual(player_bars[0].marker.opacity, 0.32)

    def test_report_keeps_red_kill_labels_on_both_sides(self):
        fig = report_rotation_figure(self._payload())
        labels = [ann for ann in fig.layout.annotations or [] if ann.text == KILL_ROW]
        self.assertEqual(len(labels), 4)
        for ann in labels:
            self.assertEqual(ann.font.color, KILL_COLOR)
        self.assertEqual(list(fig.layout.yaxis.ticktext)[0], '')
        self.assertEqual(list(fig.layout.yaxis3.ticktext)[-1], '')
        counts = [
            ann for ann in fig.layout.annotations or []
            if ann.yref == 'paper' and str(ann.text or '').isdigit()
        ]
        self.assertEqual(len(counts), 3)
        for ann in counts:
            self.assertEqual(ann.font.color, KILL_COLOR)
            self.assertEqual(ann.font.size, 11)

    def test_a_team_with_no_kill_still_has_the_stops_row(self):
        payload = self._payload()
        payload['kills'] = []
        fig = build_rotation_figure(payload, show_dnp=True)
        self.assertEqual(self._categories(fig, 'yaxis')[0], KILL_ROW)
        self.assertEqual(self._categories(fig, 'yaxis3')[-1], KILL_ROW)
        self.assertEqual(KILL_ROW, '3+ STOPS')
        self.assertFalse(self._kill_bars(fig))
        labels = [ann for ann in fig.layout.annotations or [] if ann.text == KILL_ROW]
        self.assertEqual(len(labels), 4)

    def test_short_seam_grows_by_one_count_line(self):
        self.assertAlmostEqual(stop_seam_spacing(520), 0.06)
        plot_h = 400 - 40 - 48
        self.assertAlmostEqual(stop_seam_spacing(400) * plot_h, 0.06 * plot_h + 11)

    def _seam_px(self, fig, top_domain, bottom_domain):
        plot_h = float(fig.layout.height) - 40 - 48
        return (float(top_domain[0]) - float(bottom_domain[1])) * plot_h

    def test_away_title_sits_above_the_stop_count(self):
        fig = build_rotation_figure(self._payload(), playhead=100.0)
        base_plot = 520 - 40 - 48
        upper = self._seam_px(fig, fig.layout.yaxis.domain, fig.layout.yaxis2.domain)
        lower = self._seam_px(fig, fig.layout.yaxis2.domain, fig.layout.yaxis3.domain)
        self.assertAlmostEqual(upper, 0.06 * base_plot)
        self.assertAlmostEqual(lower, LOWER_SEAM_INK)
        self.assertAlmostEqual(fig.layout.height, away_lane_height(520))
        self.assertGreater(fig.layout.height, 520)
        away_title = next(ann for ann in fig.layout.annotations if ann.text == 'Away')
        home_title = next(ann for ann in fig.layout.annotations if ann.text == 'Home')
        self.assertEqual(away_title.yshift, 11)
        self.assertAlmostEqual(float(away_title.y), float(fig.layout.yaxis3.domain[1]))
        self.assertFalse(home_title.yshift)
        away_count = next(
            ann for ann in fig.layout.annotations
            if ann.text == '3' and ann.yanchor == 'bottom'
        )
        self.assertFalse(away_count.yshift)
        self.assertAlmostEqual(float(away_count.y), float(fig.layout.yaxis3.domain[1]))
        self.assertEqual(
            [round(float(value), 6) for value in fig.layout.yaxis6.domain],
            [round(float(value), 6) for value in fig.layout.yaxis3.domain],
        )

        bare_payload = self._payload()
        bare_payload['kills'] = []
        bare = build_rotation_figure(bare_payload)
        bare_title = next(ann for ann in bare.layout.annotations if ann.text == 'Away')
        self.assertEqual(bare_title.yshift, 11)
        self.assertAlmostEqual(bare.layout.height, fig.layout.height)

        report = report_rotation_figure(self._payload())
        report_title = next(ann for ann in report.layout.annotations if ann.text == 'Away')
        self.assertEqual(report_title.yshift, 11)
        self.assertEqual(report_title.font.size, 12)
        self.assertAlmostEqual(report.layout.height, fig.layout.height)

    def test_tall_figure_keeps_its_height_and_still_raises_the_away_title(self):
        payload = self._payload()
        players = [
            {'label': f'P{index}', 'stints': [{'start': 0.0, 'end': 60.0, 'pm': 0}]}
            for index in range(14)
        ]
        payload['teams'][0]['players'] = players
        payload['teams'][1]['players'] = list(players)
        fig = build_rotation_figure(payload)
        base = 15 * 22 + 15 * 22 + 200
        self.assertAlmostEqual(fig.layout.height, base)
        self.assertAlmostEqual(away_lane_height(base), base)
        away_title = next(ann for ann in fig.layout.annotations if ann.text == 'Away')
        self.assertEqual(away_title.yshift, 11)
        upper = self._seam_px(fig, fig.layout.yaxis.domain, fig.layout.yaxis2.domain)
        lower = self._seam_px(fig, fig.layout.yaxis2.domain, fig.layout.yaxis3.domain)
        self.assertAlmostEqual(lower, upper)
        self.assertGreaterEqual(lower, LOWER_SEAM_INK)


class RunLabelTests(unittest.TestCase):
    def test_same_period_omits_repeated_quarter(self):
        periods = [{'id': 1, 'label': '1Q', 'seconds': 720, 'start': 0.0, 'end': 720.0}]
        label = format_run_label(
            {'side': 'home', 'home_pts': 10, 'away_pts': 2, 'start': 96.0, 'end': 216.0},
            periods,
        )
        self.assertEqual(label, '1Q 10:24–08:24  10–2')

    def test_cross_period_keeps_both_quarter_labels(self):
        periods = [
            {'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0},
            {'id': 2, 'label': '2Q', 'seconds': 120, 'start': 120.0, 'end': 240.0},
        ]
        label = format_run_label(
            {'side': 'away', 'home_pts': 0, 'away_pts': 8, 'start': 90.0, 'end': 150.0},
            periods,
        )
        self.assertEqual(label, '1Q 00:30–2Q 01:30  8–0')

    def test_kill_label_counts_stops(self):
        periods = [{'id': 1, 'label': '1Q', 'seconds': 600, 'start': 0.0, 'end': 600.0}]
        label = format_kill_label(
            {'side': 'home', 'stops': 4, 'start': 96.0, 'end': 216.0},
            periods,
        )
        self.assertEqual(label, '1Q 08:24–06:24  4 STOPS')


class CameraWindowTests(unittest.TestCase):
    def test_clamp_stops_at_game_edges_and_keeps_width(self):
        self.assertEqual(clamp_time_window(-20, 100, 240, 120), (0.0, 120.0))
        self.assertEqual(clamp_time_window(150, 300, 240, 120), (120.0, 240.0))
        self.assertEqual(clamp_time_window(0, 240, 240, 120), (60.0, 180.0))

    def test_period_follows_majority_overlap_else_keeps_current(self):
        periods = [
            {'id': 1, 'start': 0.0, 'end': 120.0},
            {'id': 2, 'start': 120.0, 'end': 240.0},
        ]
        self.assertEqual(period_for_window(0, 120, periods, current='1'), '1')
        self.assertEqual(period_for_window(80, 200, periods, current='1'), '2')
        self.assertEqual(period_for_window(90, 150, periods, current='1'), '1')

    def test_relayout_keeps_slice_width_and_snaps_pinch(self):
        periods = [
            {'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0},
            {'id': 2, 'label': '2Q', 'seconds': 120, 'start': 120.0, 'end': 240.0},
        ]
        view = {
            'period': '1',
            'x0': 0.0,
            'x1': 120.0,
            'slice_width': 120.0,
            'axis_rev': 0,
        }
        panned = apply_camera_relayout(
            {'xaxis.range[0]': 80.0, 'xaxis.range[1]': 200.0}, view, periods,
        )
        self.assertEqual(panned['x0'], 80.0)
        self.assertEqual(panned['x1'], 200.0)
        self.assertEqual(panned['slice_width'], 120.0)
        self.assertEqual(panned['period'], '2')
        self.assertEqual(panned['axis_rev'], 0)
        pinched = apply_camera_relayout(
            {'xaxis.range': [0.0, 240.0]}, view, periods,
        )
        self.assertEqual(pinched['x1'] - pinched['x0'], 120.0)
        self.assertGreater(pinched['axis_rev'], 0)

    def test_all_mode_relayout_cannot_leave_full_game(self):
        periods = [{'id': 1, 'start': 0.0, 'end': 240.0}]
        view = {'period': 'all', 'x0': None, 'x1': None, 'slice_width': None, 'axis_rev': 0}
        out = apply_camera_relayout(
            {'xaxis.range[0]': 10.0, 'xaxis.range[1]': 130.0}, view, periods,
        )
        self.assertIsNone(out['x0'])
        self.assertIsNone(out['x1'])
        self.assertEqual(out['period'], 'all')
        self.assertGreater(out['axis_rev'], 0)


class LivePlayheadTests(unittest.TestCase):
    def test_skips_synthetic_game_end(self):
        t = live_playhead_t({
            'margin': [
                {'t': 0.0, 'desc': 'Game start'},
                {'t': 80.0, 'desc': 'Lin 3PT'},
                {'t': 120.0, 'desc': 'Game end'},
            ],
            'teams': [],
        })
        self.assertEqual(t, 80.0)


if __name__ == '__main__':
    unittest.main()


