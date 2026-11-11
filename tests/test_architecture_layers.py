# -*- coding: utf-8 -*-
import threading
import unittest

import pandas as pd

from domain.clocks import clock_sort_seconds, clock_to_seconds, minutes_to_mmss, sum_clocks
from domain.ids import same_id, shirt_label, shirt_sort_key
from domain.periods import (
    build_period_chips,
    chip_spec,
    is_overtime_period,
    known_period_ids,
    period_id_value,
    period_label,
    resolve_period_ids,
)
from domain.rates import (
    efg_pct_display,
    flag_split_counts,
    lineup_ppp_display,
    recompute_rates,
    shot_made,
    shot_pct_display,
    sum_fields,
    three_decimal_rate,
    true_shooting,
)
from domain.schedule_filters import (
    LEAGUE_EASL,
    LEAGUE_PLG,
    choose_game_type,
    default_season_id,
    fixture_type_options,
    plain_fixture_type,
)
from inbound.cache.catalog_cache import clear_catalog_cache
from inbound.cache.frame_store import (
    PIN_OPEN_LIMIT,
    FixtureFrame,
    clear_bundles,
    clear_frames,
    clear_rotation_cache,
    get_bundle,
    get_frame,
    open_pinned_keys,
    put_bundle,
    put_frame,
    put_rotation_facts,
    rotation_facts,
)
from inbound.cache.live_cache import clear_runtime_caches
from inbound.cache.singleflight import SingleflightGroup
from ui.components import last_update_line, sized_select, to_jsonable
from ui.tables.stat_cards import card_header_rows, card_segments, edge_columns
from ui.tokens import BRAND_PRIMARY, HOME_DOT, HOME_STRIPE, MANTINE_THEME, WINNER_STYLE


class SingleflightTests(unittest.TestCase):
    def test_concurrent_callers_share_one_execution(self):
        group = SingleflightGroup()
        barrier = threading.Event()
        release = threading.Event()
        calls = []

        def work():
            calls.append(1)
            barrier.set()
            release.wait(timeout=2.0)
            return 'shared-result'

        results = [None, None]

        def caller(idx):
            results[idx] = group.do('k1', work)

        t0 = threading.Thread(target=caller, args=(0,))
        t1 = threading.Thread(target=caller, args=(1,))
        t0.start()
        barrier.wait(timeout=2.0)
        t1.start()
        release.set()
        t0.join(timeout=2.0)
        t1.join(timeout=2.0)

        self.assertEqual(len(calls), 1)
        self.assertEqual(results, ['shared-result', 'shared-result'])


class FrameStoreLRUTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()

    def tearDown(self):
        clear_runtime_caches()

    def test_pin_open_maintains_lru_up_to_limit(self):
        for idx in range(PIN_OPEN_LIMIT + 3):
            fid = f'fix-{idx}'
            put_frame(
                'org-1',
                fid,
                FixtureFrame('org-1', fid),
                pin='open',
            )
        pinned = open_pinned_keys()
        self.assertEqual(len(pinned), PIN_OPEN_LIMIT)
        self.assertNotIn(('org-1', 'fix-0'), pinned)
        self.assertIn(('org-1', f'fix-{PIN_OPEN_LIMIT + 2}'), pinned)
        self.assertIsNone(get_frame('org-1', 'fix-0'))
        self.assertIsNotNone(get_frame('org-1', f'fix-{PIN_OPEN_LIMIT + 2}'))

    def test_clear_runtime_caches_clears_frames_bundles_and_rotation(self):
        put_frame('org-1', 'fix-1', FixtureFrame('org-1', 'fix-1'), pin='open')
        put_bundle(('org-1', 'season-1'), {'games': {}})
        put_rotation_facts(('org-1', 'fix-1'), {'pbp': []})
        clear_runtime_caches()
        self.assertIsNone(get_frame('org-1', 'fix-1'))
        self.assertIsNone(get_bundle(('org-1', 'season-1')))
        self.assertIsNone(rotation_facts(('org-1', 'fix-1')))
        clear_catalog_cache()
        clear_frames()
        clear_bundles()
        clear_rotation_cache()


