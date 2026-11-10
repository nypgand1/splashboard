# -*- coding: utf-8 -*-
import unittest

import pandas as pd

from synergy_inbounder.parser import Parser
from synergy_inbounder.http_wave import run_wave
from synergy_reporter.team_rotation import (
    SELECTED_COLOR,
    SELECTED_FILL,
    OPPONENT_COLOR,
    OPPONENT_FILL,
    aggregate_games,
    build_team_rotation_figure,
    clear_rotation_cache,
    infer_opening_five,
    prepare_game,
    season_aggregate,
)


def _event(clock, entity, person, event='2pt', sub=''):
    return {
        'periodId': 1,
        'clock': clock,
        'eventType': event,
        'subType': sub,
        'entityId': entity,
        'personId': person,
        'scores': {'h': 0, 'a': 0},
    }


def _opening_game(extra, fixture_id='g'):
    rows = [_event(720, 'h', person) for person in ('p1', 'p2', 'p3', 'p4', 'p5')]
    rows.extend(_event(720, 'a', person) for person in ('q1', 'q2', 'q3', 'q4', 'q5'))
    rows.extend(extra)
    rows.append(_event(0, 'h', 'p1'))
    return {
        'fixture_id': fixture_id,
        'home': 'h',
        'away': 'a',
        'status': 'FINISHED',
        'pbp': pd.DataFrame(rows),
    }


def _player_seconds(result, person):
    row = next(item for item in result['players'] if item['person_id'] == person)
    return row['seconds']


def _frame(periods, score, players):
    rows = []
    for period in periods:
        rows.append({
            'periodId': period,
            'clock': 0,
            'eventType': '2pt',
            'subType': '',
            'entityId': 'h',
            'personId': players['h'][0],
            'h': list(players['h']),
            'a': list(players['a']),
            'scores': score,
        })
    return pd.DataFrame(rows)


def _prepared(periods, score, players=None):
    players = players or {'h': ['p1', 'p2'], 'a': ['q1']}
    return {
        'home': 'h',
        'away': 'a',
        'frame': _frame(periods, score, players),
        'starters': {'h': list(players['h']), 'a': list(players['a'])},
    }


class StarterRowsTests(unittest.TestCase):
    def test_team_ids_keep_an_empty_side(self):
        rows = [{'personId': 'p1', 'entityId': 'h', 'starter': True}]
        self.assertEqual(
            Parser.starter_dict_from_rows(rows, ['h', 'a']),
            {'h': ['p1'], 'a': []},
        )

    def test_without_team_ids_only_starter_teams_remain(self):
        rows = [
            {'personId': 'p1', 'entityId': 'h', 'starter': True},
            {'personId': None, 'entityId': 'h', 'starter': True},
            {'personId': 'q1', 'entityId': 'a', 'starter': False},
        ]
        self.assertEqual(Parser.starter_dict_from_rows(rows), {'h': ['p1']})


class OpeningFiveTests(unittest.TestCase):
    def _events(self, people, sub_in=()):
        rows = []
        for person in people:
            rows.append({
                'entityId': 'h',
                'personId': person,
                'eventType': '2pt',
                'subType': '',
            })
        for person in sub_in:
            rows.append({
                'entityId': 'h',
                'personId': person,
                'eventType': 'substitution',
                'subType': 'in',
            })
        return pd.DataFrame(rows)

    def test_five_openers_are_the_group(self):
        frame = self._events(['p1', 'p2', 'p3', 'p4', 'p5'], sub_in=['p6'])
        self.assertEqual(infer_opening_five(frame, 'h'), ['p1', 'p2', 'p3', 'p4', 'p5'])

    def test_more_than_five_openers_is_unresolved(self):
        frame = self._events(['p1', 'p2', 'p3', 'p4', 'p5', 'p6'])
        self.assertIsNone(infer_opening_five(frame, 'h'))

    def test_a_substitution_in_does_not_count_as_an_opener(self):
        frame = self._events(['p1', 'p2', 'p3', 'p4'], sub_in=['p5'])
        self.assertIsNone(infer_opening_five(frame, 'h'))


