import base64
import json
import unittest
from unittest.mock import patch

import dash_mantine_components as dmc
import pandas as pd
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
        self.assertEqual(
            game_page.update_pane_bs('{}', 'tab-lineup'),
            (no_update, no_update),
        )
        self.assertIs(game_page.update_pane_rotation('{}', 'tab-bs'), no_update)
        self.assertEqual(
            game_page.update_rotation_graph('{}', {}, 'tab-bs'),
            (no_update, no_update, no_update),
        )
        self.assertIs(game_page.update_pane_pbp('{}', 'tab-bs'), no_update)
        self.assertIs(game_page.update_pane_lineup(5, 'tab-bs', '{}', None), no_update)
        self.assertIs(
            game_page.update_pane_report('tab-bs', '', '{}', '{}', '{}', None),
            no_update,
        )

    def test_report_tab_does_not_rebuild_mounted_workspace(self):
        self.assertIs(
            game_page.update_pane_report(
                'tab-report', '1', '{}', '{}', '{}', 'g1',
            ),
            no_update,
        )

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


def _split(frame):
    return frame.to_json(orient='split')


def _walk_text(node, found):
    if isinstance(node, (list, tuple)):
        for child in node:
            _walk_text(child, found)
        return
    children = getattr(node, 'children', None)
    if isinstance(children, str):
        found.append(children)
    elif children is not None:
        _walk_text(children, found)


