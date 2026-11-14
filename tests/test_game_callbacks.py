import base64
import json
import unittest
from unittest.mock import Mock, patch

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


class WarmupGateTests(unittest.TestCase):
    def _publish(self, n, triggered, status):
        report = Mock()
        report.get_play_by_play_df.return_value = pd.DataFrame()
        report.get_all_lineup_stats_json_dict.return_value = {'size': 5}
        report.get_matchup_payload.return_value = {}
        report.get_rotation_payload.return_value = {}
        info = {
            'status': status,
            'time': '19:00',
            'home_team_id': 'h',
            'away_team_id': 'a',
            'home_score': '88',
            'away_score': '79',
        }
        with patch.object(game_page, '_fixture_status', return_value=status), \
                patch.object(game_page, 'get_cached_report', return_value=report) as cached, \
                patch.object(game_page, 'warmup_game_report') as warmup, \
                patch.object(game_page, '_triggered_id', return_value=triggered), \
                patch.object(game_page, '_info_dict', return_value=info), \
                patch.object(game_page, '_box_payload', return_value='{}'):
            outputs = game_page.publish_finished_snapshot(n, 'gid', 'plg')
        return outputs, warmup, cached

    def test_finished_load_starts_warmup_before_the_interval_ticks(self):
        outputs, warmup, cached = self._publish(0, 'interval-component', 'FINISHED')
        warmup.assert_called_once_with('gid', organization_id='b1vqz')
        cached.assert_called_once_with('gid', 'b1vqz', pin='open')
        self.assertIn('"size": 5', outputs[2])

    def test_game_or_league_change_warms_a_finished_game(self):
        _, by_game, _ = self._publish(4, 'game_id', 'CONFIRMED')
        by_game.assert_called_once_with('gid', organization_id='b1vqz')
        _, by_league, _ = self._publish(4, 'game_league', 'FINISHED')
        by_league.assert_called_once_with('gid', organization_id='b1vqz')

    def test_later_tick_and_unfinished_load_do_not_start_warmup(self):
        outputs, later, _ = self._publish(3, 'interval-component', 'FINISHED')
        later.assert_not_called()
        self.assertIn('"size": 5', outputs[2])
        live, live_warmup, live_cached = self._publish(0, 'game_id', 'IN_PROGRESS')
        live_warmup.assert_not_called()
        live_cached.assert_not_called()
        self.assertTrue(all(item is no_update for item in live))
        abandoned, abandoned_warmup, _ = self._publish(0, 'game_id', 'ABANDONED')
        abandoned_warmup.assert_not_called()
        self.assertIn('"size": 5', abandoned[2])


class IntervalGateTests(unittest.TestCase):
    def test_finished_keeps_the_interval_on(self):
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'FINISHED'})))
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'CONFIRMED'})))
        self.assertTrue(game_page.set_interval_disabled(json.dumps({'status': 'SCHEDULED'})))
        self.assertTrue(game_page.set_interval_disabled(json.dumps({'status': 'CANCELLED'})))
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'IN_PROGRESS'})))
        self.assertFalse(game_page.set_interval_disabled(json.dumps({'status': 'PENDING'})))
        self.assertFalse(game_page.set_interval_disabled('not-json'))
        self.assertFalse(game_page.set_interval_disabled(None))


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


def _callback_specs(output_id):
    from dash._callback import GLOBAL_CALLBACK_LIST
    return [item for item in GLOBAL_CALLBACK_LIST if item['output'] == output_id]


def _dep_pairs(deps):
    return {(item['id'], item['property']) for item in deps}