class AggregateTests(unittest.TestCase):
    def setUp(self):
        clear_rotation_cache()

    def _aggregate(self, games, selected='h', opponent='all', minutes=4):
        return aggregate_games(
            games, selected, opponent, minutes,
            {'p1': 'Ann Lee', 'p2': 'Bob Chen', 'q1': 'Cara Wu', 'p9': 'Dee Ko'},
            {'h': {'p1': 12, 'p2': 4, 'p9': 99}, 'a': {'q1': 8}},
        )

    def test_rate_is_seconds_over_sixty_over_n_and_zero_seconds_drop(self):
        result = self._aggregate([_prepared([1, 2, 3, 4], {'h': 0, 'a': 0})])
        self.assertEqual(result['n'], 1)
        self.assertEqual(result['players'][0]['rates'][0], 1.0)
        self.assertNotIn('p9', [row['person_id'] for row in result['players']])
        self.assertEqual(result['opponent_players'], [])

    def test_same_minutes_sort_by_jersey_then_name(self):
        result = self._aggregate([_prepared([1], {'h': 0, 'a': 0})])
        self.assertEqual(
            [row['person_id'] for row in result['players']],
            ['p2', 'p1'],
        )

    def test_first_minute_rate_outranks_later_minutes(self):
        games = [
            _prepared([1], {'h': 0, 'a': 0}, {'h': ['p1'], 'a': ['q1']}),
            _prepared([2, 3, 4], {'h': 0, 'a': 0}, {'h': ['p2'], 'a': ['q1']}),
        ]
        result = self._aggregate(games)
        order = [row['person_id'] for row in result['players']]
        self.assertEqual(order, ['p1', 'p2'])
        self.assertGreater(
            result['players'][1]['seconds'], result['players'][0]['seconds'],
        )

    def test_a_tied_minute_compares_the_next_minute(self):
        games = [
            _prepared([1], {'h': 0, 'a': 0}, {'h': ['p1', 'p2'], 'a': ['q1']}),
            _prepared([2], {'h': 0, 'a': 0}, {'h': ['p1'], 'a': ['q1']}),
        ]
        result = self._aggregate(games)
        self.assertEqual(
            [row['rates'][0] for row in result['players']],
            [1.0, 1.0],
        )
        self.assertEqual(
            [row['person_id'] for row in result['players']],
            ['p1', 'p2'],
        )

    def test_opponent_rows_use_the_same_minute_order(self):
        games = [
            _prepared([1], {'h': 0, 'a': 0}, {'h': ['p1'], 'a': ['q1']}),
            _prepared([2, 3, 4], {'h': 0, 'a': 0}, {'h': ['p1'], 'a': ['q2']}),
        ]
        result = aggregate_games(
            games, 'h', 'a', 4,
            {'p1': 'Ann Lee', 'q1': 'Cara Wu', 'q2': 'Bea Ho'},
            {'h': {'p1': 12}, 'a': {'q1': 8, 'q2': 1}},
        )
        self.assertEqual(
            [row['person_id'] for row in result['opponent_players']],
            ['q1', 'q2'],
        )

    def test_overtime_n_is_only_the_games_that_reached_it(self):
        games = [
            _prepared([1, 2, 3, 4, 11], {'h': 4, 'a': 0}),
            _prepared([1, 2, 3, 4], {'h': 2, 'a': 0}),
        ]
        result = self._aggregate(games)
        self.assertEqual(result['n'], 2)
        ot = next(point for point in result['margin'] if point['period'] == 11)
        self.assertEqual(ot['n'], 1)
        segments = []
        # The OT piece starts at that period's own start margin and is not
        # joined to the regulation mean.
        from synergy_reporter.team_rotation import _segments
        segments = _segments(result['margin'])
        self.assertGreaterEqual(len(segments), 2)
        self.assertEqual(segments[-1][0], (4, 4.0))
        self.assertEqual(segments[0][-1][1], 3.0)

    def test_selected_away_negates_the_home_margin(self):
        result = self._aggregate(
            [_prepared([1, 2, 3, 4], {'h': 4, 'a': 0})], selected='a',
        )
        self.assertEqual(result['margin'][0]['y'], -4.0)

    def test_a_missing_frame_stays_out_of_n(self):
        result = self._aggregate([
            {'frame': None, 'home': 'h', 'away': 'a', 'starters': {}},
            _prepared([1, 2, 3, 4], {'h': 0, 'a': 0}),
        ])
        self.assertEqual(result['n'], 1)

    def test_named_opponent_keeps_its_own_rows(self):
        result = self._aggregate(
            [_prepared([1], {'h': 0, 'a': 0})], opponent='a',
        )
        self.assertEqual([row['person_id'] for row in result['opponent_players']], ['q1'])

    def test_official_starter_with_seconds_keeps_the_game(self):
        frame = pd.DataFrame([{
            'periodId': 1,
            'clock': 0,
            'eventType': '2pt',
            'subType': '',
            'entityId': 'h',
            'personId': 'p1',
        }])
        game = {
            'fixture_id': 'g', 'home': 'h', 'away': 'a',
            'pbp': frame, 'status': 'FINISHED',
        }
        called = []

        def fetch(org, fixture, status):
            called.append(fixture)
            return {'h': ['p1'], 'a': ['q1']}

        ready = prepare_game('org', game, fetch_starters=fetch)
        self.assertIsNotNone(ready)
        self.assertEqual(called, ['g'])
        result = aggregate_games([ready], 'h', 'all', 4, {}, None)
        self.assertEqual(result['n'], 1)
        self.assertGreater(result['players'][0]['seconds'], 0)
        called.clear()
        self.assertIsNotNone(prepare_game('org', game, fetch_starters=fetch))
        self.assertEqual(called, [])

    def test_selected_team_with_no_seconds_is_dropped(self):
        frame = pd.DataFrame([{
            'periodId': 1,
            'clock': 0,
            'eventType': '2pt',
            'subType': '',
            'entityId': 'h',
            'personId': 'p1',
        }])
        game = {
            'fixture_id': 'drop', 'home': 'h', 'away': 'a',
            'pbp': frame, 'status': 'FINISHED',
        }
        called = []

        def fetch(org, fixture, status):
            called.append(fixture)
            return {'a': ['q1', 'q2', 'q3', 'q4', 'q5']}

        self.assertIsNone(
            prepare_game('org', game, fetch_starters=fetch, selected_id='h'),
        )
        self.assertEqual(called, ['drop'])

    def test_same_clock_substitution_stays_in_n(self):
        game = _opening_game([
            _event(480, 'h', 'p5', 'substitution', 'out'),
            _event(480, 'h', 'p6', 'substitution', 'in'),
        ])

        def fetch(*_args):
            raise AssertionError('lineup already has on-court seconds')

        ready = prepare_game('org', game, fetch_starters=fetch)
        self.assertIsNotNone(ready)
        lengths = [
            len(players) for players in ready['frame']['h']
            if isinstance(players, list)
        ]
        self.assertIn(4, lengths)
        result = aggregate_games([ready], 'h', 'all', 48, {}, None)
        self.assertEqual(result['n'], 1)
        self.assertEqual(_player_seconds(result, 'p5'), 240)
        self.assertEqual(_player_seconds(result, 'p6'), 480)

    def test_clock_advancing_six_counts(self):
        game = _opening_game([
            _event(600, 'h', 'p6', 'substitution', 'in'),
            _event(480, 'h', 'p5', 'substitution', 'out'),
        ], fixture_id='six')

        def fetch(*_args):
            raise AssertionError('lineup already has on-court seconds')

        ready = prepare_game('org', game, fetch_starters=fetch)
        self.assertIsNotNone(ready)
        lengths = [
            len(players) for players in ready['frame']['h']
            if isinstance(players, list)
        ]
        self.assertIn(6, lengths)
        result = aggregate_games([ready], 'h', 'all', 48, {}, None)
        self.assertEqual(result['n'], 1)
        self.assertEqual(_player_seconds(result, 'p5'), 240)
        self.assertEqual(_player_seconds(result, 'p6'), 600)

    def test_cached_walk_without_selected_seconds_fetches_again(self):
        frame = pd.DataFrame([{
            'periodId': 1,
            'clock': 0,
            'eventType': '2pt',
            'subType': '',
            'entityId': 'h',
            'personId': 'p1',
        }])
        game = {
            'fixture_id': 'cache', 'home': 'h', 'away': 'a',
            'pbp': frame, 'status': 'FINISHED',
        }
        calls = []

        def fetch(org, fixture, status):
            calls.append(fixture)
            if len(calls) == 1:
                return {'h': ['p1']}
            return {'a': ['q1']}

        self.assertIsNotNone(
            prepare_game('org', game, fetch_starters=fetch, selected_id='h'),
        )
        ready = prepare_game('org', game, fetch_starters=fetch, selected_id='a')
        self.assertIsNotNone(ready)
        self.assertEqual(calls, ['cache', 'cache'])

    def test_named_opponent_without_seconds_omits_the_band(self):
        frame = pd.DataFrame([{
            'periodId': 1,
            'clock': 0,
            'eventType': '2pt',
            'subType': '',
            'entityId': 'h',
            'personId': 'p1',
            'h': ['p1', 'p2'],
            'scores': {'h': 0, 'a': 0},
        }])
        result = aggregate_games(
            [{
                'home': 'h',
                'away': 'a',
                'frame': frame,
                'starters': {'h': ['p1', 'p2']},
            }],
            'h', 'a', 4,
            {'p1': 'Ann Lee', 'p2': 'Bob Chen'},
            {'h': {'p1': 12, 'p2': 4}},
        )
        self.assertEqual(result['n'], 1)
        self.assertTrue(result['players'])
        self.assertEqual(result['opponent_players'], [])
        self.assertIsNone(result['opponent'])
        self.assertTrue(result['margin'])
        figure = build_team_rotation_figure(result, 'Aces', 'Braves')
        heats = [trace for trace in figure.data if trace.type == 'heatmap']
        self.assertEqual(len(heats), 1)