class BoxScorePeriodUiTests(unittest.TestCase):
    def _payload(self):
        teams = ['Home', 'Away']
        return {
            'qt_pts_df': _split(pd.DataFrame({'Team': teams, '1Q': [20, 18], '2Q': [22, 16]})),
            'qt_foul_df': _split(pd.DataFrame({'Team': teams, '1Q': [2, 3]})),
            'qt_tout_df': _split(pd.DataFrame({'Team': teams, '1Q': [1, 0]})),
            't_adv_df': _split(pd.DataFrame({'Team': teams, 'Pace': [70.0, 68.0], 'PPP': [1.1, 1.0]})),
            't_df': _split(pd.DataFrame({'Team': teams, 'PTS': [88, 79]})),
            'k_df': _split(pd.DataFrame({'Team': teams, 'PIP': [20, 18]})),
            'p_df_dict': {
                'Home': _split(pd.DataFrame({'Player': ['Lin'], 'PTS': [10]})),
                'Away': _split(pd.DataFrame({'Player': ['Chen'], 'PTS': [8]})),
            },
            'p_summary_dict': {},
            'period_chips': [
                {'label': 'All', 'value': 'all'},
                {'label': '1Q', 'value': '1'},
            ],
            'slices': {
                '1': {
                    't_adv_df': _split(pd.DataFrame({
                        'Team': teams, 'Pace': ['4.0', '4.0'], 'PPP': ['1.20', ''],
                    })),
                    't_df': _split(pd.DataFrame({'Team': teams, 'PTS': [41, 33]})),
                    'k_df': _split(pd.DataFrame({'Team': teams, 'PIP': [9, 8]})),
                    'p_df_dict': {
                        'Home': _split(pd.DataFrame({'Player': ['Lin'], 'PTS': [4]})),
                        'Away': _split(pd.DataFrame({'Player': ['Chen'], 'PTS': [3]})),
                    },
                    'p_summary_dict': {},
                },
            },
        }

    def test_chip_filters_box_tables_and_keeps_score(self):
        tree = game_page.render_bs_children(json.dumps(self._payload()), '1')
        self.assertFalse(any(
            isinstance(node, dmc.SegmentedControl) and getattr(node, 'id', None) == 'bs-period-control'
            for node in _nodes(tree)
        ))
        texts = []
        _walk_text(tree, texts)
        self.assertLess(texts.index('SCORE'), texts.index('PACE & 4 FACTORS'))
        self.assertIn('22', texts)
        self.assertIn('41', texts)
        self.assertNotIn('88', texts)

    def test_period_control_is_in_the_initial_layout(self):
        tree = game_page.layout('g1')
        pane = next(node for node in _nodes(tree) if getattr(node, 'id', None) == 'pane-bs')
        self.assertEqual(
            [getattr(child, 'id', None) for child in pane.children],
            ['bs-matrix', 'bs-period-bar', 'bs-detail'],
        )
        bar = pane.children[1]
        control = bar.children[0]
        self.assertEqual(control.id, 'bs-period-control')
        self.assertEqual(control.data, [{'label': 'All', 'value': 'all'}])
        self.assertEqual(control.value, 'all')
        self.assertEqual(control.radius, 'md')
        self.assertEqual(control.size, 'xs')
        self.assertEqual(bar.style, {'display': 'none'})
        controls = [
            node for node in _nodes(tree)
            if isinstance(node, dmc.SegmentedControl) and node.id == 'bs-period-control'
        ]
        self.assertEqual(len(controls), 1)

    def test_period_bar_shows_store_chips_after_the_box_arrives(self):
        data, style = game_page.period_bar_state(self._payload())
        self.assertEqual([item['label'] for item in data], ['All', '1Q'])
        self.assertEqual(style, {'display': 'flex'})
        hidden_data, hidden_style = game_page.period_bar_state({})
        self.assertEqual(hidden_data, [{'label': 'All', 'value': 'all'}])
        self.assertEqual(hidden_style, {'display': 'none'})
        error_data, error_style = game_page.period_bar_state({'_ui': 'error'})
        self.assertEqual(error_data, [{'label': 'All', 'value': 'all'}])
        self.assertEqual(error_style, {'display': 'none'})

    def test_missing_chips_keep_the_current_box_score(self):
        payload = self._payload()
        payload.pop('period_chips')
        payload.pop('slices')
        tree = game_page.render_bs_children(json.dumps(payload))
        texts = []
        _walk_text(tree, texts)
        self.assertNotIn('41', texts)
        self.assertIn('88', texts)
        self.assertFalse(any(
            isinstance(node, dmc.SegmentedControl) and getattr(node, 'id', None) == 'bs-period-control'
            for node in _nodes(tree)
        ))

    def test_game_change_resets_the_chip_and_the_interval_does_not(self):
        self.assertEqual(game_page.resolve_bs_period('game_id', '1'), 'all')
        self.assertEqual(game_page.resolve_bs_period('bs-period-control', 'h1'), 'h1')
        self.assertEqual(game_page.resolve_bs_period('bs-period-control', None), 'all')
        self.assertEqual(game_page.resolve_bs_period('interval-component', '2'), '2')

    def test_store_keeps_full_game_tables_beside_slices(self):
        class _Report:
            def get_period_team_pts_df(self):
                return pd.DataFrame({'Team': ['Home'], '1Q': [20]})

            def get_period_team_fouls_df(self):
                return pd.DataFrame({'Team': ['Home'], '1Q': [2]})

            def get_period_team_timeout_df(self):
                return pd.DataFrame({'Team': ['Home'], '1Q': [1]})

            def get_team_advance_stats_df(self):
                return pd.DataFrame({'Team': ['Home'], 'Pace': [70.0]})

            def get_team_stats_df(self):
                return pd.DataFrame({'Team': ['Home'], 'PTS': [88]})

            def get_team_key_stats_df(self):
                return pd.DataFrame({'Team': ['Home'], 'PIP': [20]})

            def get_player_stats_json_dict(self):
                return {'Home': _split(pd.DataFrame({'Player': ['Lin'], 'PTS': [10]}))}

            def get_player_box_score_summary_json_dict(self):
                return {}

            def box_score_period_chips(self):
                return [{'label': 'All', 'value': 'all'}, {'label': '1Q', 'value': '1'}]

            def box_score_slice_json(self):
                return {'1': {'t_df': 'slice-frame'}}

        with patch.object(game_page, 'get_cached_report', return_value=_Report()):
            payload = json.loads(game_page.update_bs_store(1, 'g1'))
        self.assertIn('88', payload['t_df'])
        self.assertNotIn('slice-frame', payload['t_df'])
        self.assertEqual(payload['slices']['1']['t_df'], 'slice-frame')
        self.assertEqual(payload['period_chips'][0]['value'], 'all')