class LiveRefreshWiringTests(unittest.TestCase):
    def test_lineup_grids_follow_store_and_report_does_not(self):
        lineup = _callback_specs('pane-lineup.children')
        self.assertEqual(len(lineup), 1)
        self.assertIn(('lineup_store', 'data'), _dep_pairs(lineup[0]['inputs']))
        self.assertIn(('lineup_size_dropdown', 'value'), _dep_pairs(lineup[0]['inputs']))
        self.assertIn(('tabs', 'value'), _dep_pairs(lineup[0]['inputs']))
        self.assertIn(('lineup-show-opp', 'checked'), _dep_pairs(lineup[0]['state']))
        self.assertNotIn(('lineup_store', 'data'), _dep_pairs(lineup[0]['state']))

        report = _callback_specs('pane-report.children')
        self.assertEqual(len(report), 1)
        self.assertEqual(
            {item['id'] for item in report[0]['inputs']},
            {'tabs', 'report-pane-ready'},
        )
        self.assertIn(('lineup_store', 'data'), _dep_pairs(report[0]['state']))
        self.assertNotIn(('lineup_store', 'data'), _dep_pairs(report[0]['inputs']))

    def test_home_reload_reads_the_filter_store(self):
        from dash._callback import GLOBAL_CALLBACK_LIST

        home = [
            item for item in GLOBAL_CALLBACK_LIST
            if 'home-game-list.children' in item['output']
        ]
        self.assertEqual(len(home), 1)
        self.assertEqual(
            [(item['id'], item['property']) for item in home[0]['inputs']],
            [
                ('home-interval', 'n_intervals'),
                ('home-scope-store', 'data'),
            ],
        )
        self.assertIn(('home-filter-store', 'data'), _dep_pairs(home[0]['state']))
        self.assertIn('home-filter-store.data', home[0]['output'])
        watched = {item['id'] for item in home[0]['inputs'] + home[0]['state']}
        self.assertNotIn('home-show', watched)
        self.assertNotIn('home-game-type', watched)
        self.assertNotIn('home-league', watched)
        self.assertNotIn('home-season', watched)
        self.assertNotIn('home-team', watched)

    def test_home_controls_skeleton_the_list_not_the_interval(self):
        from dash._callback import GLOBAL_CALLBACK_LIST

        listed = [
            item for item in GLOBAL_CALLBACK_LIST
            if 'home-schedule-list.children' in item['output']
        ]
        clientside = [item for item in listed if item.get('clientside_function')]
        server = [item for item in listed if not item.get('clientside_function')]
        self.assertEqual(len(clientside), 1)
        self.assertEqual(len(server), 1)
        self.assertEqual(
            [item['id'] for item in clientside[0]['inputs']],
            ['home-league', 'home-season'],
        )
        self.assertNotIn('home-interval', {item['id'] for item in clientside[0]['inputs']})
        self.assertTrue(clientside[0]['prevent_initial_call'])
        self.assertIn('@', clientside[0]['output'])
        self.assertIn('@', server[0]['output'])
        self.assertIn(('home-schedule-store', 'data'), _dep_pairs(server[0]['inputs']))
        self.assertNotIn(('home-interval', 'n_intervals'), _dep_pairs(server[0]['inputs']))

    def test_open_lineup_size_uses_store_or_recomputes(self):
        with patch.object(game_page, 'render_lineup_children', return_value='painted') as render, \
                patch.object(game_page, 'get_cached_report') as cached, \
                patch.object(game_page, '_info_dict', return_value={}):
            painted = game_page.update_pane_lineup(
                '5', 'tab-lineup', '{"5": {"Home": "{}"}}', 'g1', True,
            )
        self.assertEqual(painted, 'painted')
        cached.assert_not_called()
        self.assertEqual(render.call_args.args[1], 5)
        self.assertTrue(render.call_args.kwargs['show_opp'])

        report = cached.return_value
        report.get_all_lineup_stats_json_dict.return_value = {'4': {'Home': '{}'}}
        with patch.object(game_page, 'render_lineup_children', return_value='sized') as render, \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, '_info_dict', return_value={}):
            painted = game_page.update_pane_lineup(
                '4', 'tab-lineup', '{"5": {"Home": "{}"}}', 'g1', False,
            )
        self.assertEqual(painted, 'sized')
        report.get_all_lineup_stats_json_dict.assert_called_once_with(sizes=(4,))
        self.assertFalse(render.call_args.kwargs['show_opp'])
        self.assertIn('"4"', render.call_args.args[0])

    def test_banner_clock_does_not_wake_box_lineup_or_shot_chart(self):
        from dash._callback import GLOBAL_CALLBACK_LIST

        def specs(fragment):
            return [item for item in GLOBAL_CALLBACK_LIST if fragment in item['output']]

        box = specs('bs-score-scroll.children')
        self.assertEqual(len(box), 1)
        self.assertNotIn(('match_info_store', 'data'), _dep_pairs(box[0]['inputs']))
        self.assertIn(('match_info_store', 'data'), _dep_pairs(box[0]['state']))

        lineup = _callback_specs('pane-lineup.children')
        self.assertEqual(len(lineup), 1)
        self.assertNotIn(('match_info_store', 'data'), _dep_pairs(lineup[0]['inputs']))
        self.assertIn(('match_info_store', 'data'), _dep_pairs(lineup[0]['state']))

        chart = specs('pane-shot-chart.children')
        self.assertEqual(len(chart), 1)
        self.assertNotIn(('match_info_store', 'data'), _dep_pairs(chart[0]['inputs']))
        self.assertIn(('match_info_store', 'data'), _dep_pairs(chart[0]['state']))

        players = specs('shot-chart-player-away.data')
        self.assertEqual(len(players), 1)
        self.assertIn(('tabs', 'value'), _dep_pairs(players[0]['inputs']))
        self.assertNotIn(('match_info_store', 'data'), _dep_pairs(players[0]['inputs']))
        self.assertIn(('match_info_store', 'data'), _dep_pairs(players[0]['state']))

        periods = specs('shot-chart-period.data')
        self.assertEqual(len(periods), 1)
        self.assertIn(('tabs', 'value'), _dep_pairs(periods[0]['inputs']))
        self.assertNotIn('match_info_store', {item['id'] for item in periods[0]['inputs']})

        playhead = specs('rotation_view_store.data')
        self.assertEqual(len(playhead), 1)
        self.assertIn(('match_info_store', 'data'), _dep_pairs(playhead[0]['inputs']))
        playhead_ids = {item['id'] for item in playhead[0]['inputs']}
        self.assertNotIn('rotation-period', playhead_ids)
        self.assertNotIn('rotation-graph', playhead_ids)

        chip = specs('rotation-live.style')
        self.assertEqual(len(chip), 1)
        self.assertIn(('match_info_store', 'data'), _dep_pairs(chip[0]['inputs']))

        matchup = specs('matchup-team.data')
        self.assertEqual(len(matchup), 1)
        self.assertIn(('match_info_store', 'data'), _dep_pairs(matchup[0]['inputs']))


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
            'kills': [
                {'side': 'away', 'stops': 3, 'start': 90.0, 'end': 140.0},
            ],
            'teams': [{'side': 'home', 'players': []}],
        }

    def test_run_click_sets_playhead(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            {'type': 'rotation-run', 'index': 0},
            False,
            [1],
            None,
            store,
            'g1',
            {'t': 0.0, 'x0': 0.0, 'x1': 120.0},
            {},
        )
        self.assertEqual(view['t'], 30.0)
        self.assertFalse(view['follow_live'])
        for key in ('period', 'x0', 'x1', 'slice_width', 'axis_rev'):
            self.assertNotIn(key, view)

    def test_kill_trigger_does_not_move_the_playhead(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            {'type': 'rotation-kill', 'index': 0},
            False,
            [],
            None,
            store,
            'g1',
            {'t': 0.0},
            {},
        )
        self.assertIs(view, no_update)

    def test_graph_click_sets_playhead_to_clicked_time_not_bar_end(self):
        store = json.dumps(self._payload())
        view = game_page.apply_rotation_view_event(
            'rotation-click-t',
            False,
            [],
            55.0,
            store,
            'g1',
            {'t': None},
            {},
        )
        self.assertEqual(view['t'], 55.0)
        self.assertNotIn('x0', view)

    def test_show_dnp_toggles_without_a_window(self):
        view = game_page.apply_rotation_view_event(
            'rotation-show-dnp', True, [], None, '{}', 'g1', {'show_dnp': False}, {},
        )
        self.assertTrue(view['show_dnp'])
        for key in ('period', 'x0', 'x1', 'slice_width', 'axis_rev'):
            self.assertNotIn(key, view)

    def test_finished_playhead_defaults_to_game_start(self):
        payload = self._payload()
        for status in ('FINISHED', 'CONFIRMED'):
            t = game_page.resolve_rotation_playhead(payload, {}, {'status': status})
            self.assertEqual(t, 0.0)

    def test_abandoned_playhead_defaults_to_game_end(self):
        t = game_page.resolve_rotation_playhead(self._payload(), {}, {'status': 'ABANDONED'})
        self.assertEqual(t, 240.0)

    def test_finished_without_periods_has_no_playhead(self):
        t = game_page.resolve_rotation_playhead({'periods': []}, {}, {'status': 'FINISHED'})
        self.assertIsNone(t)

    def test_stored_playhead_wins_over_finished_default(self):
        t = game_page.resolve_rotation_playhead(
            self._payload(), {'t': 55.0}, {'status': 'FINISHED'},
        )
        self.assertEqual(t, 55.0)

    def _live_store(self):
        payload = self._payload()
        payload['margin'] = [{'t': 80.0, 'desc': 'Lin 3PT'}]
        return json.dumps(payload)

    def _store_event(self, trigger, view, status):
        return game_page.apply_rotation_view_event(
            trigger, False, [], None, self._live_store(), 'g1', view,
            {'status': status},
        )

    def test_opening_finished_game_keeps_view(self):
        for trigger in ('match_info_store', 'rotation_store'):
            for status in ('FINISHED', 'CONFIRMED'):
                view = self._store_event(trigger, {}, status)
                self.assertIs(view, no_update)

    def test_live_store_event_marks_saw_live_and_follows_now(self):
        view = self._store_event('match_info_store', {}, 'IN_PROGRESS')
        self.assertTrue(view['saw_live'])
        self.assertEqual(view['t'], 80.0)
        self.assertFalse(view['finished_reset'])

    def test_live_store_event_keeps_parked_playhead_and_camera(self):
        view = self._store_event(
            'rotation_store',
            {'follow_live': False, 't': 20.0, 'period': '1', 'x0': 0.0, 'x1': 120.0},
            'IN_PROGRESS',
        )
        self.assertTrue(view['saw_live'])
        self.assertEqual(view['t'], 20.0)
        self.assertFalse(view['follow_live'])
        self.assertNotIn('x0', view)

    def test_live_to_finished_resets_once(self):
        parked = {
            'saw_live': True, 'follow_live': False, 't': 50.0,
            'show_dnp': True,
        }
        for status in ('FINISHED', 'CONFIRMED'):
            reset = self._store_event('match_info_store', dict(parked), status)
            self.assertIsNone(reset['t'])
            self.assertFalse(reset['follow_live'])
            self.assertTrue(reset['finished_reset'])
            self.assertTrue(reset['saw_live'])
            self.assertTrue(reset['show_dnp'])
            for key in ('period', 'x0', 'x1', 'slice_width', 'axis_rev'):
                self.assertNotIn(key, reset)
            again = self._store_event('rotation_store', dict(reset, t=70.0), status)
            self.assertIs(again, no_update)

    def test_live_to_abandoned_keeps_playhead_and_camera(self):
        view = self._store_event(
            'match_info_store',
            {'saw_live': True, 'follow_live': False, 't': 50.0, 'x0': 0.0, 'x1': 120.0},
            'ABANDONED',
        )
        self.assertIs(view, no_update)

    def test_game_id_resets_view(self):
        view = game_page.apply_rotation_view_event(
            'game_id', True, [], None, '{}', 'g2',
            {'t': 9, 'show_dnp': True},
            {},
        )
        self.assertEqual(view, game_page.DEFAULT_ROTATION_VIEW)

    def test_game_id_clears_live_and_reset_flags(self):
        view = game_page.apply_rotation_view_event(
            'game_id', False, [], None, '{}', 'g2',
            {'saw_live': True, 'finished_reset': True, 't': 50.0},
            {},
        )
        self.assertFalse(view['saw_live'])
        self.assertFalse(view['finished_reset'])
        self.assertIsNone(view['t'])

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
            't_adv_df': _split(pd.DataFrame({'Team': teams, 'Pace': [70.0, 68.0]})),
            'adv_df': _split(pd.DataFrame({
                'Team': teams, 'PPP': ['1.10', '1.00'], 'AS/TO': ['1.50', '1.00'], 'AST%': ['62.5%', '40.0%'], '3P-R': ['40.0%', '30.0%'], 'TS%': ['55.0%', '48.0%'],
            })),
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
                        'Team': teams, 'Pace': ['4.0', '4.0'],
                    })),
                    'adv_df': _split(pd.DataFrame({
                        'Team': teams, 'PPP': ['1.20', ''], 'AS/TO': ['1.20', '0.50'], 'AST%': ['50.0%', '25.0%'], '3P-R': ['30.0%', '20.0%'], 'TS%': ['50.0%', '40.0%'],
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
        self.assertLess(texts.index('SCORE'), texts.index('PACE & FOUR FACTORS'))
        self.assertLess(texts.index('PACE & FOUR FACTORS'), texts.index('ADVANCED'))
        self.assertLess(texts.index('ADVANCED'), texts.index('PAINT / 2ND CHANCE / FASTBREAK / OFF TO / BENCH'))
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

            def get_team_advanced_df(self):
                return pd.DataFrame({'Team': ['Home'], 'PPP': ['1.10'], 'AS/TO': ['1.50'], 'AST%': ['62.5%'], '3P-R': ['40.0%'], 'TS%': ['55.0%']})

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

        with patch.object(game_page, 'get_cached_report', return_value=_Report()), \
                patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'):
            payload = json.loads(game_page.update_bs_store(1, 'g1'))
        self.assertIn('88', payload['t_df'])
        self.assertIn('1.50', payload['adv_df'])
        self.assertNotIn('slice-frame', payload['t_df'])
        self.assertEqual(payload['slices']['1']['t_df'], 'slice-frame')
        self.assertEqual(payload['period_chips'][0]['value'], 'all')
        self.assertEqual(payload['game_id'], 'g1')

    def _sync(self, period, game_id, tab, columns, triggered, payload=None):
        body = self._payload() if payload is None else payload
        body = dict(body)
        body['game_id'] = body.get('game_id', 'g1')
        values = game_page.box_score_sync_values(
            json.dumps(body), period, game_id, tab, columns, triggered,
        )
        self.assertEqual(len(values), len(game_page.BS_SYNC_KEYS))
        return dict(zip(game_page.BS_SYNC_KEYS, values))

    def test_shell_stays_mounted_and_is_outside_loading(self):
        from dash import dcc
        tree = game_page.layout('g1')
        wrap = next(node for node in _nodes(tree) if getattr(node, 'id', None) == 'wrap-bs')
        self.assertFalse(any(isinstance(node, dcc.Loading) for node in _nodes(wrap)))
        ids = {getattr(node, 'id', None) for node in _nodes(wrap)}
        self.assertTrue({
            'bs-skeleton', 'bs-score-scroll', 'bs-team-scroll', 'bs-advanced-scroll',
            'bs-player-grid-0', 'bs-player-grid-1',
        } <= ids)
        detail_body = next(node for node in _nodes(tree) if getattr(node, 'id', None) == 'bs-detail-body')
        pair = detail_body.children[0]
        self.assertEqual(getattr(pair, 'cols', None), {'base': 1, 'lg': 2})
        pair_ids = {getattr(node, 'id', None) for node in _nodes(pair)}
        self.assertIn('bs-pace-scroll', pair_ids)
        self.assertIn('bs-advanced-scroll', pair_ids)
        self.assertNotIn('bs-key-scroll', pair_ids)
        key_ids = {getattr(node, 'id', None) for node in _nodes(detail_body.children[1])}
        self.assertIn('bs-key-scroll', key_ids)
        shell_texts = []
        _walk_text(detail_body, shell_texts)
        self.assertLess(shell_texts.index('PACE & FOUR FACTORS'), shell_texts.index('ADVANCED'))
        self.assertLess(
            shell_texts.index('ADVANCED'),
            shell_texts.index('PAINT / 2ND CHANCE / FASTBREAK / OFF TO / BENCH'),
        )
        self.assertEqual(
            game_page.update_pane_bs(json.dumps(self._payload()), 'tab-bs', '1'),
            (no_update, no_update),
        )

    def test_period_change_keeps_score_shell_and_swaps_slice_numbers(self):
        frames = game_page._bs_frames(dict(self._payload(), game_id='g1'), '1')
        columns = {
            'columns': {
                '0': [str(column) for column in frames['players'][0][1].columns],
                '1': [str(column) for column in frames['players'][1][1].columns],
            },
        }
        patch = self._sync('1', 'g1', 'tab-bs', columns, 'bs-period')
        self.assertIs(patch['score'], no_update)
        self.assertIs(patch['fouls'], no_update)
        self.assertIs(patch['tout'], no_update)
        self.assertIs(patch['last_update'], no_update)
        self.assertIs(patch['defs0'], no_update)
        self.assertIs(patch['columns'], no_update)
        self.assertEqual(patch['skeleton_style'], {'display': 'none'})
        self.assertEqual(patch['matrix_body_style'], {'display': 'block'})
        texts = []
        _walk_text(patch['team'], texts)
        self.assertIn('41', texts)
        self.assertNotIn('88', texts)
        self.assertEqual(patch['rows0'][0]['PTS'], 3)
        self.assertTrue(patch['rows0'][0]['_row'])

    def test_live_refresh_rewrites_score_and_other_game_shows_skeleton(self):
        patch = self._sync('all', 'g1', 'tab-bs', None, 'bs_store')
        texts = []
        _walk_text(patch['score'], texts)
        self.assertIn('22', texts)
        self.assertIsNot(patch['last_update'], no_update)
        self.assertEqual(patch['chip_data'][1]['label'], '1Q')

        stale = self._sync('all', 'g2', 'tab-bs', None, 'game_id')
        self.assertEqual(stale['skeleton_style'], {'display': 'block'})
        self.assertEqual(stale['matrix_body_style'], {'display': 'none'})
        self.assertEqual(stale['bar_style'], {'display': 'none'})
        self.assertIs(stale['score'], no_update)
        self.assertIs(stale['rows0'], no_update)

    def test_hidden_tab_does_not_patch_until_game_changes(self):
        hidden = self._sync('1', 'g1', 'tab-lineup', None, 'bs_store')
        self.assertTrue(all(value is no_update for value in hidden.values()))
        changed = self._sync('1', 'g2', 'tab-lineup', None, 'game_id')
        self.assertEqual(changed['skeleton_style'], {'display': 'block'})
        self.assertIs(changed['team'], no_update)

    def test_error_for_this_game_replaces_the_shell(self):
        values = game_page.box_score_sync_values(
            json.dumps({'_ui': 'error', 'message': 'Failed to load this view. Please try again later.', 'game_id': 'g1'}),
            'all', 'g1', 'tab-bs', None, 'bs_store',
        )
        patch = dict(zip(game_page.BS_SYNC_KEYS, values))
        self.assertEqual(patch['status_style'], {'display': 'block'})
        self.assertEqual(patch['skeleton_style'], {'display': 'none'})
        self.assertEqual(patch['bar_style'], {'display': 'none'})
        self.assertIn('Failed to load this view. Please try again later.', str(patch['status_children']))


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


class TabsDmcContractTests(unittest.TestCase):
    def test_game_tab_order_is_lineup_before_pbp(self):
        import dash_mantine_components as dmc
        from tests.test_dmc_ui import find_type
        tree = game_page.layout('g1')
        values = [node.value for node in find_type(tree, dmc.TabsTab)]
        self.assertEqual(
            values,
            ['tab-bs', 'tab-rotation', 'tab-shot-chart', 'tab-lineup', 'tab-matchups', 'tab-pbp', 'tab-report'],
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

    def test_narrow_game_tabs_use_a_three_column_grid(self):
        import os
        css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'app.css')
        with open(css_path, 'r') as handle:
            css = handle.read()
        narrow = css.split('@media (max-width: 767px)', 1)[1].split('@media', 1)[0]
        self.assertIn('grid-template-columns: repeat(3, minmax(0, 1fr))', narrow)
        self.assertIn('padding: 8px 6px', narrow)
        self.assertIn('font-size: 13px', narrow)
        self.assertIn('margin-inline-end: 4px', narrow)
        self.assertIn('border-radius: 10px', narrow)
        phone = css.split('@media (max-width: 768px)', 1)[1].split('@media', 1)[0]
        self.assertIn('flex-wrap: nowrap', phone)
        self.assertIn('border-radius: 10px', phone)
        self.assertIn('border: 1px solid var(--border)', phone)
        self.assertIn('box-shadow: 0 8px 30px rgba(15, 23, 42, 0.15)', phone)
        self.assertIn('margin: 0 !important', phone)
        self.assertNotIn('border-radius: 0', phone)
        self.assertIn('.mantine-Select-input', phone)
        self.assertIn('.select-sizer-probe', phone)
        self.assertIn('font-size: max(1rem, 1em)', phone)


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
        result = game_page.update_shot_chart('{}', 'all', 'all', 'all', 'tab-bs', '{}')
        self.assertTrue(all(item is no_update for item in result))
        self.assertEqual(
            game_page.update_shot_chart_period_options(_shot_frame(), 'tab-bs'),
            (no_update, no_update),
        )
        info = json.dumps({'away_team_id': 'away', 'home_team_id': 'home'})
        self.assertEqual(
            game_page.update_shot_chart_players(_shot_frame(), 'tab-lineup', info),
            (no_update, no_update),
        )
        data, style = game_page.update_shot_chart_period_options(_shot_frame(), 'tab-shot-chart')
        self.assertEqual([item['label'] for item in data], ['All', '1Q', '2Q', '1H'])
        self.assertEqual(style, {'display': 'flex'})
        away, home = game_page.update_shot_chart_players(_shot_frame(), 'tab-shot-chart', info)
        self.assertEqual(away[1]['label'], '#9 Chen')
        self.assertEqual(home[1]['label'], '#7 Lin')


class GridDmcContractTests(unittest.TestCase):
    def test_game_page_uses_dmc_simple_grid_without_dbc_row_col(self):
        import os
        root = os.path.dirname(os.path.dirname(__file__))
        code = '\n'.join(
            open(os.path.join(root, *parts), 'r').read()
            for parts in (('pages', 'game.py'), ('ui', 'game_tabs', 'box_score.py'))
        )
        self.assertIn('dmc.SimpleGrid', code)
        self.assertIn('"lg": 3', code)
        self.assertIn('"lg": 2', code)
        self.assertNotIn('alwaysShowHorizontalScroll', code)
        self.assertNotIn('"sm": 3', code)
        self.assertNotIn('dbc.Row', code)
        self.assertNotIn('dbc.Col', code)


class ScoreboardTests(unittest.TestCase):
    def _frame(self, rows):
        return pd.DataFrame(rows)

    def test_clock_is_the_last_event_and_later_scoreless_rows_are_ignored(self):
        from synergy_inbounder.live_clock import scoreboard_from_pbp_frame

        frame = self._frame([
            {'periodId': 1, 'clock': 'PT10M00S', 'scores': '{"home": 0, "away": 0}'},
            {'periodId': 2, 'clock': 'PT03M41S', 'scores': None},
            {'periodId': 2, 'clock': None, 'scores': '{"home": 50, "away": 40}'},
        ])
        label, home, away = scoreboard_from_pbp_frame(frame, 'home', 'away')
        self.assertEqual(label, '2Q 3:41')
        self.assertEqual((home, away), ('0', '0'))

    def test_missing_score_on_the_clock_event_walks_backward(self):
        from synergy_inbounder.live_clock import scoreboard_from_pbp_frame

        frame = self._frame([
            {'periodId': 1, 'clock': 'PT08M00S', 'scores': '{"home": 12, "away": 7}'},
            {'periodId': 1, 'clock': 'PT07M00S', 'scores': '{"home": 12}'},
            {'periodId': 1, 'clock': 'PT06M00S', 'scores': None},
        ])
        label, home, away = scoreboard_from_pbp_frame(frame, 'home', 'away')
        self.assertEqual(label, '1Q 6:00')
        self.assertEqual((home, away), ('12', '7'))

    def test_no_drawable_clock_returns_nothing(self):
        from synergy_inbounder.live_clock import clock_from_pbp_frame, scoreboard_from_pbp_frame

        frame = self._frame([
            {'periodId': 1, 'clock': None, 'scores': '{"home": 2, "away": 1}'},
        ])
        self.assertEqual(scoreboard_from_pbp_frame(frame, 'home', 'away'), (None, None, None))
        self.assertIsNone(clock_from_pbp_frame(frame))

    def test_a_score_of_zero_stays_zero(self):
        from synergy_inbounder.live_clock import scoreboard_from_pbp_frame

        frame = self._frame([
            {'periodId': 1, 'clock': 'PT00M00S', 'scores': {'home': 0, 'away': 0.0}},
        ])
        self.assertEqual(
            scoreboard_from_pbp_frame(frame, 'home', 'away'),
            ('1Q 0:00', '0', '0'),
        )


class LivePaintTests(unittest.TestCase):
    def _info(self, **extra):
        payload = {
            'status': 'IN_PROGRESS',
            'time': '19:00',
            'date': '2026-01-01',
            'venue': 'Arena',
            'home_team': 'Home',
            'away_team': 'Away',
            'home_team_id': 'home',
            'away_team_id': 'away',
            'home_score': '40',
            'away_score': '38',
        }
        payload.update(extra)
        return payload

    def test_in_progress_banner_reads_the_play_by_play_scoreboard(self):
        report = Mock()
        report.playbyplay_df = pd.DataFrame([
            {'periodId': 2, 'clock': 'PT03M41S', 'scores': '{"home": 10, "away": 8}'},
        ])
        with patch.object(game_page, '_info_dict', return_value=self._info()), \
                patch.object(game_page, 'get_cached_report', return_value=report):
            raw = game_page.update_match_info_store(1, 'g1', 'plg', None)
        data = json.loads(raw)
        self.assertTrue(data['banner_ready'])
        self.assertEqual(data['banner_clock'], '2Q 3:41')
        self.assertEqual(data['banner_home_score'], '10')
        self.assertEqual(data['banner_away_score'], '8')
        self.assertEqual(data['home_score'], '40')

    def test_same_generation_does_not_rewrite_the_banner(self):
        previous = json.dumps(self._info(banner_generation=4, banner_ready=True))
        with patch.object(game_page, '_info_dict', return_value=self._info()), \
                patch.object(game_page, 'get_cached_report', return_value=Mock()), \
                patch.object(game_page, 'report_generation', return_value=4):
            result = game_page.update_match_info_store(2, 'g1', 'plg', previous)
        self.assertIs(result, no_update)

    def test_a_stale_banner_does_not_overwrite(self):
        report = Mock()
        report.playbyplay_df = pd.DataFrame([
            {'periodId': 1, 'clock': 'PT01M00S', 'scores': '{"home": 1, "away": 0}'},
        ])
        generations = iter([1, 2])
        with patch.object(game_page, '_info_dict', return_value=self._info()), \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, 'report_generation', side_effect=lambda *_a, **_k: next(generations)):
            result = game_page.update_match_info_store(2, 'g1', 'plg', None)
        self.assertIs(result, no_update)

    def test_pre_tip_does_not_open_the_report(self):
        with patch.object(game_page, '_info_dict', return_value=self._info(status='PENDING')), \
                patch.object(game_page, 'get_cached_report') as cached:
            raw = game_page.update_match_info_store(1, 'g1', 'plg', None)
        cached.assert_not_called()
        data = json.loads(raw)
        self.assertEqual(data['status'], 'PENDING')
        self.assertNotIn('banner_ready', data)

    def test_pre_tip_repeat_does_not_rewrite_the_store(self):
        info = self._info(status='WARM_UP')
        with patch.object(game_page, '_info_dict', return_value=info), \
                patch.object(game_page, 'get_cached_report') as cached:
            first = game_page.update_match_info_store(1, 'g1', 'plg', None)
            again = game_page.update_match_info_store(2, 'g1', 'plg', first)
        cached.assert_not_called()
        self.assertEqual(json.loads(first)['status'], 'WARM_UP')
        self.assertIs(again, no_update)

    def test_play_by_play_failure_keeps_the_banner(self):
        from synergy_inbounder.communicator import SynergyAuthError

        previous = json.dumps(self._info(banner_ready=True, banner_clock='1Q 5:00'))
        with patch.object(game_page, '_info_dict', return_value=self._info()), \
                patch.object(game_page, 'get_cached_report', side_effect=RuntimeError('down')):
            kept = game_page.update_match_info_store(1, 'g1', 'plg', previous)
        self.assertEqual(kept, previous)
        with patch.object(game_page, '_info_dict', return_value=self._info()), \
                patch.object(game_page, 'get_cached_report', side_effect=SynergyAuthError('401')):
            auth = game_page.update_match_info_store(1, 'g1', 'plg', previous)
        self.assertEqual(json.loads(auth)['_ui'], 'error')

    def test_stats_failure_keeps_the_whole_box_and_still_updates_lineup(self):
        report = Mock()
        report.stats_failed = True
        report.get_all_lineup_stats_json_dict.return_value = {'size': 5}
        previous = json.dumps({'qt_pts_df': 'old-box', 't_df': 'old-teams'})
        with patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, '_box_payload') as boxed:
            kept = json.loads(game_page.update_bs_store(1, 'g1', 'plg', previous))
            lineup = json.loads(game_page.update_lineup_store(1, 'g1', 'plg'))
        boxed.assert_not_called()
        self.assertEqual(kept['qt_pts_df'], 'old-box')
        self.assertEqual(kept['t_df'], 'old-teams')
        self.assertTrue(kept['stats_delayed'])
        self.assertEqual(lineup, {'size': 5})

    def test_stats_failure_with_no_box_is_the_red_alert(self):
        report = Mock(stats_failed=True)
        with patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', return_value=report):
            raw = game_page.update_bs_store(1, 'g1', 'plg', None)
        self.assertEqual(json.loads(raw)['_ui'], 'error')

    def test_a_stale_stats_failure_does_not_rewrite_the_box(self):
        report = Mock(stats_failed=True)
        previous = json.dumps({'qt_pts_df': 'newer-box', 'generation': 2})
        generations = iter([1, 2])
        with patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, 'report_generation', side_effect=lambda *_a, **_k: next(generations)):
            result = game_page.update_bs_store(1, 'g1', 'plg', previous)
        self.assertIs(result, no_update)

    def test_a_stale_play_by_play_does_not_overwrite(self):
        report = Mock()
        report.get_play_by_play_df.return_value = pd.DataFrame({'eventType': ['shot']})
        generations = iter([1, 1, 2])
        with patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, 'report_generation', side_effect=lambda *_a, **_k: next(generations)):
            result = game_page.update_pbp_store(1, 'g1', 'plg')
        self.assertIs(result, no_update)

    def test_each_page_remembers_the_generation_it_painted(self):
        report = Mock()
        report.get_play_by_play_df.return_value = pd.DataFrame({'eventType': ['shot']})
        with patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, 'report_generation', return_value=3):
            first = game_page.update_pbp_store(1, 'g1', 'plg')
            again = game_page.update_pbp_store(2, 'g1', 'plg', first)
            fresh = game_page.update_pbp_store(3, 'g1', 'plg', None)
        painted = json.loads(first)
        self.assertEqual(painted['generation'], 3)
        self.assertEqual(painted['game_id'], 'g1')
        self.assertIn('shot', painted['frame'])
        self.assertIs(again, no_update)
        self.assertEqual(json.loads(fresh)['generation'], 3)

    def test_a_budget_wait_keeps_the_fixture_header_and_a_skeleton(self):
        from synergy_inbounder.communicator import LiveBudgetWait

        info = self._info()
        previous = json.dumps(self._info(banner_ready=True, banner_clock='1Q 5:00'))
        previous_pbp = json.dumps({'columns': ['eventType'], 'data': [['shot']]})
        with patch.object(game_page, '_info_dict', return_value=info), \
                patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', side_effect=LiveBudgetWait('wait')):
            banner = json.loads(game_page.update_match_info_store(1, 'g1', 'plg', None))
            waiting = json.loads(game_page.update_pbp_store(1, 'g1', 'plg', None))
            kept = game_page.update_match_info_store(2, 'g1', 'plg', previous)
            kept_pbp = game_page.update_pbp_store(2, 'g1', 'plg', previous_pbp)
        self.assertNotIn('banner_ready', banner)
        self.assertEqual(banner['home_team'], 'Home')
        self.assertEqual(banner['time'], info['time'])
        self.assertEqual(waiting['_ui'], 'waiting')
        self.assertEqual(kept, previous)
        self.assertEqual(kept_pbp, previous_pbp)

    def test_a_build_failure_without_a_snapshot_alerts_the_tabs(self):
        info = self._info()
        with patch.object(game_page, '_info_dict', return_value=info), \
                patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report', side_effect=RuntimeError('down')):
            banner = json.loads(game_page.update_match_info_store(1, 'g1', 'plg', None))
            alert = json.loads(game_page.update_pbp_store(1, 'g1', 'plg', None))
        self.assertNotIn('banner_ready', banner)
        self.assertEqual(banner['home_team'], 'Home')
        self.assertEqual(banner['time'], info['time'])
        self.assertEqual(alert['_ui'], 'error')

    def test_rotation_without_team_ids_does_not_open_the_report(self):
        with patch.object(game_page, '_info_dict', return_value={}), \
                patch.object(game_page, 'get_cached_report') as cached:
            result = game_page.update_rotation_store(1, 'g1', 'plg')
        cached.assert_not_called()
        self.assertIs(result, no_update)

    def test_last_update_without_a_snapshot_is_a_dash(self):
        text = str(game_page._last_update_span('missing-game', 'org-missing'))
        self.assertIn('Last Update: —', text)

    def test_finish_waits_while_the_fixture_is_live(self):
        with patch.object(game_page, '_fixture_status', return_value='IN_PROGRESS'), \
                patch.object(game_page, 'get_cached_report') as cached:
            outputs = game_page.publish_finished_snapshot(1, 'g1', 'plg')
        cached.assert_not_called()
        self.assertTrue(all(item is no_update for item in outputs))

    def test_finish_success_writes_every_store_and_stops_the_interval(self):
        report = Mock()
        report.get_play_by_play_df.return_value = pd.DataFrame({'eventType': ['shot']})
        report.get_all_lineup_stats_json_dict.return_value = {'size': 5}
        report.get_matchup_payload.return_value = {'pairs': []}
        report.get_rotation_payload.return_value = {'periods': []}
        info = self._info(
            status='FINISHED',
            home_score='88',
            away_score='79',
            time='19:00',
        )
        with patch.object(game_page, '_fixture_status', return_value='FINISHED'), \
                patch.object(game_page, 'get_cached_report', return_value=report), \
                patch.object(game_page, '_info_dict', return_value=info), \
                patch.object(game_page, '_box_payload', return_value='{"qt_pts_df":"official"}'), \
                patch.object(game_page, 'warmup_game_report'), \
                patch.object(game_page, '_triggered_id', return_value='interval-component'):
            outputs = game_page.publish_finished_snapshot(3, 'g1', 'plg')
        self.assertIn('official', outputs[0])
        self.assertIn('shot', outputs[1])
        self.assertIn('"size": 5', outputs[2])
        self.assertIn('pairs', outputs[3])
        self.assertIn('periods', outputs[4])
        posted = json.loads(outputs[5])
        self.assertEqual(posted['home_score'], '88')
        self.assertEqual(posted['status'], 'FINISHED')
        self.assertNotIn('banner_ready', posted)
        self.assertFalse(game_page.set_interval_disabled(outputs[5]))

    def test_finish_failure_keeps_a_snapshot_and_errors_on_the_first_load(self):
        from synergy_inbounder.communicator import SynergyAuthError

        with patch.object(game_page, '_fixture_status', return_value='FINISHED'), \
                patch.object(game_page, 'get_cached_report', side_effect=RuntimeError('down')), \
                patch.object(game_page, 'report_generation', return_value=2):
            held = game_page.publish_finished_snapshot(1, 'g1', 'plg')
        self.assertTrue(all(item is no_update for item in held))

        with patch.object(game_page, '_fixture_status', return_value='FINISHED'), \
                patch.object(game_page, 'get_cached_report', side_effect=RuntimeError('down')), \
                patch.object(game_page, 'report_generation', return_value=0):
            fresh = game_page.publish_finished_snapshot(0, 'g1', 'plg')
        self.assertTrue(all(json.loads(item)['_ui'] == 'error' for item in fresh))

        with patch.object(game_page, '_fixture_status', return_value='FINISHED'), \
                patch.object(game_page, 'get_cached_report', side_effect=SynergyAuthError('401')), \
                patch.object(game_page, 'report_generation', return_value=2):
            auth = game_page.publish_finished_snapshot(1, 'g1', 'plg')
        self.assertTrue(all(json.loads(item)['_ui'] == 'error' for item in auth))


