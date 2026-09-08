import json
import unittest

from dash import no_update

import app  # noqa: F401
from pages import game as game_page


class SafeLoadsTests(unittest.TestCase):
    def test_bad_json_and_none_are_empty_dicts(self):
        self.assertEqual(game_page.safe_loads(None), {})
        self.assertEqual(game_page.safe_loads('not-json'), {})
        self.assertEqual(game_page.safe_loads('null'), {})
        self.assertEqual(game_page.safe_loads('{"status": "FINISHED"}'), {'status': 'FINISHED'})


class IntervalGateTests(unittest.TestCase):
    def test_finished_disables_interval(self):
        self.assertTrue(game_page.set_interval_disabled(json.dumps({'status': 'FINISHED'})))
        self.assertTrue(game_page.set_interval_disabled(json.dumps({'status': 'CONFIRMED'})))
        self.assertTrue(game_page.set_interval_disabled(json.dumps({'status': 'SCHEDULED'})))
        self.assertTrue(game_page.set_interval_disabled(json.dumps({'status': 'CANCELLED'})))
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'IN_PROGRESS'})))
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'PENDING'})))
        self.assertTrue(game_page.set_interval_disabled('not-json'))
        self.assertTrue(game_page.set_interval_disabled(None))


class HiddenTabTests(unittest.TestCase):
    def test_hidden_tabs_do_not_rebuild(self):
        self.assertIs(game_page.update_pane_bs('{}', 'tab-lineup'), no_update)
        self.assertIs(game_page.update_pane_rotation('{}', 'tab-bs'), no_update)
        self.assertEqual(
            game_page.update_rotation_graph('{}', {}, 'tab-bs'),
            (no_update, no_update, no_update),
        )
        self.assertIs(game_page.update_pane_pbp('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_lineup(5, 'tab-bs', '{}', None), no_update)
        self.assertIs(game_page.update_pane_report('tab-bs', '{}', '{}', '{}', None), no_update)

    def test_report_tab_hidden_for_live_and_shown_when_finished(self):
        live_style, live_tab = game_page.toggle_report_tab(
            json.dumps({'status': 'IN_PROGRESS'}),
            'tab-bs',
        )
        self.assertEqual(live_style, {'display': 'none'})
        self.assertIs(live_tab, no_update)

        live_on_report_style, switched = game_page.toggle_report_tab(
            json.dumps({'status': 'PENDING'}),
            'tab-report',
        )
        self.assertEqual(live_on_report_style, {'display': 'none'})
        self.assertEqual(switched, 'tab-bs')

        done_style, done_tab = game_page.toggle_report_tab(
            json.dumps({'status': 'FINISHED'}),
            'tab-bs',
        )
        self.assertEqual(done_style, {})
        self.assertIs(done_tab, no_update)

        scheduled_style, _ = game_page.toggle_report_tab(
            json.dumps({'status': 'SCHEDULED'}),
            'tab-bs',
        )
        self.assertEqual(scheduled_style, {'display': 'none'})


class RotationViewTests(unittest.TestCase):
    def _payload(self):
        return {
            'periods': [
                {'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0},
                {'id': 2, 'label': '2Q', 'seconds': 120, 'start': 120.0, 'end': 240.0},
            ],
            'runs': [
                {'side': 'home', 'home_pts': 10, 'away_pts': 2, 'start': 30.0, 'end': 80.0, 'delta': 8},
            ],
            'teams': [{'side': 'home', 'players': []}],
        }

    def test_period_zoom_and_all_reset(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            'rotation-period', '1', False, [], None, store, 'g1', {}, {},
        )
        self.assertEqual(view['x0'], 0.0)
        self.assertEqual(view['x1'], 120.0)
        self.assertEqual(view['t'], 0.0)
        self.assertEqual(view['slice_width'], 120.0)
        reset = game_page.apply_rotation_view_event(
            'rotation-period', 'all', False, [], None, store, 'g1', view, {},
        )
        self.assertIsNone(reset['x0'])
        self.assertIsNone(reset['x1'])
        self.assertIsNone(reset['slice_width'])

    def test_run_click_returns_to_all_and_sets_playhead(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            {'type': 'rotation-run', 'index': 0},
            '1',
            False,
            [1],
            None,
            store,
            'g1',
            {'period': '1', 'x0': 0.0, 'x1': 120.0, 'slice_width': 120.0, 't': 0.0},
            {},
        )
        self.assertEqual(view['t'], 30.0)
        self.assertEqual(view['period'], 'all')
        self.assertIsNone(view['x0'])
        self.assertIsNone(view['x1'])
        self.assertIsNone(view['slice_width'])

    def test_relayout_updates_period_chip_from_window(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            'rotation-graph.relayoutData',
            '1',
            False,
            [],
            None,
            store,
            'g1',
            {'period': '1', 'x0': 0.0, 'x1': 120.0, 'slice_width': 120.0, 'axis_rev': 0},
            {},
            relayout_data={'xaxis.range[0]': 80.0, 'xaxis.range[1]': 200.0},
        )
        self.assertEqual(view['period'], '2')
        self.assertEqual(view['x0'], 80.0)
        self.assertEqual(view['slice_width'], 120.0)

    def test_graph_click_sets_playhead_to_clicked_time_not_bar_end(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            'rotation-click-t',
            'all',
            False,
            [],
            55.0,
            store,
            'g1',
            {'x0': None, 'x1': None, 't': None},
            {},
        )
        self.assertEqual(view['t'], 55.0)
        self.assertIsNone(view['x0'])

    def test_period_chip_sets_playhead_to_period_start(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            'rotation-period', '2', False, [], None, store, 'g1', {}, {},
        )
        self.assertEqual(view['t'], 120.0)
        self.assertEqual(view['x0'], 120.0)

    def test_finished_playhead_defaults_to_game_end(self):
        payload = self._payload()
        t = game_page.resolve_rotation_playhead(payload, {}, {'status': 'FINISHED'})
        self.assertEqual(t, 240.0)

    def test_live_follow_uses_now_until_unfollowed(self):
        payload = {
            'periods': [{'id': 1, 'start': 0.0, 'end': 120.0}],
            'margin': [{'t': 80.0, 'desc': 'Lin 3PT'}, {'t': 120.0, 'desc': 'Game end'}],
            'teams': [],
        }
        now = game_page.resolve_rotation_playhead(
            payload, {'follow_live': True}, {'status': 'IN_PROGRESS'},
        )
        self.assertEqual(now, 80.0)
        parked = game_page.resolve_rotation_playhead(
            payload, {'follow_live': False, 't': 20.0}, {'status': 'IN_PROGRESS'},
        )
        self.assertEqual(parked, 20.0)

    def test_graph_click_unfollows_live(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            'rotation-click-t',
            'all',
            False,
            [],
            40.0,
            store,
            'g1',
            {'follow_live': True, 't': None},
            {'status': 'IN_PROGRESS'},
        )
        self.assertEqual(view['t'], 40.0)
        self.assertFalse(view['follow_live'])

    def test_live_chip_reattaches_follow(self):
        store = json.dumps({
            'periods': [{'id': 1, 'start': 0.0, 'end': 120.0}],
            'margin': [{'t': 80.0, 'desc': 'Lin 3PT'}],
            'teams': [],
        })
        view = game_page.apply_rotation_view_event(
            'rotation-live',
            'all',
            False,
            [],
            None,
            store,
            'g1',
            {'follow_live': False, 't': 20.0},
            {'status': 'IN_PROGRESS'},
        )
        self.assertTrue(view['follow_live'])
        self.assertEqual(view['t'], 80.0)

    def test_live_chip_hidden_when_finished(self):
        style, variant = game_page.update_rotation_live_chip(
            json.dumps({'status': 'FINISHED'}),
            {'follow_live': True},
        )
        self.assertEqual(style.get('display'), 'none')
        style_live, variant_live = game_page.update_rotation_live_chip(
            json.dumps({'status': 'IN_PROGRESS'}),
            {'follow_live': True},
        )
        self.assertNotEqual(style_live.get('display'), 'none')
        self.assertEqual(variant_live, 'filled')

    def test_game_id_resets_view(self):
        view = game_page.apply_rotation_view_event(
            'game_id', 'all', True, [], None, '{}', 'g2',
            {'period': '1', 't': 9, 'x0': 1, 'x1': 2, 'show_dnp': True},
            {},
        )
        self.assertEqual(view, game_page.DEFAULT_ROTATION_VIEW)


class TabsDmcContractTests(unittest.TestCase):
    def test_game_tab_order_is_lineup_before_pbp(self):
        import dash_mantine_components as dmc
        from tests.test_dmc_ui import find_type
        tree = game_page.layout('g1')
        values = [node.value for node in find_type(tree, dmc.TabsTab)]
        self.assertEqual(
            values,
            ['tab-bs', 'tab-rotation', 'tab-lineup', 'tab-pbp', 'tab-report'],
        )

    def test_game_page_uses_dmc_tabs(self):
        import os
        page_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', 'game.py')
        with open(page_path, 'r') as f:
            code = f.read()
        self.assertIn('dmc.Tabs', code)
        self.assertIn('dmc.TabsList', code)
        self.assertIn('dmc.TabsTab', code)
        self.assertLess(
            code.find('dmc.TabsTab("Lineup Stats"'),
            code.find('dmc.TabsTab("Play-By-Play"'),
        )
        self.assertNotIn('dbc.Tabs', code)
        self.assertNotIn('dbc.Tab(', code)
        self.assertIn('tabler:table', code)
        self.assertNotIn('bi bi-', code)
        self.assertIn('loading_skeleton', code)


class GridDmcContractTests(unittest.TestCase):
    def test_game_page_uses_dmc_simple_grid_without_dbc_row_col(self):
        import os
        page_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', 'game.py')
        with open(page_path, 'r') as f:
            code = f.read()
        self.assertIn('dmc.SimpleGrid', code)
        self.assertIn('"lg": 3', code)
        self.assertIn('"lg": 2', code)
        self.assertNotIn('alwaysShowHorizontalScroll', code)
        self.assertNotIn('"sm": 3', code)
        self.assertNotIn('dbc.Row', code)
        self.assertNotIn('dbc.Col', code)