class FigureTests(unittest.TestCase):
    def test_heatmap_uses_one_shared_scale(self):
        aggregate = aggregate_games(
            [_prepared([1], {'h': 2, 'a': 0})],
            'h', 'a', 4, {}, {'h': {'p1': 4, 'p2': 12}, 'a': {'q1': 8}},
        )
        aggregate['margin'][0]['start'] = 4
        aggregate['margin'][0]['y'] = -3
        figure = build_team_rotation_figure(aggregate, 'Aces', 'Braves')
        heats = [trace for trace in figure.data if trace.type == 'heatmap']
        self.assertEqual(len(heats), 2)
        self.assertIn(SELECTED_COLOR, str(heats[0].colorscale))
        self.assertIn(OPPONENT_COLOR, str(heats[1].colorscale))
        self.assertEqual(OPPONENT_COLOR, '#94a3b8')
        self.assertEqual(heats[0].zmin, 0)
        self.assertEqual(heats[0].zmax, 1)
        self.assertEqual(figure.layout.margin.l, 112)
        self.assertEqual(figure.layout.margin.r, 112)
        self.assertEqual(figure.layout.margin.t, 40)
        self.assertEqual(figure.layout.margin.b, 48)
        self.assertEqual(figure.layout.font.size, 12)
        self.assertEqual(figure.layout.font.color, '#334155')
        self.assertEqual(figure.layout.yaxis.tickfont.size, 12)
        self.assertEqual(figure.layout.yaxis.tickfont.color, '#334155')
        self.assertEqual(figure.layout.yaxis.title.text, '')
        self.assertEqual(figure.layout.yaxis4.side, 'right')
        self.assertEqual(list(figure.layout.yaxis4.ticktext), list(figure.layout.yaxis.ticktext))
        self.assertEqual(figure.layout.yaxis2.tickfont.size, 10)
        self.assertEqual(figure.layout.yaxis2.zerolinecolor, '#475569')
        self.assertGreaterEqual(figure.layout.height, 520)
        titles = [ann for ann in figure.layout.annotations if ann.text]
        self.assertEqual(titles[0].text, 'Aces')
        self.assertEqual(titles[-1].text, 'Braves')
        self.assertEqual(titles[0].font.size, 14)
        self.assertEqual(titles[0].font.color, '#1e293b')
        fills = [trace.fillcolor for trace in figure.data if getattr(trace, 'fill', None) == 'tozeroy']
        self.assertIn(SELECTED_FILL, fills)
        self.assertIn(OPPONENT_FILL, fills)
        steps = [trace for trace in figure.data if getattr(trace, 'fill', None) == 'tozeroy']
        self.assertTrue(steps)
        self.assertTrue(all(trace.line.shape == 'hv' for trace in steps))
        self.assertEqual(heats[0].xgap, 1)
        self.assertEqual(heats[0].ygap, 1)
        self.assertTrue(all(not ann.yshift for ann in titles))
        self.assertIs(figure.layout.dragmode, False)
        for name in (
            'xaxis', 'xaxis2', 'xaxis3',
            'yaxis', 'yaxis2', 'yaxis3', 'yaxis4', 'yaxis5', 'yaxis6',
        ):
            self.assertIs(figure.layout[name].fixedrange, True)

    def test_period_labels_are_centered_and_rules_mark_later_edges(self):
        columns = []
        for period in (1, 2, 3, 4):
            for minute in range(12):
                columns.append({'period': period, 'minute': minute})
        columns.append({'period': 11, 'minute': 0})
        columns.append({'period': 11, 'minute': 1})
        columns.append({'period': 11, 'minute': 2})
        aggregate = {
            'columns': columns,
            'players': [{'label': '#4 Ann', 'rates': [1.0] * len(columns)}],
            'opponent_players': [{'label': '#8 Bea', 'rates': [0.5] * len(columns)}],
            'opponent': 'a',
            'lengths': {1: 12, 2: 12, 3: 12, 4: 12, 11: 3},
            'counts': [1] * len(columns),
            'clock': lambda *_args: '1Q 12:00–11:00',
            'margin': [
                {
                    'n': 1,
                    'y': 2.0,
                    'start': 1.0,
                    'period': column['period'],
                    'minute': column['minute'],
                }
                for column in columns
            ],
        }
        figure = build_team_rotation_figure(aggregate, 'Aces', 'Braves')
        self.assertEqual(list(figure.layout.xaxis3.ticktext), ['1Q', '2Q', '3Q', '4Q', 'OT'])
        self.assertEqual(list(figure.layout.xaxis3.tickvals), [5.5, 17.5, 29.5, 41.5, 49.0])
        self.assertFalse(figure.layout.xaxis.showticklabels)
        self.assertFalse(figure.layout.xaxis2.showticklabels)
        rules = sorted({
            round(float(shape.x0), 3)
            for shape in figure.layout.shapes or []
            if abs(float(shape.x0) - float(shape.x1)) < 1e-6
            and shape.line.color == '#94a3b8'
            and shape.line.width == 1
        })
        self.assertEqual(rules, [11.5, 23.5, 35.5, 47.5, 50.5])
        self.assertNotIn(-0.5, rules)
        self.assertEqual(figure.layout.height, 520)

    def test_one_band_skips_the_gantt_clamp(self):
        from synergy_reporter.team_rotation import _band_layout, _step_runs

        height, weights = _band_layout(12, 0)
        self.assertEqual(height, 520)
        self.assertAlmostEqual(weights[0], (12 * 22) / (12 * 22 + 180))
        self.assertAlmostEqual(sum(weights), 1.0)
        both_height, both = _band_layout(12, 12)
        self.assertEqual(both_height, 12 * 22 + 12 * 22 + 200)
        self.assertGreaterEqual(both[0], 0.25)
        self.assertLessEqual(both[0], 0.45)
        self.assertGreaterEqual(both[1], 0.18)
        tall = {
            'columns': [{'period': 1, 'minute': 0}],
            'players': [
                {'label': '#{0}'.format(index), 'rates': [1.0]}
                for index in range(12)
            ],
            'opponent_players': [
                {'label': 'O{0}'.format(index), 'rates': [1.0]}
                for index in range(12)
            ],
            'opponent': 'a',
            'lengths': {1: 1},
            'counts': [1],
            'clock': lambda *_args: '1Q 12:00–11:00',
            'margin': [{'n': 1, 'y': 1.0, 'start': 0.0, 'period': 1, 'minute': 0}],
        }
        self.assertEqual(
            build_team_rotation_figure(tall, 'Aces', 'Braves').layout.height,
            both_height,
        )
        solo_players = [
            {'label': '#{0}'.format(index), 'rates': [1.0]}
            for index in range(15)
        ]
        solo = build_team_rotation_figure({
            'columns': [{'period': 1, 'minute': 0}],
            'players': solo_players,
            'opponent_players': [],
            'opponent': None,
            'lengths': {1: 1},
            'counts': [1],
            'clock': lambda *_args: '1Q 12:00–11:00',
            'margin': [{'n': 1, 'y': 1.0, 'start': 0.0, 'period': 1, 'minute': 0}],
        }, 'Aces')
        self.assertEqual(solo.layout.height, 15 * 22 + 200)
        top_span = solo.layout.yaxis.domain[1] - solo.layout.yaxis.domain[0]
        margin_span = solo.layout.yaxis2.domain[1] - solo.layout.yaxis2.domain[0]
        self.assertAlmostEqual(
            solo.layout.yaxis.domain[0] - solo.layout.yaxis2.domain[1],
            0.06,
        )
        self.assertAlmostEqual(
            top_span / (top_span + margin_span),
            (15 * 22) / (15 * 22 + 180),
            places=3,
        )
        runs = _step_runs([(0, 4.0), (1, -3.0)])
        self.assertEqual(runs, [
            ('pos', [(0, 4.0), (1, 0)]),
            ('neg', [(1, 0), (1, -3.0)]),
        ])
        self.assertEqual(
            _step_runs([(0, 4.0), (1, 0), (2, 2.0)]),
            [('pos', [(0, 4.0), (1, 0), (2, 2.0)])],
        )