def _walk(node):
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    if node is None or isinstance(node, (str, int, float, bool)):
        return
    yield node
    children = getattr(node, 'children', None)
    if children is not None:
        yield from _walk(children)


class DuplicateOutputKeyTests(unittest.TestCase):
    def test_renderer_output_keys_are_unique(self):
        from collections import Counter

        from dash._callback import GLOBAL_CALLBACK_LIST
        from dash._utils import split_callback_id

        keys = []
        for spec in GLOBAL_CALLBACK_LIST:
            parts = split_callback_id(spec['output'])
            items = parts if isinstance(parts, list) else [parts]
            for item in items:
                keys.append(f"{item['id']}.{item['property']}")
        duplicates = {key: count for key, count in Counter(keys).items() if count > 1}
        self.assertEqual(duplicates, {})

    def test_one_reader_writes_the_game_stores(self):
        from dash._callback import GLOBAL_CALLBACK_LIST

        readers = [
            item for item in GLOBAL_CALLBACK_LIST
            if 'rotation_store.data' in str(item.get('output'))
            and 'interval-component.interval' in str(item.get('output'))
        ]
        self.assertEqual(len(readers), 1)
        self.assertEqual(
            [(item['id'], item['property']) for item in readers[0]['inputs']],
            [
                ('interval-component', 'n_intervals'),
                ('game_id', 'children'),
                ('game_league', 'children'),
            ],
        )
        state = {(item['id'], item['property']) for item in readers[0]['state']}
        self.assertIn(('bs_store', 'data'), state)
        self.assertIn(('match_info_store', 'data'), state)
        self.assertIn(('interval-component', 'interval'), state)
        self.assertNotIn('finished-snapshot-sentinel', {item['id'] for item in readers[0]['inputs']})

    def test_game_layout_has_no_sentinel_store(self):
        matches = [
            node for node in _walk(game_page.layout('g1', 'plg'))
            if getattr(node, 'id', None) == 'finished-snapshot-sentinel'
        ]
        self.assertEqual(matches, [])