class DomainLayerTests(unittest.TestCase):
    def test_clocks_and_ids(self):
        self.assertEqual(clock_to_seconds('PT10M30S'), 630.0)
        self.assertEqual(minutes_to_mmss('PT05M04S'), '5:04')
        self.assertEqual(sum_clocks(['PT1M30S', 'PT2M30S']), 'PT4M0S')
        self.assertEqual(clock_sort_seconds('01:30'), 90.0)
        self.assertTrue(same_id('abc', 'abc'))
        self.assertEqual(shirt_sort_key('00'), (0, 0, ''))
        self.assertEqual(
            shirt_label('p1', {'p1': 'Lin'}, {'p1': {'shirtNumber': '7'}}),
            '#7 Lin',
        )

    def test_periods_and_rates(self):
        self.assertEqual(period_label(1), '1Q')
        self.assertEqual(period_label(5), 'OT')
        self.assertEqual(period_label(12), '2OT')
        self.assertTrue(is_overtime_period(5))
        self.assertEqual(period_id_value('2.0'), 2)
        self.assertEqual(known_period_ids(pd.DataFrame({'periodId': [1, 2, 5]})), {1, 2, 5})
        self.assertEqual(chip_spec('h1'), ((1, 2), True))
        chips = build_period_chips([1, 2, 3, 4, 5])
        self.assertTrue(any(c['label'] == 'OT' for c in chips))
        self.assertEqual(resolve_period_ids('h1'), (1, 2))
        self.assertEqual(three_decimal_rate(1 / 3), '.333')
        self.assertEqual(shot_pct_display(1, 2), '.500')
        self.assertEqual(lineup_ppp_display(23, 20), '1.15')
        self.assertEqual(efg_pct_display(2, 4, 1, 2), '58.3%')
        self.assertEqual(true_shooting(20, 15, 4), '59.7%')
        totals = sum_fields(
            pd.DataFrame([
                {'pointsTwoMade': 2, 'pointsTwoAttempted': 4},
                {'pointsTwoMade': 1, 'pointsTwoAttempted': 2},
            ]),
            ('pointsTwoMade', 'pointsTwoAttempted'),
        )
        recompute_rates(totals)
        self.assertEqual(totals['pointsTwoPercentage'], 50.0)
        self.assertTrue(shot_made(True))
        splits = flag_split_counts(
            pd.DataFrame([
                {
                    'entityId': 't1',
                    'periodId': 1,
                    'eventType': '2pt',
                    'success': True,
                    'options': {'fastBreak': True},
                },
            ]),
            ['t1'],
            None,
        )
        self.assertEqual(splits['t1']['FBP2M'], 1)
        self.assertEqual(splits['t1']['FBP2A'], 1)

    def test_schedule_filters(self):
        self.assertEqual(default_season_id(LEAGUE_PLG), default_season_id('plg'))
        self.assertNotEqual(default_season_id(LEAGUE_PLG), default_season_id(LEAGUE_EASL))
        self.assertEqual(plain_fixture_type('REGULAR'), 'REGULAR')
        opts = fixture_type_options([{'fixtureType': 'REGULAR'}, {'fixtureType': 'PLAYOFF'}])
        self.assertEqual(len(opts), 2)
        self.assertEqual(choose_game_type(opts, 'PLAYOFF'), 'PLAYOFF')


class UiLayerTests(unittest.TestCase):
    def test_tokens_and_shared_stat_cards(self):
        self.assertEqual(BRAND_PRIMARY, '#0077b6')
        self.assertEqual(HOME_DOT, '#00b4d8')
        self.assertEqual(HOME_STRIPE, BRAND_PRIMARY)
        self.assertEqual(WINNER_STYLE['color'], BRAND_PRIMARY)
        self.assertEqual(MANTINE_THEME['primaryColor'], 'bravesBlue')
        segs = card_segments('pace', ['Team', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R'])
        self.assertEqual(segs[-1][0], 'group')
        edges = edge_columns('pace', ['Team', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R'])
        self.assertIn('FT-R', edges)
        rows = card_header_rows('pace', ['Team', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R'])
        self.assertEqual(len(rows), 2)
        node = last_update_line('Last Update: 12:00', delayed=False)
        self.assertIsInstance(to_jsonable(node), dict)
        sel = sized_select('sel-id', 'probe-id', 'All Teams', [{'label': 'All Teams', 'value': 'all'}], 'all')
        self.assertIsInstance(to_jsonable(sel), dict)


if __name__ == '__main__':
    unittest.main()