def _nodes(node):
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from _nodes(child)
        return
    yield node
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _nodes(child)
    elif children is not None:
        yield from _nodes(children)

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
            ['tab-bs', 'tab-rotation', 'tab-shot-chart', 'tab-lineup', 'tab-pbp', 'tab-report'],
        )
        ids = {getattr(node, 'id', None) for node in _nodes(tree)}
        self.assertIn('shot-chart-period', ids)
        self.assertIn('shot-chart-player-away', ids)
        self.assertIn('shot-chart-player-home', ids)
        self.assertIn('wrap-shot-chart', ids)

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


def _shot_frame():
    return pd.DataFrame([
        {
            'entityId': 'home', 'personId': 'p-home', 'Player': 'Lin', 'shirtNumber': '7',
            'eventType': '2pt', 'periodId': 1, 'success': True, 'x': 6, 'y': 50,
        },
        {
            'entityId': 'away', 'personId': 'p-away', 'Player': 'Chen', 'shirtNumber': '9',
            'eventType': '2pt', 'periodId': 2, 'success': False, 'x': 94, 'y': 50,
        },
        {
            'entityId': 'home', 'personId': 'p-home', 'Player': 'Lin', 'shirtNumber': '7',
            'eventType': 'freeThrow', 'periodId': 1, 'success': True, 'x': 6, 'y': 50,
        },
    ]).to_json(orient='split')


