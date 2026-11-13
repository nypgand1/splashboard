# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import patch

import pandas as pd
from dash import no_update

import app  # noqa: F401
from pages import game as game_page
from synergy_inbounder.communicator import Communicator, force_body_refresh
from synergy_inbounder.frame_store import (
    clear as clear_frames,
    peek,
    piece_fresh,
    store,
)
from synergy_inbounder.runtime_cache import clear_runtime_caches
import synergy_inbounder.publisher as publisher
from synergy_reporter.team_season import (
    advance_watched_season,
    refresh_watched_pbp,
    watched_fixture_batch,
)


class PublisherClockTests(unittest.TestCase):
    def setUp(self):
        self._game = publisher._game_builder
        self._season = publisher._season_step
        publisher.set_autostart(False)
        publisher.reset()

    def tearDown(self):
        publisher.register_game_builder(self._game)
        publisher.register_season_step(self._season)
        publisher.set_autostart(True)
        clear_runtime_caches()

    def test_cold_start_does_not_run_without_a_watch(self):
        self.assertIsNone(publisher.run_once(now=0))

    def test_watch_drops_at_70_seconds(self):
        calls = []
        publisher.register_game_builder(
            lambda *args: calls.append(args[1]) or {'unchanged': True, 'kind': 'live'},
        )
        publisher.note_game('org', 'g1', 'plg', now=0)
        self.assertIsNone(publisher.run_once(now=70))
        self.assertEqual(calls, [])
        publisher.note_game('org', 'g1', 'plg', now=0)
        self.assertEqual(publisher.run_once(now=69), 'game')
        self.assertEqual(calls, ['g1'])

    def test_a_second_note_does_not_start_another_job(self):
        nested = []

        def builder(*args):
            nested.append(publisher.run_once(now=1))
            return {
                'stores': {'info': json.dumps({'status': 'IN_PROGRESS'})},
                'kind': 'live',
                'fingerprint': None,
            }

        publisher.register_game_builder(builder)
        publisher.note_game('org', 'g1', 'plg', now=0)
        publisher.note_game('org', 'g1', 'plg', now=1)
        self.assertEqual(publisher.run_once(now=1), 'game')
        self.assertEqual(nested, [None])
        self.assertEqual(
            json.loads(publisher.peek_game('org', 'g1')['stores']['info'])['status'],
            'IN_PROGRESS',
        )

    def test_live_game_runs_before_a_due_season(self):
        order = []

        def game_builder(*args):
            order.append('game')
            return {'unchanged': True, 'kind': 'live'}

        def season_step(org, season_id, view, state, now):
            order.append('season')
            return (
                {'phase': 'idle', 'next_due': now + 120, 'cursor': 0, 'painted': None},
                None,
            )

        publisher.register_game_builder(game_builder)
        publisher.register_season_step(season_step)
        publisher.note_game('org', 'g1', 'plg', now=0)
        publisher.note_season('org', 's1', {'league': 'PLG'}, now=0)
        with publisher._LOCK:
            publisher._seasons[('org', 's1')]['cycle']['next_due'] = 0
        self.assertEqual(publisher.run_once(now=0), 'game')
        self.assertEqual(publisher.run_once(now=0), 'season')
        self.assertEqual(order, ['game', 'season'])


class GameDrawerTests(unittest.TestCase):
    def setUp(self):
        publisher.set_autostart(False)
        publisher.reset()

    def tearDown(self):
        publisher.set_autostart(True)
        clear_runtime_caches()

    def test_reader_does_not_open_the_report(self):
        with patch.object(game_page, 'get_cached_report') as cached:
            outputs = game_page.read_game_drawer(
                0, 'g1', 'plg', None, None, None, None, None, None, 2000,
            )
        cached.assert_not_called()
        self.assertTrue(all(item is no_update for item in outputs))

    def test_reader_copies_a_ready_drawer_and_settles_the_interval(self):
        publisher.note_game('b1vqz', 'g1', 'plg', now=0)
        with publisher._LOCK:
            publisher._game_snaps[('b1vqz', 'g1')] = {
                'stores': {
                    'bs': '{"ok": 1}',
                    'pbp': '{}',
                    'lineup': '{}',
                    'matchup': '{}',
                    'rotation': '{}',
                    'info': '{"status": "FINISHED"}',
                },
            }
            publisher._games[('b1vqz', 'g1')]['kind'] = 'official'
            publisher._games[('b1vqz', 'g1')]['last_run'] = 0
        with patch.object(game_page, 'get_cached_report') as cached:
            outputs = game_page.read_game_drawer(
                1, 'g1', 'plg', None, '{}', '{}', '{}', '{}', None, 2000,
            )
        cached.assert_not_called()
        self.assertEqual(outputs[0], '{"ok": 1}')
        self.assertIs(outputs[1], no_update)
        self.assertEqual(outputs[5], '{"status": "FINISHED"}')
        self.assertEqual(outputs[6], 35000)

    def test_same_fingerprint_fetches_and_skips_the_rebuild(self):
        calls = {'fetch': 0, 'publish': 0}

        def fetched(*args, **kwargs):
            calls['fetch'] += 1
            return {'data': [{'n': 1}]}

        def published(*args, **kwargs):
            calls['publish'] += 1
            return ('{"box": 1}', '{}', '{}', '{}', '{}', '{"status": "FINISHED"}')

        names = (
            'get_game_play_by_play_synergy',
            'get_game_team_stats_synergy',
            'get_game_team_stats_periods_synergy',
            'get_game_player_stats_synergy',
            'get_game_player_stats_periods_synergy',
            'get_fixture_roster_synergy',
        )
        patches = [patch.object(Communicator, name, side_effect=fetched) for name in names]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in patches])
        with patch.object(game_page, 'lookup_game_status', return_value='FINISHED'), \
                patch.object(game_page, 'publish_finished_snapshot', side_effect=published):
            first = game_page.background_game_snapshot('org', 'g1', 'plg', None, None)
            second = game_page.background_game_snapshot(
                'org', 'g1', 'plg', first['stores'], first['fingerprint'],
            )
        self.assertEqual(calls['publish'], 1)
        self.assertGreater(calls['fetch'], 6)
        self.assertTrue(second.get('unchanged'))
        self.assertEqual(second['fingerprint'], first['fingerprint'])