def _stats_rows():
    rows = []
    for person, number in (
        ('p1', '7'), ('p2', '4'), ('p3', '11'), ('p4', '8'), ('p5', '15'),
        ('q1', '9'), ('q2', '12'), ('q3', '3'), ('q4', '21'), ('q5', '6'),
    ):
        rows.append({
            'personId': person,
            'entityId': 'h' if person.startswith('p') else 'a',
            'shirtNumber': number,
            'starter': True,
        })
    return rows


def _season_source(games, opponent='all'):
    return {
        'org_id': 'org',
        'team': 'h',
        'opponent': opponent,
        'minutes': 48,
        'id_table': {
            'p1': 'Ann Lee',
            'p2': 'Bob Chen',
            'q1': 'Cara Wu',
        },
        'games': games,
    }


class SeasonAggregateTests(unittest.TestCase):
    def setUp(self):
        clear_rotation_cache()

    def test_empty_roster_keeps_player_stats_bib_and_walks_once(self):
        from unittest.mock import patch

        from synergy_reporter import rotation as rotation_module

        source = _season_source([_opening_game([], fixture_id='g')])
        roster_calls = []
        stat_calls = []

        def fetch_roster(_org, fixture, _status):
            roster_calls.append(fixture)
            return {'data': []}

        def fetch_rows(_org, fixture, _status):
            stat_calls.append(fixture)
            return [row for row in _stats_rows() if row['personId'] != 'p2']

        with patch.object(rotation_module, 'detect_runs') as runs, \
                patch.object(rotation_module, 'possession_trips') as trips, \
                patch(
                    'synergy_reporter.team_rotation.build_rotation_payload',
                    wraps=rotation_module.build_rotation_payload,
                ) as built, \
                patch(
                    'synergy_reporter.team_rotation.run_wave',
                    wraps=run_wave,
                ) as wave:
            result = season_aggregate(
                source, fetch_roster=fetch_roster, fetch_player_rows=fetch_rows,
            )
            walked = built.call_count
            waves = wave.call_count
            again = season_aggregate(
                source, fetch_roster=fetch_roster, fetch_player_rows=fetch_rows,
            )
        self.assertEqual(roster_calls, ['g'])
        self.assertEqual(stat_calls, ['g'])
        self.assertEqual(waves, 1)
        self.assertEqual(built.call_count, walked)
        self.assertFalse(runs.called)
        self.assertFalse(trips.called)
        self.assertEqual(result['n'], again['n'])
        label = next(row['label'] for row in result['players'] if row['person_id'] == 'p1')
        self.assertTrue(label.startswith('#7 '))
        bare = next(row['label'] for row in result['players'] if row['person_id'] == 'p2')
        self.assertFalse(bare.startswith('#'))

    def test_roster_bib_wins_and_a_later_filter_does_not_fetch(self):
        source = _season_source([
            _opening_game([], fixture_id='g1'),
            _opening_game([], fixture_id='g2'),
        ])
        calls = []

        def fetch_roster(_org, fixture, _status):
            calls.append(('roster', fixture))
            if fixture == 'g1':
                return {'data': [{
                    'personId': 'p1',
                    'entityId': 'h',
                    'bib': '10',
                    'starter': True,
                }]}
            return {'data': []}

        def fetch_rows(_org, fixture, _status):
            calls.append(('stats', fixture))
            return _stats_rows()

        result = season_aggregate(
            source, fetch_roster=fetch_roster, fetch_player_rows=fetch_rows,
        )
        label = next(row['label'] for row in result['players'] if row['person_id'] == 'p1')
        self.assertTrue(label.startswith('#10 '))
        self.assertCountEqual(calls, [
            ('roster', 'g1'), ('stats', 'g1'),
            ('roster', 'g2'), ('stats', 'g2'),
        ])
        named = season_aggregate(
            _season_source([
                _opening_game([], fixture_id='g1'),
                _opening_game([], fixture_id='g2'),
            ], opponent='a'),
            fetch_roster=fetch_roster,
            fetch_player_rows=fetch_rows,
        )
        self.assertEqual(len(calls), 4)
        opponent = next(
            row for row in named['opponent_players'] if row['person_id'] == 'q1'
        )
        self.assertTrue(opponent['label'].startswith('#9 '))

    def test_a_failed_fact_fetch_is_retried(self):
        source = _season_source([_opening_game([], fixture_id='g')])
        calls = []

        def fetch_roster(_org, _fixture, _status):
            calls.append('roster')
            raise RuntimeError('roster down')

        def fetch_rows(_org, _fixture, _status):
            calls.append('stats')
            raise RuntimeError('stats down')

        season_aggregate(
            source, fetch_roster=fetch_roster, fetch_player_rows=fetch_rows,
        )
        season_aggregate(
            source, fetch_roster=fetch_roster, fetch_player_rows=fetch_rows,
        )
        self.assertEqual(calls, ['roster', 'stats', 'roster', 'stats'])

    def test_a_roster_row_without_bib_keeps_the_stats_number(self):
        source = _season_source([_opening_game([], fixture_id='g')])

        def fetch_roster(_org, _fixture, _status):
            return {'data': [{
                'personId': 'p1', 'entityId': 'h', 'starter': True,
            }]}

        result = season_aggregate(
            source,
            fetch_roster=fetch_roster,
            fetch_player_rows=lambda *_args: _stats_rows(),
        )
        label = next(row['label'] for row in result['players'] if row['person_id'] == 'p1')
        self.assertTrue(label.startswith('#7 '))


