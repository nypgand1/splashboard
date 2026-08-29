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


