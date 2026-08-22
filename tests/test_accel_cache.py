import json
import threading
import time
import unittest
from unittest.mock import patch

from synergy_inbounder.communicator import Communicator, SynergyApiError, payload_from_response
from synergy_inbounder.settings import MissingSynergyCredentials, get_synergy_credentials
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

    def test_refreshes_after_expires_in(self):
        posts = []
        clock = {'now': 1000.0}

        def post():
            posts.append(1)
            return FakeResponse(200, {'data': {'token': 't{0}'.format(len(posts)), 'expiresIn': 120}})

        def get(url, params=None, headers=None, **kwargs):
            return FakeResponse(200)

        with patch.object(Communicator, 'post_synergy_for_token', side_effect=post), \
                patch.object(Communicator, 'get', side_effect=get), \
                patch('synergy_inbounder.communicator.time.monotonic', side_effect=lambda: clock['now']):
            Communicator.get_synergy('https://example.test/stats')
            self.assertEqual(len(posts), 1)
            clock['now'] = 1070.0
            Communicator.get_synergy('https://example.test/stats')

        self.assertEqual(len(posts), 2)

    def test_missing_credentials_fail_before_http(self):
        posts = []

        def post(*args, **kwargs):
            posts.append(1)
            return FakeResponse(200, {'data': {'token': 'abc'}})

        with patch.dict('os.environ', {
            'SYNERGY_CREDENTIAL_ID': '',
            'SYNERGY_CREDENTIAL_SECRET': '',
        }):
            with patch('synergy_inbounder.communicator.requests.post', side_effect=post):
                with self.assertRaises(MissingSynergyCredentials):
                    Communicator.post_synergy_for_token()
                with self.assertRaises(MissingSynergyCredentials):
                    get_synergy_credentials()
        self.assertEqual(posts, [])

    def test_401_refreshes_token(self):
        posts = []

        def post():
            posts.append(1)
            return FakeResponse(200, {'data': {'token': 'tok-{0}'.format(len(posts)), 'expiresIn': 3600}})

        calls = {'n': 0}

        def get(url, params=None, headers=None, **kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                return FakeResponse(401)
            return FakeResponse(200)

        with patch.object(Communicator, 'post_synergy_for_token', side_effect=post), \
                patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_synergy('https://example.test/stats')

        self.assertEqual(len(posts), 2)


class LiveRouteTests(unittest.TestCase):
    def setUp(self):
        Communicator.reset_token_state()

    def test_finished_games_use_official_not_live_urls(self):
        seen = []

        def get(url, params=None, headers=None, **kwargs):
            seen.append(url)
            return FakeResponse(200, {'data': []})

        with patch.object(Communicator, 'post_synergy_for_token',
                          return_value=FakeResponse(200, {'data': {'token': 'abc', 'expiresIn': 3600}})), \
                patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_game_play_by_play_synergy('org', 'game', live=False)
            Communicator.get_game_team_stats_synergy('org', 'game', live=False)
            Communicator.get_game_team_stats_periods_synergy('org', 'game', live=False)
            Communicator.get_game_player_stats_synergy('org', 'game', live=False)

        self.assertTrue(any(url.endswith('/playbyplay') for url in seen))
        self.assertFalse(any('/playbyplay/live' in url for url in seen))
        self.assertFalse(any(url.endswith('/live') for url in seen))

    def test_live_games_keep_live_urls(self):
        seen = []

        def get(url, params=None, headers=None, **kwargs):
            seen.append(url)
            return FakeResponse(200, {'data': []})

        with patch.object(Communicator, 'post_synergy_for_token',
                          return_value=FakeResponse(200, {'data': {'token': 'abc', 'expiresIn': 3600}})), \
                patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_game_play_by_play_synergy('org', 'game', live=True)

        self.assertTrue(any(url.endswith('/playbyplay/live') for url in seen))


class RosterMergeTests(unittest.TestCase):
    def test_fixture_bib_wins_over_stats_shirt(self):
        from synergy_inbounder.parser import Parser
        fixture = {'data': [{
            'personId': 'p1',
            'entityId': 'home',
            'starter': True,
            'bib': '10',
        }]}
        stats = {'data': [{
            'personId': 'p1',
            'entityId': 'home',
            'starter': False,
            'participated': True,
            'shirtNumber': '99',
        }]}
        merged = Parser._merge_roster(
            Parser._roster_from_fixture_json(fixture),
            Parser._roster_from_json(stats),
        )
        self.assertEqual(merged[0]['shirtNumber'], '10')
        self.assertTrue(merged[0]['starter'])


class SynergyPayloadTests(unittest.TestCase):
    def test_rejects_500_and_payload_without_data(self):
        with self.assertRaises(SynergyApiError):
            payload_from_response(FakeResponse(500, {'message': None}), url='https://example.test')
        with self.assertRaises(SynergyApiError):
            payload_from_response(FakeResponse(200, {'message': None}), url='https://example.test')

    def test_accepts_data_envelope(self):
        payload = payload_from_response(FakeResponse(200, {'data': [{'id': 1}]}))
        self.assertEqual(payload['data'], [{'id': 1}])


class HostAlignmentTests(unittest.TestCase):
    def test_all_synergy_urls_use_connect_sportradar_hosts(self):
        from synergy_inbounder import settings
        token = settings.SYNERGY_TOKEN_URL
        rest = [
            settings.SYNERGY_SEASON_GAME_LIST_URL,
            settings.SYNERGY_PLAY_BY_PLAY_URL,
            settings.SYNERGY_PLAY_BY_PLAY_LIVE_URL,
            settings.SYNERGY_TEAM_STATS_URL,
            settings.SYNERGY_TEAM_STATS_LIVE_URL,
            settings.SYNERGY_TEAM_STATS_PERIODS_URL,
            settings.SYNERGY_TEAM_STATS_PERIODS_LIVE_URL,
            settings.SYNERGY_PLAYER_STATS_URL,
            settings.SYNERGY_PLAYER_STATS_LIVE_URL,
            settings.SYNERGY_FIXTURE_ROSTER_URL,
            settings.SYNERGY_ORG_PERSONS_URL,
            settings.SYNERGY_ORG_ENTITIES_URL,
            settings.SYNERGY_ORG_VENUES_URL,
        ]
        self.assertTrue(token.startswith('https://token.connect.sportradar.com/v1/'))
        self.assertTrue(token.endswith('/oauth2/rest/token'))
        for url in rest:
            self.assertTrue(
                url.startswith('https://api.dc.connect.sportradar.com/v1/basketball/'),
                url,
            )
            self.assertNotIn('atriumsports.com', url)
        self.assertTrue(settings.SYNERGY_PLAY_BY_PLAY_LIVE_URL.endswith('/playbyplay/live'))
        self.assertTrue(settings.SYNERGY_PLAY_BY_PLAY_URL.endswith('/playbyplay'))
        self.assertFalse(settings.SYNERGY_PLAY_BY_PLAY_URL.endswith('/live'))
        self.assertNotIn('atriumsports.com', token)


class LiveCadenceTests(unittest.TestCase):
    def test_pbp_and_rotation_share_the_same_live_rule(self):
        from synergy_inbounder.runtime_cache import (
            LIVE_CADENCE_SECONDS,
            LIVE_PBP_HTTP_TTL_SECONDS,
            LIVE_REPORT_TTL_SECONDS,
        )
        from synergy_inbounder import communicator
        self.assertEqual(LIVE_CADENCE_SECONDS, 30)
        self.assertEqual(LIVE_PBP_HTTP_TTL_SECONDS, 25)
        self.assertEqual(LIVE_REPORT_TTL_SECONDS, 25)
        self.assertLess(LIVE_PBP_HTTP_TTL_SECONDS, LIVE_CADENCE_SECONDS)
        self.assertLess(LIVE_REPORT_TTL_SECONDS, LIVE_CADENCE_SECONDS)
        self.assertEqual(
            communicator.urls_expire_after['*/playbyplay/live'],
            LIVE_PBP_HTTP_TTL_SECONDS,
        )


class HomeCallbackTests(unittest.TestCase):
    def test_synergy_failure_renders_error_not_exception(self):
        import app  # noqa: F401
        from pages import home as home_page
        with patch.object(home_page, 'df_data', side_effect=SynergyApiError('Synergy 500')):
            result = home_page.load_home_game_list('home-game-list')
        self.assertIn('Failed to load games', str(result))


class ReportCacheTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def test_finished_and_live_status(self):
        from synergy_inbounder.runtime_cache import should_use_live_endpoints
        self.assertTrue(is_finished_status('FINISHED'))
        self.assertTrue(is_finished_status('FINISHED '))
        self.assertTrue(is_finished_status('CONFIRMED'))
        self.assertFalse(is_finished_status('IN_PROGRESS'))
        self.assertFalse(is_finished_status(None))
        self.assertFalse(should_use_live_endpoints(status='FINISHED'))
        self.assertTrue(should_use_live_endpoints(status='IN_PROGRESS'))
        self.assertTrue(should_use_live_endpoints(status='PENDING'))

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
        self.assertIs(game_page.update_pane_rotation('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_pbp('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_lineup('{}', 5, 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_report('tab-bs', '{}', '{}', '{}', None), no_update)


if __name__ == '__main__':
    unittest.main()