class RotationDownloadTests(unittest.TestCase):
    def test_only_the_selected_teams_games_are_downloaded(self):
        from unittest.mock import patch

        from synergy_inbounder.settings import SYNERGY_SEASON_ID
        from synergy_reporter import team_season

        schedule = [
            {
                'fixtureId': 'mine', 'status': 'FINISHED', 'fixtureType': 'REGULAR',
                'teamIdHome': 'h', 'teamIdAway': 'a', 'venueId': 'v',
            },
            {
                'fixtureId': 'other', 'status': 'FINISHED', 'fixtureType': 'REGULAR',
                'teamIdHome': 'x', 'teamIdAway': 'y', 'venueId': 'v',
            },
        ]
        bundle = {
            'schedule': schedule,
            'id_table': {'h': 'Home', 'a': 'Away', 'x': 'Ex', 'y': 'Why', 'v': 'Venue'},
        }
        with patch.object(team_season, '_load_bundle', return_value=bundle), \
                patch.object(team_season, '_ensure_pbp') as ensure, \
                patch.object(team_season, '_pbp_map', return_value={}):
            result = team_season.rotation_games(
                'PLG', SYNERGY_SEASON_ID, 'REGULAR', 'all', 'all', 'all', 'h',
            )
        sent = [row['fixtureId'] for row in ensure.call_args[0][1]]
        self.assertEqual(sent, ['mine'])
        self.assertEqual([game['fixture_id'] for game in result['games']], ['mine'])

    def test_opponent_from_another_type_returns_to_all(self):
        from unittest.mock import patch

        from synergy_inbounder.settings import SYNERGY_SEASON_ID
        from synergy_reporter import team_season

        schedule = [
            {
                'fixtureId': 'reg', 'status': 'FINISHED', 'fixtureType': 'REGULAR',
                'teamIdHome': 'h', 'teamIdAway': 'a', 'venueId': 'v',
            },
            {
                'fixtureId': 'final', 'status': 'FINISHED', 'fixtureType': 'FINAL',
                'teamIdHome': 'h', 'teamIdAway': 'z', 'venueId': 'v',
            },
        ]
        bundle = {
            'schedule': schedule,
            'id_table': {'h': 'Home', 'a': 'Away', 'z': 'Zone', 'v': 'Venue'},
        }
        with patch.object(team_season, '_load_bundle', return_value=bundle), \
                patch.object(team_season, '_ensure_pbp') as ensure, \
                patch.object(team_season, '_pbp_map', return_value={}):
            result = team_season.rotation_games(
                'PLG', SYNERGY_SEASON_ID, 'FINAL', 'a', 'all', 'all', 'h',
            )
        self.assertEqual(result['opponent'], 'all')
        self.assertEqual([game['fixture_id'] for game in result['games']], ['final'])
        sent = [row['fixtureId'] for row in ensure.call_args[0][1]]
        self.assertEqual(sent, ['final'])
