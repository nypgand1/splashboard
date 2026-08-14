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
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'IN_PROGRESS'})))
        self.assertFalse(game_page.set_interval_disabled('not-json'))
        self.assertFalse(game_page.set_interval_disabled(None))


class HiddenTabTests(unittest.TestCase):
    def test_hidden_tabs_do_not_rebuild(self):
        self.assertIs(game_page.update_pane_bs('{}', 'tab-lineup'), no_update)
        self.assertIs(game_page.update_pane_rotation('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_pbp('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_lineup('{}', 5, 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_report('{}', '{}', '{}', 'tab-bs'), no_update)
