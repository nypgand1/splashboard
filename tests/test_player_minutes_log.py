import unittest

from synergy_inbounder.player_minutes_log import (
    note_player_minutes,
    reset_player_minutes_log,
)


def _person(person_id, statistics, starter=True, participated=True, entity='home'):
    return {
        'personId': person_id,
        'entityId': entity,
        'starter': starter,
        'participated': participated,
        'statistics': statistics,
    }


class PlayerMinutesLogTests(unittest.TestCase):
    def setUp(self):
        reset_player_minutes_log()

    def test_missing_minutes_with_points_logs_the_gap_and_the_key_names(self):
        lines = note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'data': [_person('p1', {'points': 2, 'rebounds': 1})]},
            {'data': []},
        )
        text = '\n'.join(lines)
        self.assertIn('route=live', text)
        self.assertIn('status=IN_PROGRESS', text)
        self.assertIn('rows=1', text)
        self.assertIn('missing=1', text)
        self.assertIn('missing_with_counts=1', text)
        self.assertIn('present=missing', text)
        self.assertIn('starter=True', text)
        self.assertIn('points=2', text)
        self.assertIn('period=all', text)
        self.assertIn('keys=points,rebounds', text)

    def test_null_minutes_does_not_dump_key_names(self):
        lines = note_player_minutes(
            'org', 'game-1', True, '',
            {'data': [_person('p1', {'minutes': None, 'points': 4}, starter=False)]},
            {'data': []},
        )
        text = '\n'.join(lines)
        self.assertIn('present=null', text)
        self.assertIn('starter=False', text)
        self.assertIn('status=live', text)
        self.assertNotIn('player-minutes keys', text)

    def test_blank_and_zero_duration_are_different(self):
        blank = note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'data': [_person('p1', {'minutes': '  ', 'points': 1})]},
            {'data': []},
        )
        self.assertIn('present=blank', '\n'.join(blank))
        reset_player_minutes_log()
        zero = note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'data': [_person('p1', {'minutes': 'PT0S', 'points': 1})]},
            {'data': []},
        )
        self.assertNotIn('player-minutes row', '\n'.join(zero))
        self.assertIn('missing=0', '\n'.join(zero))

    def test_repeat_snapshot_adds_nothing(self):
        payload = {'data': [_person('p1', {'points': 2})]}
        note_player_minutes('org', 'game-1', True, 'IN_PROGRESS', payload, {'data': []})
        with self.assertNoLogs('synergy.live.minutes', level='INFO'):
            again = note_player_minutes(
                'org', 'game-1', True, 'IN_PROGRESS', payload, {'data': []},
            )
        self.assertEqual(again, [])

    def test_a_later_duration_logs_filled(self):
        note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'data': [_person('p1', {'points': 2})]},
            {'data': []},
        )
        lines = note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'data': [_person('p1', {'minutes': 'PT8M12S', 'points': 2})]},
            {'data': []},
        )
        text = '\n'.join(lines)
        self.assertIn("minutes='PT8M12S'", text)
        self.assertIn('player-minutes filled', text)
        self.assertIn('missing=0', text)

    def test_official_bundle_is_quiet_until_that_game_was_live(self):
        payload = {'data': [_person('p1', {'points': 3})]}
        with self.assertNoLogs('synergy.live.minutes', level='INFO'):
            quiet = note_player_minutes(
                'org', 'game-1', False, 'FINISHED', payload, {'data': []},
            )
        self.assertEqual(quiet, [])
        note_player_minutes('org', 'game-1', True, 'IN_PROGRESS', payload, {'data': []})
        official = note_player_minutes(
            'org', 'game-1', False, 'CONFIRMED',
            {'data': [_person('p1', {'minutes': 'PT20M', 'points': 3})]},
            {'data': []},
        )
        text = '\n'.join(official)
        self.assertIn('route=official', text)
        self.assertIn('status=CONFIRMED', text)
        self.assertIn('player-minutes filled', text)

    def test_failed_player_payload_logs_one_line(self):
        lines = note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'_stats_failed': True, 'data': []},
            {'data': [_person('p1', {'points': 5})]},
        )
        self.assertEqual(lines, [
            'player-minutes fixture=game-1 org=org route=live failed=1',
        ])

    def test_period_gap_names_the_period_and_ignores_a_zero_count(self):
        lines = note_player_minutes(
            'org', 'game-1', True, 'IN_PROGRESS',
            {'data': [_person('p1', {'minutes': 'PT10M', 'points': 0})]},
            {'data': [{
                'personId': 'p1',
                'entityId': 'home',
                'periodId': 1,
                'statistics': {'points': 0},
            }, {
                'personId': 'p2',
                'entityId': 'home',
                'periodId': 2,
                'statistics': {'minutes': None, 'points': 6},
            }]},
        )
        text = '\n'.join(lines)
        self.assertIn('period_rows=2', text)
        self.assertIn('period_missing=2', text)
        self.assertIn('period_missing_with_counts=1', text)
        self.assertIn('period=1', text)
        self.assertIn('period=2', text)
        self.assertIn('present=null', text)
        row_lines = [line for line in lines if line.startswith('player-minutes row')]
        self.assertTrue(row_lines)
        self.assertTrue(all('period=all' not in line for line in row_lines))
        self.assertNotIn('player-minutes keys', text)
