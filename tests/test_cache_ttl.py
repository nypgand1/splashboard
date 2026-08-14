import unittest
from unittest.mock import patch

from synergy_inbounder.runtime_cache import (
    LIVE_REPORT_TTL_SECONDS,
    clear_runtime_caches,
    get_cached_id_table,
    get_cached_report,
    get_cached_season_df,
)


class SeasonAndIdCacheTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def test_season_and_id_table_build_once(self):
        season_builds = []
        id_builds = []

        self.assertEqual(
            get_cached_season_df('org', 'season', lambda: season_builds.append(1) or 'season'),
            'season',
        )
        self.assertEqual(
            get_cached_season_df('org', 'season', lambda: season_builds.append(1) or 'season'),
            'season',
        )
        self.assertEqual(
            get_cached_id_table('org', lambda: id_builds.append(1) or {'p': 'Name'}),
            {'p': 'Name'},
        )
        self.assertEqual(
            get_cached_id_table('org', lambda: id_builds.append(1) or {'p': 'Name'}),
            {'p': 'Name'},
        )
        self.assertEqual(season_builds, [1])
        self.assertEqual(id_builds, [1])


class LiveReportTtlTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def test_live_report_rebuilds_after_ttl_finished_does_not(self):
        builds = []
        clock = {'now': 1000.0}

        class DummyReport:
            def __init__(self, game_id):
                builds.append(game_id)

        def monotonic():
            return clock['now']

        with patch('synergy_reporter.post_game_report.PostGameReport', DummyReport), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='IN_PROGRESS'), \
                patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            get_cached_report('live-1')
            get_cached_report('live-1')
            clock['now'] = 1000.0 + LIVE_REPORT_TTL_SECONDS
            get_cached_report('live-1')
        self.assertEqual(builds, ['live-1', 'live-1'])

        builds.clear()
        clear_runtime_caches()
        clock['now'] = 2000.0
        with patch('synergy_reporter.post_game_report.PostGameReport', DummyReport), \
                patch('synergy_inbounder.runtime_cache.lookup_game_status', return_value='FINISHED'), \
                patch('synergy_inbounder.runtime_cache.time.monotonic', side_effect=monotonic):
            get_cached_report('done-1')
            clock['now'] = 2000.0 + LIVE_REPORT_TTL_SECONDS + 10
            get_cached_report('done-1')
        self.assertEqual(builds, ['done-1'])
