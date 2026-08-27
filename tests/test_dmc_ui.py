import json
import os
import unittest
from unittest.mock import patch

import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
from dash_iconify import DashIconify

import app  # noqa: F401
from pages import game as game_page
from pages import home as home_page
from ui_kit import (
    EMPTY_GAME,
    EMPTY_GAME_NEXT,
    EMPTY_HOME,
    EMPTY_HOME_NEXT,
    ERROR_GAME,
    ERROR_HOME,
    loading_skeleton,
)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def walk(node):
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from walk(child)
        return
    yield node
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from walk(child)
    elif children is not None:
        yield from walk(children)
    left = getattr(node, 'leftSection', None)
    if left is not None:
        yield from walk(left)
    right = getattr(node, 'rightSection', None)
    if right is not None:
        yield from walk(right)


def find_type(tree, cls):
    return [node for node in walk(tree) if isinstance(node, cls)]


class NoBootstrapIconsTests(unittest.TestCase):
    def test_python_and_js_have_no_bootstrap_icon_classes(self):
        skip = {'.git', '__pycache__', 'scratch', 'venv', '.grok'}
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in skip]
            for name in files:
                if not name.endswith(('.py', '.js', '.css')):
                    continue
                path = os.path.join(root, name)
                if '/tests/' in path.replace('\\', '/'):
                    continue
                with open(path, 'r', encoding='utf-8') as handle:
                    text = handle.read()
                self.assertNotIn('bootstrap-icons', text, path)
                self.assertNotIn('bi bi-', text, path)


class FourStateTests(unittest.TestCase):
    def test_loading_skeleton_is_dmc_skeleton(self):
        tree = loading_skeleton()
        self.assertTrue(find_type(tree, dmc.Skeleton))
        self.assertNotIn('Loading...', str(tree))

    def test_home_error_and_empty(self):
        with patch.object(home_page, 'df_data', side_effect=RuntimeError('boom')):
            err = home_page.load_home_game_list('home-game-list')
        self.assertIsInstance(err, dmc.Alert)
        self.assertEqual(err.children, ERROR_HOME)

        with patch.object(home_page, 'df_data', return_value=pd.DataFrame()):
            empty = home_page.load_home_game_list('home-game-list')
        markup = str(empty)
        self.assertIn(EMPTY_HOME, markup)
        self.assertIn(EMPTY_HOME_NEXT, markup)

    def test_home_layout_uses_skeleton(self):
        layout = home_page.layout()
        self.assertTrue(find_type(layout, dmc.Skeleton))

    def test_game_error_and_empty_views(self):
        err = game_page.render_bs_children(json.dumps({'_ui': 'error', 'message': ERROR_GAME}))
        self.assertTrue(find_type(err, dmc.Alert))
        self.assertIn(ERROR_GAME, str(err))
        empty = game_page.render_bs_children('{}')
        markup = str(empty)
        self.assertIn(EMPTY_GAME, markup)
        self.assertIn(EMPTY_GAME_NEXT, markup)
        self.assertFalse(find_type(empty, dmc.Skeleton))

    def test_rotation_pbp_lineup_empty_and_error(self):
        for renderer in (
            game_page.render_rotation_children,
            game_page.render_pbp_children,
            lambda store: game_page.render_lineup_children(store, 5),
        ):
            err = renderer(json.dumps({'_ui': 'error', 'message': ERROR_GAME}))
            self.assertTrue(find_type(err, dmc.Alert), renderer)
            empty = renderer('{}')
            self.assertIn(EMPTY_GAME, str(empty))


class HomeAlignmentTests(unittest.TestCase):
    def test_every_home_column_is_center(self):
        df = pd.DataFrame([{
            'Time': '19:00', 'Status': 'FINISHED', 'rawStatus': 'FINISHED',
            'Game Type': 'B1', 'Venue': 'Arena', 'Home Team': 'A',
            'Score': '1 : 2', 'Away Team': 'B', 'fixtureId': 'g1',
        }])
        with patch.object(home_page, 'df_data', return_value=df):
            grid = home_page.load_home_game_list('home-game-list')
        self.assertIsInstance(grid, dag.AgGrid)
        fields = []
        for cdef in grid.columnDefs:
            fields.append(cdef['field'])
            self.assertEqual(cdef['headerClass'], 'ag-header-align-center')
            self.assertEqual(cdef['cellClass'], 'ag-cell-align-center')
            self.assertEqual(cdef['cellStyle']['textAlign'], 'center')
        self.assertEqual(
            fields,
            ['Time', 'Status', 'Game Type', 'Venue', 'Home Team', 'Score', 'Away Team'],
        )