class OfficialRefreshTests(unittest.TestCase):
    def tearDown(self):
        clear_frames()
        clear_runtime_caches()

    def test_force_refresh_overrides_the_confirmed_ttl(self):
        class _Response(object):
            status_code = 200

            def json(self):
                return {'data': []}

        response = _Response()
        with patch.object(Communicator, '_current_token', return_value=('tok', 1)), \
                patch.object(Communicator, 'get', return_value=response) as got:
            with force_body_refresh(30):
                Communicator.get_synergy('https://example.test/playbyplay', expire_after=7200)
        self.assertEqual(got.call_args.kwargs['expire_after'], 30)
        self.assertTrue(got.call_args.kwargs['force_refresh'])

    def test_confirmed_piece_is_stale_after_mark(self):
        from synergy_inbounder.frame_store import mark_stale
        store('org', 'g1', status='CONFIRMED', team_df=pd.DataFrame({'a': [1]}), touch=('team_df',))
        self.assertTrue(piece_fresh(peek('org', 'g1'), 'team_df'))
        mark_stale('org', 'g1')
        self.assertFalse(piece_fresh(peek('org', 'g1'), 'team_df'))

    def test_watched_pbp_drops_a_confirmed_piece_before_download(self):
        frame = pd.DataFrame({'eventType': ['shot']})
        store('org', 'g1', status='CONFIRMED', playbyplay_df=frame, touch=('playbyplay_df',))
        with patch('synergy_reporter.team_season._download_pbp') as download:
            refresh_watched_pbp('org', {'fixtureId': 'g1', 'status': 'CONFIRMED'})
        download.assert_called_once()
        self.assertFalse(piece_fresh(peek('org', 'g1'), 'playbyplay_df'))

    def test_confirmed_batch_is_four_games_after_every_unconfirmed_finish(self):
        schedule = [{'fixtureId': 'f1', 'status': 'FINISHED'}]
        schedule.extend(
            {'fixtureId': 'c{0}'.format(index), 'status': 'CONFIRMED'}
            for index in range(6)
        )
        rows, cursor = watched_fixture_batch(schedule, 0, batch=4)
        self.assertEqual(
            [row['fixtureId'] for row in rows],
            ['f1', 'c0', 'c1', 'c2', 'c3'],
        )
        self.assertEqual(cursor, 4)
        rows, cursor = watched_fixture_batch(schedule, cursor, batch=4)
        self.assertEqual(
            [row['fixtureId'] for row in rows],
            ['f1', 'c4', 'c5', 'c0', 'c1'],
        )
        self.assertEqual(cursor, 2)

    def test_season_step_refreshes_the_head_before_one_game(self):
        schedule = [{'fixtureId': 'f1', 'status': 'FINISHED'}]
        schedule.extend(
            {'fixtureId': 'c{0}'.format(index), 'status': 'CONFIRMED'}
            for index in range(4)
        )
        bundle = {'schedule': schedule, 'totals': None, 'periods': None, 'id_table': {}}
        with patch('synergy_reporter.team_season._load_bundle', return_value=bundle) as loaded, \
                patch('synergy_reporter.team_season.refresh_watched_pbp') as refresh, \
                patch('synergy_reporter.team_season.team_stats_payload') as payload:
            state, built = advance_watched_season(
                'org', 's1', {'league': 'PLG'}, {'phase': 'idle', 'cursor': 0}, 0,
            )
        loaded.assert_called_once()
        refresh.assert_not_called()
        payload.assert_not_called()
        self.assertIsNone(built)
        self.assertEqual(state['phase'], 'games')
        self.assertEqual(len(state['rows']), 5)
        with patch('synergy_reporter.team_season._load_bundle') as loaded, \
                patch('synergy_reporter.team_season.refresh_watched_pbp') as refresh:
            state, built = advance_watched_season('org', 's1', {'league': 'PLG'}, state, 1)
        loaded.assert_not_called()
        refresh.assert_called_once()
        self.assertIsNone(built)
        self.assertEqual(state['index'], 1)