class ShotChartUiTests(unittest.TestCase):
    def test_game_change_resets_filters_and_the_interval_does_not(self):
        self.assertEqual(
            game_page.resolve_shot_chart_filters('game_id', '1', 'p-home', 'p-away'),
            ('all', 'all', 'all'),
        )
        self.assertEqual(
            game_page.resolve_shot_chart_filters('interval-component', 'h1', 'p-home', 'p-away'),
            ('h1', 'p-home', 'p-away'),
        )

    def test_period_chips_come_from_play_by_play(self):
        data, style = game_page.shot_chart_period_state(_shot_frame())
        self.assertEqual([item['label'] for item in data], ['All', '1Q', '2Q', '1H'])
        self.assertEqual(style, {'display': 'flex'})
        hidden, hidden_style = game_page.shot_chart_period_state(json.dumps({'_ui': 'error'}))
        self.assertEqual(hidden, [{'label': 'All', 'value': 'all'}])
        self.assertEqual(hidden_style, {'display': 'none'})

    def test_player_menus_stay_on_full_game_attempts(self):
        info = json.dumps({
            'away_team_id': 'away', 'home_team_id': 'home',
            'away_team': 'Dreamers', 'home_team': 'Braves',
        })
        away, home = game_page.shot_chart_player_state(_shot_frame(), info)
        self.assertEqual([item['label'] for item in away], ['All', '#9 Chen'])
        self.assertEqual([item['label'] for item in home], ['All', '#7 Lin'])

    def test_ready_panel_draws_both_courts(self):
        info = json.dumps({
            'away_team_id': 'away', 'home_team_id': 'home',
            'away_team': 'Dreamers', 'home_team': 'Braves',
        })
        panel = game_page.shot_chart_panel(_shot_frame(), info, 'all', 'all', 'all')
        self.assertEqual(panel['status'], 'ready')
        home = base64.b64decode(panel['home_src'].split(',', 1)[1]).decode('utf-8')
        away = base64.b64decode(panel['away_src'].split(',', 1)[1]).decode('utf-8')
        self.assertIn('100.0', home)
        self.assertIn(' %', home)
        self.assertNotIn('100.0%', home)
        self.assertIn('1 / 1', home)
        self.assertIn('0.0', away)
        self.assertIn(' %', away)
        self.assertIn('0 / 1', away)
        pane, pane_style, courts_style, away_name, home_name, away_img, home_img = game_page.shot_chart_outputs(panel)
        self.assertEqual(pane, [])
        self.assertEqual(pane_style, {'display': 'none'})
        self.assertEqual(courts_style, {})
        self.assertEqual(away_name, 'Dreamers')
        self.assertEqual(home_name, 'Braves')
        self.assertEqual(home_img.alt, 'Braves shot chart')

    def test_empty_and_error_use_the_game_copy(self):
        from ui_kit import EMPTY_GAME, EMPTY_GAME_NEXT, ERROR_GAME
        empty_pane, _, empty_courts, *_rest = game_page.shot_chart_outputs(
            game_page.shot_chart_panel('{}', '{}', 'all', 'all', 'all')
        )
        texts = []
        _walk_text(empty_pane, texts)
        self.assertIn(EMPTY_GAME, texts)
        self.assertIn(EMPTY_GAME_NEXT, texts)
        self.assertEqual(empty_courts, {'display': 'none'})
        error_pane, _, error_courts, *_rest = game_page.shot_chart_outputs(
            game_page.shot_chart_panel(json.dumps({'_ui': 'error'}), '{}', 'all', 'all', 'all')
        )
        error_text = []
        _walk_text(error_pane, error_text)
        self.assertIn(ERROR_GAME, error_text)
        self.assertEqual(error_courts, {'display': 'none'})
        self.assertEqual(
            game_page.shot_chart_panel(None, '{}', 'all', 'all', 'all')['status'],
            'loading',
        )

    def test_rows_without_shots_still_show_the_court(self):
        frame = pd.DataFrame([{
            'entityId': 'home', 'eventType': 'substitution', 'periodId': 1,
        }]).to_json(orient='split')
        info = json.dumps({'home_team_id': 'home', 'away_team_id': 'away', 'home_team': 'Braves', 'away_team': 'Dreamers'})
        panel = game_page.shot_chart_panel(frame, info, '1', 'all', 'all')
        self.assertEqual(panel['status'], 'ready')
        svg = base64.b64decode(panel['home_src'].split(',', 1)[1]).decode('utf-8')
        self.assertIn('>-</text>', svg)
        self.assertNotIn('No shots', svg)

    def test_both_courts_share_one_capped_card(self):
        import dash_mantine_components as dmc
        tree = game_page.layout('g1')
        papers = [node for node in _nodes(tree) if getattr(node, 'id', None) == 'shot-chart-card']
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertIsInstance(paper, dmc.Paper)
        self.assertTrue(paper.withBorder)
        self.assertEqual(paper.radius, 'md')
        self.assertEqual(paper.shadow, 'xs')
        self.assertEqual(paper.p, 'md')
        self.assertEqual(paper.style.get('maxWidth'), '808px')
        inside = list(_nodes(paper))
        ids = {getattr(node, 'id', None) for node in inside}
        self.assertIn('shot-chart-period', ids)
        self.assertIn('shot-chart-courts', ids)
        self.assertIn('pane-shot-chart', ids)
        grid = next(node for node in inside if getattr(node, 'id', None) == 'shot-chart-courts')
        for child in grid.children:
            self.assertEqual(child.style['maxWidth'], '380px')
        wrap = next(node for node in _nodes(tree) if getattr(node, 'id', None) == 'wrap-shot-chart')
        self.assertEqual(getattr(wrap.children[0], 'id', None), 'shot-chart-last-update')
        self.assertIn('Last Update', str(wrap.children[0]))
        self.assertEqual(getattr(wrap.children[1], 'id', None), 'shot-chart-card')
        self.assertIs(game_page.update_shot_chart_last_update('{}', 'tab-bs'), no_update)
        self.assertIn('Last Update', str(game_page.update_shot_chart_last_update('{}', 'tab-shot-chart')))

    def test_hidden_tab_does_not_rebuild_the_chart(self):
        result = game_page.update_shot_chart('{}', '{}', 'all', 'all', 'all', 'tab-bs')
        self.assertTrue(all(item is no_update for item in result))


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