class PlayerDotColorTests(unittest.TestCase):
    def test_player_and_lineup_section_dots_use_home_and_away_colors(self):
        def split_json(frame):
            return frame.to_json(orient='split')

        teams = ['Taipei Fubon Braves', 'Formosa Dreamers']
        bs = {
            'qt_pts_df': split_json(pd.DataFrame({'Team': teams, '1Q': [20, 18]})),
            'qt_foul_df': split_json(pd.DataFrame({'Team': teams, '1Q': [2, 3]})),
            'qt_tout_df': split_json(pd.DataFrame({'Team': teams, '1Q': [1, 0]})),
            't_adv_df': split_json(pd.DataFrame({'Team': teams, 'Pace': [70.0, 68.0], 'PPP': [1.1, 1.0]})),
            't_df': split_json(pd.DataFrame({'Team': teams, 'PTS': [88, 79]})),
            'k_df': split_json(pd.DataFrame({'Team': teams, 'PIP': [20, 18]})),
            'p_df_dict': {
                teams[0]: split_json(pd.DataFrame({'Player': ['A'], 'PTS': [10]})),
                teams[1]: split_json(pd.DataFrame({'Player': ['B'], 'PTS': [8]})),
            },
            'p_summary_dict': {},
        }
        tree = game_page.render_bs_children(json.dumps(bs))
        dots = [
            node.style.get('backgroundColor')
            for node in walk(tree)
            if isinstance(node, dmc.Box) and isinstance(getattr(node, 'style', None), dict)
            and node.style.get('width') == '8px'
        ]
        self.assertEqual(dots, ['#00b4d8', '#94a3b8'])

        lineup_store = json.dumps({
            '5': {
                teams[0]: split_json(pd.DataFrame({'Lineup': ['A-B'], 'PTS': [10]})),
                teams[1]: split_json(pd.DataFrame({'Lineup': ['C-D'], 'PTS': [8]})),
            }
        })
        lineup_tree = game_page.render_lineup_children(lineup_store, 5)
        lineup_dots = [
            node.style.get('backgroundColor')
            for node in walk(lineup_tree)
            if isinstance(node, dmc.Box) and isinstance(getattr(node, 'style', None), dict)
            and node.style.get('width') == '8px'
        ]
        self.assertEqual(lineup_dots, ['#00b4d8', '#94a3b8'])


class PbpAlignmentTests(unittest.TestCase):
    def test_pbp_columns_are_center(self):
        df = pd.DataFrame([
            {'Team': 'Home', 'Player': 'Lin', 'clock': '9:59', 'eventType': 'shot'},
        ])
        tree = game_page.render_pbp_children(df.to_json(orient='split'))
        grids = find_type(tree, dag.AgGrid)
        self.assertEqual(len(grids), 1)
        for cdef in grids[0].columnDefs:
            self.assertEqual(cdef['headerClass'], 'ag-header-align-center')
            self.assertEqual(cdef['cellClass'], 'ag-cell-align-center')
            self.assertEqual(cdef['cellStyle']['textAlign'], 'center')


class GameBannerStatusTests(unittest.TestCase):
    def test_banner_uses_raw_status_not_live_copy(self):
        tree = game_page.render_game_info_banner(json.dumps({
            'home_team': 'A', 'away_team': 'B',
            'home_score': '1', 'away_score': '2',
            'status': 'IN_PROGRESS',
            'date': '2026-01-01', 'time': '19:00', 'venue': 'Arena',
        }))
        markup = str(tree)
        self.assertIn('IN_PROGRESS', markup)
        self.assertNotIn('LIVE', markup)
        self.assertEqual(game_page.status_bucket('IN_PROGRESS'), 'live')


class PageDeleteSvgTests(unittest.TestCase):
    def test_js_page_delete_uses_inline_svg(self):
        js_path = os.path.join(REPO, 'assets', 'report_canvas.js')
        with open(js_path, 'r', encoding='utf-8') as handle:
            js = handle.read()
        self.assertIn('<svg', js)
        self.assertNotIn('bi-x-lg', js)
        self.assertNotIn('LIVE 🔴', js)
        self.assertIn('scoreClickable', js)
        self.assertIn('statusBucket', js)

    def test_table_pan_is_bound_without_visible_scrollbar_contract(self):
        js_path = os.path.join(REPO, 'assets', 'report_canvas.js')
        css_path = os.path.join(REPO, 'assets', 'report.css')
        with open(js_path, 'r', encoding='utf-8') as handle:
            js = handle.read()
        with open(css_path, 'r', encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('bindTablePan', js)
        self.assertIn('ag-center-cols-viewport', js)
        self.assertIn('panMoved', js)
        self.assertIn('is-scrollable', js)
        self.assertIn('cursor: grab', css)
        self.assertIn('cursor: grabbing', css)
        self.assertIn('.is-scrollable', css)
        self.assertIn('.braves-table-scroll', css)
        self.assertIn('scrollbar-width: none', css)


class GameLayoutContractTests(unittest.TestCase):
    def test_game_layout_uses_skeleton_and_dash_iconify(self):
        layout = game_page.layout('abc')
        self.assertTrue(find_type(layout, dmc.Skeleton))
        self.assertTrue(find_type(layout, DashIconify))
        markup = str(layout)
        self.assertNotIn('bi bi-', markup)
        self.assertNotIn('Loading...', markup)
