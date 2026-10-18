import json
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

from synergy_inbounder.communicator import (
    Communicator,
    SynergyApiError,
    SynergyAuthError,
    drop_cached_live_urls,
)
from synergy_inbounder.live_budget import BUDGET, parse_retry_after
from synergy_inbounder.runtime_cache import (
    clear_runtime_caches,
    get_cached_id_table,
    get_cached_report,
    get_cached_season_df,
    id_refresh_state,
    report_refresh_state,
    season_refresh_state,
)
from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from ui_kit import ERROR_HOME, REFRESH_DELAYED


LIVE_PBP = 'https://example.test/o/org/fixtures/g/playbyplay/live'


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {'data': {}}
        self.headers = {}
        self.from_cache = False

    def json(self):
        return self._payload


def _clock(start=1000.0):
    state = {'now': start}

    def monotonic():
        return state['now']

    return state, monotonic


class LiveBudgetTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def tearDown(self):
        clear_runtime_caches()

    def test_retry_after_falls_back_to_sixty_seconds(self):
        self.assertEqual(parse_retry_after('12'), 12.0)
        self.assertEqual(parse_retry_after('nope'), 60.0)
        self.assertEqual(parse_retry_after(-3), 60.0)

    def test_two_games_burst_then_take_turns(self):
        self.assertEqual(BUDGET.acquire('rot', 'b', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('rot', 'a', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('rot', 'b', True, 40, 10), 'serve')
        self.assertEqual(BUDGET.acquire('rot', 'a', True, 40, 40), 'serve')
        self.assertEqual(BUDGET.acquire('rot', 'b', True, 40, 60), 'serve')
        self.assertEqual(BUDGET.acquire('rot', 'a', True, 40, 60), 'fetch')
        self.assertEqual(BUDGET.acquire('rot', 'a', True, 40, 95), 'serve')
        self.assertEqual(BUDGET.acquire('rot', 'b', True, 40, 95), 'fetch')

    def test_single_game_waits_for_short_ttl_then_skips_a_full_budget(self):
        self.assertEqual(BUDGET.acquire('one', 'a', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('one', 'a', True, 10, 10), 'serve')
        self.assertEqual(BUDGET.acquire('one', 'a', True, 30, 30), 'fetch')
        self.assertEqual(BUDGET.acquire('one', 'a', True, 35, 50), 'serve')

    def test_cooldown_delays_our_turn_and_fails_without_a_snapshot(self):
        self.assertEqual(BUDGET.acquire('cool', 'a', False, 0, 0), 'fetch')
        BUDGET.note_429('cool', None, now=0)
        self.assertEqual(BUDGET.acquire('cool', 'a', True, 30, 10), 'delay')
        self.assertEqual(BUDGET.acquire('cool', 'a', False, 30, 10), 'fail')

    def test_a_full_route_refuses_the_extra_retry(self):
        self.assertEqual(BUDGET.acquire('retry', 'a', False, 0, 0), 'fetch')
        self.assertTrue(BUDGET.in_hold('retry'))
        self.assertTrue(BUDGET.allow_retry('retry', 'pbp', 0))
        self.assertFalse(BUDGET.allow_retry('retry', 'pbp', 0))
        self.assertTrue(BUDGET.allow_retry('retry', 'team', 0))
        BUDGET.release('retry')
        self.assertFalse(BUDGET.in_hold('retry'))

    def test_forget_drops_a_game_from_the_rotation(self):
        self.assertEqual(BUDGET.acquire('gone', 'a', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('gone', 'b', False, 0, 0), 'fetch')
        BUDGET.forget('gone', 'a')
        self.assertEqual(BUDGET.acquire('gone', 'b', True, 40, 60), 'fetch')

    def test_a_quiet_game_leaves_after_seventy_seconds(self):
        self.assertEqual(BUDGET.acquire('watch', 'old', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('watch', 'new', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('watch', 'new', True, 40, 70), 'fetch')

    def test_organizations_do_not_share_a_budget(self):
        self.assertEqual(BUDGET.acquire('plg', 'g', False, 0, 0), 'fetch')
        self.assertEqual(BUDGET.acquire('easl', 'g', False, 0, 0), 'fetch')


class LiveReportFailureTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()
        get_cached_report.factory = None

    def tearDown(self):
        get_cached_report.factory = None
        clear_runtime_caches()

    def test_a_failed_turn_keeps_the_snapshot_until_the_next_success(self):
        import app  # noqa: F401
        from pages import game as game_page

        clock, monotonic = _clock()

        class Scripted:
            mode = 'ok'

            def __init__(self, game_id, organization_id=None):
                if Scripted.mode == 'boom':
                    raise SynergyApiError('500')
                self.game_id = game_id

        with patch('synergy_reporter.post_game_report.PostGameReport', Scripted), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='IN_PROGRESS'), \
                patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            first = get_cached_report('g', 'org-budget')
            label = report_refresh_state('g', 'org-budget')['label']
            Scripted.mode = 'boom'
            clock['now'] = 1030.0
            second = get_cached_report('g', 'org-budget')
            delayed = report_refresh_state('g', 'org-budget')
            self.assertIs(second, first)
            self.assertTrue(delayed['delayed'])
            self.assertEqual(delayed['label'], label)
            self.assertIn(REFRESH_DELAYED, str(game_page._last_update_span('g', 'org-budget')))
            Scripted.mode = 'ok'
            clock['now'] = 1090.0
            third = get_cached_report('g', 'org-budget')
        self.assertIsNot(third, first)
        self.assertFalse(report_refresh_state('g', 'org-budget')['delayed'])
        self.assertNotIn(REFRESH_DELAYED, str(game_page._last_update_span('g', 'org-budget')))

    def test_auth_failure_drops_the_snapshot(self):
        clock, monotonic = _clock()

        class Scripted:
            mode = 'ok'

            def __init__(self, game_id, organization_id=None):
                if Scripted.mode == 'auth':
                    raise SynergyAuthError('401')
                self.game_id = game_id

        with patch('synergy_reporter.post_game_report.PostGameReport', Scripted), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='IN_PROGRESS'), \
                patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            get_cached_report('g', 'org-auth')
            Scripted.mode = 'auth'
            clock['now'] = 1030.0
            with self.assertRaises(SynergyAuthError):
                get_cached_report('g', 'org-auth')
        self.assertIsNone(report_refresh_state('g', 'org-auth')['label'])

    def test_a_first_failure_does_not_store_a_snapshot(self):
        class Boom:
            def __init__(self, game_id, organization_id=None):
                raise SynergyApiError('down')

        with patch('synergy_reporter.post_game_report.PostGameReport', Boom), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='IN_PROGRESS'):
            with self.assertRaises(SynergyApiError):
                get_cached_report('missing', 'org-cold')
        self.assertIsNone(report_refresh_state('missing', 'org-cold')['label'])

    def test_siblings_build_once_and_share_the_failure(self):
        builds = []
        lock = threading.Lock()

        class Boom:
            def __init__(self, game_id, organization_id=None):
                time.sleep(0.05)
                with lock:
                    builds.append(game_id)
                raise SynergyApiError('down')

        errors = []

        def run():
            try:
                get_cached_report('same', 'org-sib')
            except SynergyApiError:
                errors.append(1)

        with patch('synergy_reporter.post_game_report.PostGameReport', Boom), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='IN_PROGRESS'):
            threads = [threading.Thread(target=run) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(builds, ['same'])
        self.assertEqual(len(errors), 8)

    def test_a_failed_build_drops_partial_live_http_cache(self):
        seen = []

        class Boom:
            def __init__(self, game_id, organization_id=None):
                raise SynergyApiError('down')

        with patch('synergy_inbounder.communicator.drop_cached_live_urls', side_effect=seen.append), \
                patch('synergy_reporter.post_game_report.PostGameReport', Boom), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='IN_PROGRESS'):
            with self.assertRaises(SynergyApiError):
                get_cached_report('gid-9', 'org-drop')
        self.assertEqual(seen, ['gid-9'])


class SeasonMetaTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def tearDown(self):
        clear_runtime_caches()

    def test_a_failed_refresh_keeps_the_previous_season_and_the_stamp(self):
        clock, monotonic = _clock()

        def boom():
            raise RuntimeError('down')

        with patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            self.assertEqual(get_cached_season_df('org-s', 'season', lambda: 'v1'), 'v1')
            label = season_refresh_state('org-s', 'season')['label']
            clock['now'] = 1031.0
            self.assertEqual(get_cached_season_df('org-s', 'season', boom), 'v1')
        state = season_refresh_state('org-s', 'season')
        self.assertEqual(state['label'], label)
        self.assertTrue(state['delayed'])

    def test_auth_failure_does_not_serve_a_stale_season(self):
        clock, monotonic = _clock()

        def boom():
            raise SynergyAuthError('401')

        with patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            get_cached_season_df('org-s', 'season', lambda: 'v1')
            clock['now'] = 1031.0
            with self.assertRaises(SynergyAuthError):
                get_cached_season_df('org-s', 'season', boom)
        state = season_refresh_state('org-s', 'season')
        self.assertFalse(state['delayed'])
        self.assertTrue(state['label'])

    def test_id_table_failure_marks_delay_without_replacing_the_table(self):
        clock, monotonic = _clock()

        def boom():
            raise RuntimeError('down')

        with patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            self.assertEqual(get_cached_id_table('org-id', lambda: {'p': 'A'}), {'p': 'A'})
            clock['now'] = 1000.0 + (2 * 60 * 60) + 1
            self.assertEqual(get_cached_id_table('org-id', boom), {'p': 'A'})
        self.assertTrue(id_refresh_state('org-id')['delayed'])


class HomeDelayTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def tearDown(self):
        clear_runtime_caches()

    def _page(self, n_intervals, df_side_effect=None, df_value=None):
        import app  # noqa: F401
        from pages import home as home_page

        scope = {'league': 'PLG', 'season_id': SYNERGY_SEASON_ID}
        filters = {'show': 'upcoming', 'league': 'PLG', 'seasons': {'PLG': SYNERGY_SEASON_ID}}
        kwargs = {}
        if df_side_effect is not None:
            kwargs['side_effect'] = df_side_effect
        else:
            kwargs['return_value'] = pd.DataFrame() if df_value is None else df_value
        with patch.object(home_page, 'df_data', **kwargs):
            return home_page.load_home_game_list(n_intervals, scope, filters)

    def test_stale_season_renders_the_old_stamp_and_the_delay_line(self):
        clock, monotonic = _clock()
        with patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            get_cached_season_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID, lambda: 'rows')
            label = season_refresh_state(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)['label']
            clock['now'] = 1031.0

            def boom():
                raise RuntimeError('down')

            get_cached_season_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID, boom)
        page, _store = self._page(1)
        text = str(page)
        self.assertIn(label, text)
        self.assertIn(REFRESH_DELAYED, text)
        self.assertNotIn('Last Update: —', text)

    def test_only_a_stale_id_table_still_shows_the_delay_line(self):
        clock, monotonic = _clock()

        def boom():
            raise RuntimeError('down')

        with patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            get_cached_season_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID, lambda: 'rows')
            get_cached_id_table(SYNERGY_ORGANIZATION_ID, lambda: {'p': 'A'})
            clock['now'] = 1000.0 + (2 * 60 * 60) + 1
            get_cached_id_table(SYNERGY_ORGANIZATION_ID, boom)
        self.assertFalse(season_refresh_state(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)['delayed'])
        page, _store = self._page(1)
        self.assertIn(REFRESH_DELAYED, str(page))

    def test_auth_on_a_later_tick_is_the_red_alert(self):
        page, _store = self._page(2, df_side_effect=SynergyAuthError('401'))
        text = str(page)
        self.assertIn(ERROR_HOME, text)
        self.assertIn('Last Update: —', text)
        self.assertNotIn(REFRESH_DELAYED, text)

    def test_a_later_tick_with_no_snapshot_leaves_the_page(self):
        from dash import no_update
        page, store = self._page(3, df_side_effect=RuntimeError('down'))
        self.assertIs(page, no_update)
        self.assertIs(store, no_update)


