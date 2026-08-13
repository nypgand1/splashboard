import json
import threading
import time
import unittest
from unittest.mock import patch

from synergy_inbounder.communicator import Communicator
from synergy_inbounder.runtime_cache import (
    clear_runtime_caches,
    get_cached_report,
    is_finished_status,
)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class TokenTests(unittest.TestCase):
    def setUp(self):
        Communicator.reset_token_state()

    def test_fetches_token_before_first_get(self):
        posts = []

        def post():
            posts.append(1)
            return FakeResponse(200, {'data': {'token': 'abc'}})

        def get(url, params=None, headers=None, **kwargs):
            self.assertEqual(kwargs['auth'].token, 'abc')
            return FakeResponse(200)

        with patch.object(Communicator, 'post_synergy_for_token', side_effect=post), \
                patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_synergy('https://example.test/stats')

        self.assertEqual(len(posts), 1)

    def test_concurrent_first_calls_refresh_once(self):
        posts = []
        lock = threading.Lock()

        def post():
            time.sleep(0.05)
            with lock:
                posts.append(1)
            return FakeResponse(200, {'data': {'token': 'abc'}})

        def get(url, params=None, headers=None, **kwargs):
            return FakeResponse(200)

        with patch.object(Communicator, 'post_synergy_for_token', side_effect=post), \
                patch.object(Communicator, 'get', side_effect=get):
            threads = [
                threading.Thread(target=lambda: Communicator.get_synergy('https://example.test/stats'))
                for _ in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(posts), 1)

    def test_concurrent_403_refresh_once(self):
        posts = []
        lock = threading.Lock()
        seed_done = threading.Event()

        def post():
            time.sleep(0.05)
            with lock:
                posts.append(1)
                token = 'seed' if len(posts) == 1 else 'refreshed'
            return FakeResponse(200, {'data': {'token': token}})

        def get(url, params=None, headers=None, **kwargs):
            if seed_done.is_set() and kwargs['auth'].token == 'seed':
                return FakeResponse(403)
            return FakeResponse(200)

        with patch.object(Communicator, 'post_synergy_for_token', side_effect=post), \
                patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_synergy('https://example.test/warmup')
            self.assertEqual(len(posts), 1)
            seed_done.set()

            threads = [
                threading.Thread(target=lambda: Communicator.get_synergy('https://example.test/stats'))
                for _ in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(posts), 2)


class ReportCacheTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def test_finished_and_live_status(self):
        self.assertTrue(is_finished_status('FINISHED'))
        self.assertTrue(is_finished_status('FINISHED '))
        self.assertTrue(is_finished_status('CONFIRMED'))
        self.assertFalse(is_finished_status('IN_PROGRESS'))
        self.assertFalse(is_finished_status(None))

    def test_concurrent_lookups_build_once(self):
        builds = []
        lock = threading.Lock()

        class DummyReport:
            def __init__(self, game_id):
                time.sleep(0.05)
                with lock:
                    builds.append(game_id)

        with patch('synergy_reporter.post_game_report.PostGameReport', DummyReport), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='FINISHED'):
            threads = [
                threading.Thread(target=lambda: get_cached_report('game-1'))
                for _ in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            again = get_cached_report('game-1')

        self.assertEqual(builds, ['game-1'])
        self.assertIsInstance(again, DummyReport)


class LineupStoreShapeTests(unittest.TestCase):
    def test_picks_size_from_new_store(self):
        from synergy_reporter.report_components import lineup_tables_for_size
        store = {
            '5': {'Home': '{"columns":["Lineup"]}'},
            '4': {'Home': '{"columns":["Lineup4"]}'},
        }
        self.assertEqual(lineup_tables_for_size(store, 4)['Home'], '{"columns":["Lineup4"]}')
        self.assertEqual(lineup_tables_for_size(json.dumps(store), 5)['Home'], '{"columns":["Lineup"]}')

    def test_old_store_still_reads_as_tables(self):
        from synergy_reporter.report_components import lineup_tables_for_size
        store = {'勇士': '{"columns":["Lineup"]}'}
        self.assertEqual(lineup_tables_for_size(store, 5)['勇士'], '{"columns":["Lineup"]}')


class PaneRenderGateTests(unittest.TestCase):
    def test_hidden_tab_callbacks_do_not_rebuild(self):
        import app  # noqa: F401
        from dash import no_update
        from pages import game as game_page
        self.assertIs(game_page.update_pane_bs('{}', 'tab-lineup'), no_update)
        self.assertIs(game_page.update_pane_pbp('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_lineup('{}', 5, 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_report('{}', '{}', '{}', 'tab-bs'), no_update)


if __name__ == '__main__':
    unittest.main()
