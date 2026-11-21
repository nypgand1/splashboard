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


class UnifiedPrefetchAndEvictionTests(unittest.TestCase):
    def setUp(self):
        self._game = publisher._game_builder
        self._season = publisher._season_step
        self._pf_season = publisher._prefetch_season_step
        publisher.set_autostart(False)
        clear_runtime_caches()

    def tearDown(self):
        publisher.register_game_builder(self._game)
        publisher.register_season_step(self._season)
        publisher.register_prefetch_season_step(self._pf_season)
        publisher.set_autostart(True)
        clear_runtime_caches()

    def test_p0_and_p1_run_before_p2_and_p3_and_p2_populates_drawer(self):
        order = []

        def builder(org, gid, league, prev, fp, prefetch=False):
            order.append(('game_pf' if prefetch else 'game', gid))
            return {
                'stores': {'bs': '{"ok": 1}', 'info': '{"status": "FINISHED"}'},
                'fingerprint': 'fp-' + gid,
                'kind': 'official',
            }

        def pf_season(org, sid, state):
            order.append(('pf_season', sid))
            return {'phase': 'done'}

        publisher.register_game_builder(builder)
        publisher.register_prefetch_season_step(pf_season)
        publisher.note_prefetch_season('org', 's1', league='plg')
        publisher.note_prefetch_games('org', ['g-pf'], league='plg')
        publisher.note_game('org', 'g-live', 'plg', now=0)

        self.assertEqual(publisher.run_once(now=0), 'game')
        self.assertEqual(publisher.run_once(now=0), 'prefetch_game')
        snap = publisher.peek_game('org', 'g-pf')
        self.assertIsNotNone(snap)
        self.assertEqual(snap['stores']['bs'], '{"ok": 1}')

        with patch('synergy_inbounder.runtime_cache.peek_finished_report') as peek_rep, \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='FINISHED'):
            class _Rep:
                def get_all_lineup_stats_json_dict(self, sizes=()):
                    order.append(('warmup_lineup', sizes))
                    return {}
            peek_rep.return_value = _Rep()
            self.assertEqual(publisher.run_once(now=0), 'prefetch_game')

        self.assertEqual(publisher.run_once(now=0), 'prefetch_season')
        self.assertIsNone(publisher.run_once(now=0))
        self.assertEqual(order, [
            ('game', 'g-live'),
            ('game_pf', 'g-pf'),
            ('warmup_lineup', (5, 4, 3, 2)),
            ('pf_season', 's1'),
        ])

    def test_report_cache_and_drawer_evict_beyond_12_preserving_pinned(self):
        from inbound.cache.frame_store import REPORT_CACHE_LIMIT, pin_home, pin_open
        from synergy_inbounder.runtime_cache import _report_cache, get_cached_report

        class _DummyReport:
            def __init__(self, gid, org=None):
                self.gid = gid
                self.stats_failed = False

        pin_open('org', 'g0')
        pin_home('org', ['g1'])
        with patch('synergy_reporter.post_game_report.PostGameReport', _DummyReport), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='CONFIRMED'):
            for idx in range(REPORT_CACHE_LIMIT + 3):
                gid = f'g{idx}'
                with publisher._LOCK:
                    publisher._store_game_snap_locked(('org', gid), {'bs': gid}, None)
                get_cached_report(gid, 'org')

        self.assertEqual(len(_report_cache), REPORT_CACHE_LIMIT)
        self.assertIn(('org', 'g0'), _report_cache)
        self.assertIn(('org', 'g1'), _report_cache)
        self.assertNotIn(('org', 'g2'), _report_cache)
        self.assertIsNone(publisher.peek_game('org', 'g2'))
        self.assertIsNotNone(publisher.peek_game('org', 'g0'))
        self.assertIsNotNone(publisher.peek_game('org', 'g1'))

    def test_parse_game_bundle_absorbs_fixture_facts_into_frame_store(self):
        from inbound.cache.frame_store import get_fixture_facts, get_fixture_starters, get_team_shirts
        from synergy_inbounder.parser import Parser

        team_json = {'data': [{'entityId': 't-home', 'statistics': {'minutes': 'PT40M'}}]}
        periods_json = {'data': []}
        player_json = {'data': [{
            'personId': 'p1', 'entityId': 't-home', 'starter': True,
            'participated': True, 'shirtNumber': '99', 'statistics': {'minutes': 'PT20M'},
        }]}
        roster_json = {'data': [{
            'personId': 'p1', 'entityId': 't-home', 'starter': True, 'bib': '7',
        }]}
        pbp_json = {'data': []}
        with patch('synergy_inbounder.parser.should_use_live_endpoints', return_value=False), \
                patch('synergy_inbounder.parser.cached_fixture_status', return_value='CONFIRMED'), \
                patch('synergy_inbounder.parser.run_wave', return_value=(
                    team_json, periods_json, player_json, {'data': []},
                    pbp_json, roster_json, {'p1': 'Jeremy Lin', 't-home': 'Braves'},
                )):
            Parser.parse_game_bundle('org', 'g-fact')

        facts = get_fixture_facts('org', 'g-fact')
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['shirtNumber'], '7')
        self.assertEqual(get_team_shirts('t-home').get('p1'), '7')
        self.assertEqual(get_fixture_starters('org', 'g-fact'), {'t-home': ['p1']})

    def test_p3_advance_prefetch_season_steps_incrementally(self):
        from inbound.cache.frame_store import (
            get_lineup_summary,
            get_rotation_summary,
            is_fact_attempted,
        )
        from synergy_reporter import team_season
        from synergy_reporter.team_season import advance_prefetch_season

        schedule = [
            {
                'fixtureId': f'g{idx}',
                'status': 'CONFIRMED',
                'fixtureType': 'REGULAR',
                'teamIdHome': 'h',
                'teamIdAway': 'a',
                'startTimeLocal': f'2026-10-0{idx}T19:00:00',
            }
            for idx in range(1, 6)
        ]
        bundle = {
            'schedule': schedule,
            'totals': pd.DataFrame([{'fixtureId': 'g1', 'entityId': 'h'}]),
            'periods': pd.DataFrame([{'fixtureId': 'g1', 'entityId': 'h', 'periodId': 1}]),
            'id_table': {'h': 'Home', 'a': 'Away', 'p1': 'P1'},
            'stamp': 'Last Update: now',
            'fetched_at': 100.0,
        }
        pbp_rows = [
            {'periodId': 1, 'clock': 'PT10M00S', 'eventType': '2pt', 'subType': 'jump', 'entityId': 'h', 'personId': f'p{i}', 'success': 1, 'scores': {'h': 2, 'a': 0}, 'options': None}
            for i in range(1, 6)
        ] + [
            {'periodId': 1, 'clock': 'PT10M00S', 'eventType': '2pt', 'subType': 'jump', 'entityId': 'a', 'personId': f'q{i}', 'success': 1, 'scores': {'h': 2, 'a': 2}, 'options': None}
            for i in range(1, 6)
        ] + [
            {'periodId': 1, 'clock': 'PT00M00S', 'eventType': 'period', 'subType': 'end', 'entityId': None, 'personId': None, 'success': 0, 'scores': {'h': 2, 'a': 2}, 'options': None}
        ]
        pbp_calls = []

        def fake_pbp(org, fid, status):
            pbp_calls.append(fid)
            return {'data': pbp_rows}

        def fake_load_bundle(org, sid, reason, force=False):
            team_season._store_bundle(org, sid, bundle)
            return bundle

        with patch.object(team_season, '_load_bundle', side_effect=fake_load_bundle), \
                patch.object(team_season, 'Communicator_pbp', side_effect=fake_pbp), \
                patch('synergy_reporter.team_rotation.default_fetch_roster', return_value=[]), \
                patch('synergy_reporter.team_rotation.default_fetch_player_rows', return_value=[]):
            st = advance_prefetch_season('org', 's1', {'phase': 'bundle', 'game_type': 'REGULAR'})
            self.assertEqual(st['phase'], 'pbp')
            # First PBP step downloads a batch of 4 (newest first: g5, g4, g3, g2)
            st = advance_prefetch_season('org', 's1', st)
            self.assertEqual(st['phase'], 'pbp')
            self.assertEqual(pbp_calls, ['g5', 'g4', 'g3', 'g2'])
            # Second PBP step downloads the remaining 1 (g1) and transitions to facts
            st = advance_prefetch_season('org', 's1', st)
            self.assertEqual(st['phase'], 'facts')
            self.assertEqual(pbp_calls, ['g5', 'g4', 'g3', 'g2', 'g1'])
            # First facts step warms 4 games
            st = advance_prefetch_season('org', 's1', st)
            self.assertEqual(st['phase'], 'facts')
            self.assertTrue(is_fact_attempted('org', 'g5'))
            self.assertFalse(is_fact_attempted('org', 'g1'))
            # Second facts step warms the remaining 1 game and finishes
            st = advance_prefetch_season('org', 's1', st)
            self.assertEqual(st['phase'], 'done')
            self.assertTrue(is_fact_attempted('org', 'g1'))
            frame_g5 = peek('org', 'g5')
            self.assertIsNotNone(get_rotation_summary('org', 'g5', id(frame_g5.playbyplay_df)))
            self.assertIsNotNone(get_lineup_summary('org', 'g5', id(frame_g5.playbyplay_df)))