class GameFailureSurfaceTests(unittest.TestCase):
    def test_auth_clears_match_info_and_other_failures_keep_it(self):
        import app  # noqa: F401
        from pages import game as game_page
        from synergy_inbounder.parser import Parser

        previous = json.dumps({
            'status': 'IN_PROGRESS',
            'home_team': 'Home',
            'away_team': 'Away',
        })
        with patch.object(Parser, 'find_game_row', side_effect=SynergyAuthError('401')):
            auth = game_page.update_match_info_store(1, 'g1', 'plg', previous)
        self.assertEqual(json.loads(auth)['_ui'], 'error')
        self.assertFalse(game_page.set_interval_disabled(auth))

        with patch.object(Parser, 'find_game_row', side_effect=RuntimeError('down')):
            kept = game_page.update_match_info_store(1, 'g1', 'plg', previous)
        self.assertIn('IN_PROGRESS', kept)
        self.assertFalse(game_page.set_interval_disabled(kept))

    def test_an_error_store_keeps_the_interval_armed(self):
        import app  # noqa: F401
        from pages import game as game_page
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'_ui': 'error'})))


class LiveHttpBudgetTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()
        Communicator.reset_token_state()

    def tearDown(self):
        clear_runtime_caches()
        Communicator.reset_token_state()

    def _token(self):
        return patch.object(
            Communicator,
            'post_synergy_for_token',
            return_value=FakeResponse(200, {'data': {'token': 'abc', 'expiresIn': 3600}}),
        )

    def test_a_full_live_route_does_not_send_the_5xx_retry(self):
        now = time.monotonic()
        self.assertTrue(BUDGET.try_spend('org-http', 'pbp', now))
        calls = []

        def get(url, params=None, headers=None, **kwargs):
            calls.append(url)
            return FakeResponse(500)

        with self._token(), patch.object(Communicator, 'get', side_effect=get):
            response = Communicator.get_synergy(LIVE_PBP, organization_id='org-http')
        self.assertEqual(len(calls), 1)
        self.assertEqual(response.status_code, 500)

    def test_an_open_live_route_retries_a_5xx(self):
        calls = {'n': 0}

        def get(url, params=None, headers=None, **kwargs):
            calls['n'] += 1
            return FakeResponse(500 if calls['n'] == 1 else 200)

        with self._token(), patch.object(Communicator, 'get', side_effect=get):
            response = Communicator.get_synergy(LIVE_PBP, organization_id='org-retry')
        self.assertEqual(calls['n'], 2)
        self.assertEqual(response.status_code, 200)

    def test_429_pauses_that_organization(self):
        def get(url, params=None, headers=None, **kwargs):
            response = FakeResponse(429)
            response.headers = {'Retry-After': '12'}
            return response

        with self._token(), patch.object(Communicator, 'get', side_effect=get), \
                patch('synergy_inbounder.live_budget.time.monotonic', return_value=5000.0):
            Communicator.get_synergy(LIVE_PBP, organization_id='org-429')
            action = BUDGET.acquire('org-429', 'g', True, 30, 5000.0)
        self.assertEqual(action, 'delay')

    def test_a_cache_hit_does_not_spend_the_budget(self):
        def get(url, params=None, headers=None, **kwargs):
            response = FakeResponse(200)
            response.from_cache = True
            return response

        with self._token(), patch.object(Communicator, 'get', side_effect=get):
            for _ in range(3):
                Communicator.get_synergy(LIVE_PBP, organization_id='org-hit')

    def test_a_held_bundle_is_not_counted_twice(self):
        now = time.monotonic()
        self.assertEqual(BUDGET.acquire('org-hold', 'g', False, 30, now), 'fetch')
        self.assertTrue(BUDGET.try_spend('org-hold', 'pbp', now))
        calls = []

        def get(url, params=None, headers=None, **kwargs):
            calls.append(url)
            return FakeResponse(200)

        with self._token(), patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_synergy(LIVE_PBP, organization_id='org-hold')
            BUDGET.release('org-hold')
            with self.assertRaises(SynergyApiError):
                Communicator.get_synergy(LIVE_PBP, organization_id='org-hold')
        self.assertEqual(len(calls), 1)

    def test_season_list_bypasses_the_http_cache(self):
        seen = []

        def get(url, params=None, headers=None, **kwargs):
            seen.append(kwargs.get('cached'))
            return FakeResponse(200, {'data': []})

        with self._token(), patch.object(Communicator, 'get', side_effect=get):
            Communicator.get_season_game_list('org', 'season')
        self.assertEqual(seen, [False])

    def test_drop_cached_live_urls_keeps_other_fixtures_and_official_urls(self):
        class FakeCache:
            def __init__(self):
                self.deleted = None

            def urls(self):
                return [
                    'https://x/fixtures/game-1/playbyplay/live',
                    'https://x/fixtures/game-10/playbyplay/live',
                    'https://x/fixtures/game-1/playbyplay',
                    'https://x/fixtures/game-1/roster',
                ]

            def delete(self, urls=None, **kwargs):
                self.deleted = list(urls or [])

        cache = FakeCache()
        with patch('synergy_inbounder.communicator.requests_cache.get_cache', return_value=cache):
            drop_cached_live_urls('game-1')
        self.assertEqual(cache.deleted, ['https://x/fixtures/game-1/playbyplay/live'])


if __name__ == '__main__':
    unittest.main()
