# -*- coding: utf-8 -*-
import base64
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import dash_mantine_components as dmc
from dash import no_update
from dash.exceptions import PreventUpdate

import app  # noqa: F401
from pages import team_stats as team_stats_page
from ui_kit import ERROR_GAME


def _callbacks(fragment):
    from dash._callback import GLOBAL_CALLBACK_LIST
    return [item for item in GLOBAL_CALLBACK_LIST if fragment in item['output']]


def _pairs(deps):
    return [(item['id'], item['property']) for item in deps]


def _names(node, found=None):
    found = set() if found is None else found
    found.add(type(node).__name__)
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            _names(child, found)
    elif children is not None and not isinstance(children, (str, int, float, dict)):
        _names(children, found)
    return found


def _walk(node, found=None):
    found = [] if found is None else found
    found.append(node)
    pending = []
    spinner = getattr(node, 'custom_spinner', None)
    if spinner is not None:
        pending.append(spinner)
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        pending.extend(children)
    elif children is not None and not isinstance(children, (str, int, float, dict)):
        pending.append(children)
    for child in pending:
        _walk(child, found)
    return found


class TeamStatsChromeTests(unittest.TestCase):
    def test_rotation_pane_is_not_wrapped_in_loading(self):
        from dash import dcc

        layout = team_stats_page.layout()
        self.assertFalse(any(isinstance(node, dcc.Loading) for node in _walk(layout)))
        pane = next(node for node in _walk(layout) if getattr(node, 'id', None) == 'ts-rotation')
        self.assertIsNone(pane.children)

    def test_chart_skeleton_is_written_on_intent_and_slice_changes(self):
        text = Path('pages/team_stats.py').read_text(encoding='utf-8')
        self.assertIn("Output('ts-rotation', 'children', allow_duplicate=True)", text)
        self.assertIn('var cards = __LOADING_BODY__;', text)
        self.assertIn('loading_skeleton(\'chart\')', text)
        self.assertIn('sameLeague ? seasonValue : null', text)
        listed = _callbacks('ts-rotation.children')
        clientside = [item for item in listed if item.get('clientside_function')]
        self.assertGreaterEqual(len(clientside), 2)

    def test_select_menus_use_the_shared_plan(self):
        text = Path('assets/select_menu.js').read_text(encoding='utf-8')
        self.assertFalse(Path('assets/shot_chart_menu.js').exists())
        for field in (
            '#shot-chart-player-away',
            '#shot-chart-player-home',
            '#home-team',
            '#home-season',
            '#ts-team',
            '#ts-opponent',
            '#ts-stadium',
            '#ts-season',
        ):
            self.assertIn(field, text)
        self.assertIn('splashboardSelectMenuPlan', text)
        self.assertNotIn('splashboardShotMenuPlan', text)


class TeamStatsCallbackTests(unittest.TestCase):
    def test_skeleton_follows_intent_and_scope_only(self):
        listed = _callbacks('ts-body.children')
        clientside = [item for item in listed if item.get('clientside_function')]
        server = [item for item in listed if not item.get('clientside_function')]
        self.assertEqual(len(clientside), 3)
        self.assertEqual(len(server), 4)
        intent_body = next(
            item for item in clientside
            if _pairs(item['inputs']) == [('ts-intent', 'data')]
        )
        self.assertTrue(intent_body['prevent_initial_call'])
        self.assertNotIn('ts-league', {item['id'] for item in intent_body['inputs']})
        self.assertNotIn('ts-game-type', {item['id'] for item in intent_body['inputs']})
        self.assertNotIn('ts-period', {item['id'] for item in intent_body['inputs']})
        slice_body = next(
            item for item in clientside
            if ('ts-team', 'value') in _pairs(item['inputs'])
        )
        self.assertIn(('ts-slice', 'data'), _pairs(slice_body['state']))
        self.assertTrue(slice_body['prevent_initial_call'])
        period_body = next(
            item for item in clientside
            if _pairs(item['inputs']) == [('ts-period', 'value')]
        )
        self.assertEqual(_pairs(period_body['state']), [('ts-slice', 'data')])
        self.assertTrue(period_body['prevent_initial_call'])
        source = Path('pages/team_stats.py').read_text(encoding='utf-8')
        self.assertIn('current.period', source)
        store = next(node for node in _walk(team_stats_page.layout()) if getattr(node, 'id', None) == 'ts-slice')
        self.assertEqual(store.data.get('period'), 'all')

        bridge = _callbacks('ts-intent.data')
        self.assertEqual(len(bridge), 1)
        self.assertTrue(bridge[0].get('clientside_function'))
        self.assertEqual(
            _pairs(bridge[0]['inputs']),
            [
                ('ts-league', 'value'),
                ('ts-season', 'value'),
                ('ts-game-type', 'value'),
            ],
        )
        self.assertEqual(_pairs(bridge[0]['state']), [('ts-applied', 'data')])
        self.assertTrue(bridge[0]['prevent_initial_call'])

        render = [item for item in server if 'ts-job.data' in item['output']]
        drawer = [
            item for item in server
            if _pairs(item['inputs']) == [('ts-interval', 'n_intervals')]
        ]
        sort_cb = [
            item for item in server
            if any('ts-sort-th' in str(dep.get('id')) for dep in item['inputs'])
        ]
        self.assertEqual(len(render), 1)
        self.assertEqual(len(drawer), 1)
        self.assertEqual(len(sort_cb), 1)
        download = [
            item for item in server
            if item not in render and item not in drawer and item not in sort_cb
        ]
        self.assertEqual(len(download), 1)
        # Dash stores initial_duplicate as "do not skip the first call".
        self.assertFalse(drawer[0]['prevent_initial_call'])
        self.assertIn('ts-seen.data', drawer[0]['output'])
        self.assertNotIn('ts-job.data', drawer[0]['output'])
        self.assertIn(('ts-seen', 'data'), _pairs(drawer[0]['state']))
        self.assertEqual(
            _pairs(render[0]['inputs']),
            [
                ('ts-intent', 'data'),
                ('ts-period', 'value'),
                ('ts-opponent', 'value'),
                ('ts-stadium', 'value'),
                ('ts-site', 'value'),
                ('ts-team', 'value'),
            ],
        )
        self.assertEqual(
            _pairs(render[0]['state']),
            [
                ('ts-league', 'value'),
                ('ts-season', 'value'),
                ('ts-game-type', 'value'),
                ('ts-sort', 'data'),
            ],
        )
        self.assertNotIn('ts-opponent', {item['id'] for item in intent_body['inputs']})
        self.assertNotIn('ts-stadium', {item['id'] for item in intent_body['inputs']})
        self.assertNotIn('ts-site', {item['id'] for item in intent_body['inputs']})
        self.assertIn('ts-applied.data', render[0]['output'])
        self.assertFalse(render[0]['prevent_initial_call'])
        self.assertEqual(_pairs(download[0]['inputs']), [('ts-job', 'data')])
        self.assertIn(('ts-intent', 'data'), _pairs(download[0]['state']))
        self.assertIn(('ts-period', 'value'), _pairs(download[0]['state']))
        self.assertIn(('ts-opponent', 'value'), _pairs(download[0]['state']))
        self.assertIn(('ts-stadium', 'value'), _pairs(download[0]['state']))
        self.assertIn(('ts-site', 'value'), _pairs(download[0]['state']))
        self.assertIn(('ts-team', 'value'), _pairs(download[0]['state']))
        self.assertIn('ts-applied.data', download[0]['output'])
        self.assertNotIn('ts-job.data', download[0]['output'])
        self.assertTrue(download[0]['prevent_initial_call'])
        self.assertIn('ts-period-wrap.style', render[0]['output'])
        self.assertNotIn('ts-period-bar.style', render[0]['output'])
        self.assertNotIn('ts-show-opp', {item['id'] for item in render[0]['inputs']})
        self.assertNotIn('ts-show-opp', {item['id'] for item in download[0]['state']})

        show = _callbacks('ts-body.className')
        self.assertEqual(len(show), 1)
        self.assertTrue(show[0].get('clientside_function'))
        self.assertEqual(_pairs(show[0]['inputs']), [('ts-show-opp', 'checked')])
        self.assertNotIn('ts-league', {item['id'] for item in show[0]['inputs']})
        self.assertNotIn('ts-period', {item['id'] for item in show[0]['inputs']})


def _payload(season_id='s', game_type='REGULAR', period='all'):
    return {
        'ok': True,
        'empty': True,
        'message': 'No games in this view.',
        'next_step': 'Switch Game Type.',
        'stamp': 'Last Update: 2026-10-24',
        'season_id': season_id,
        'seasons': [{'label': '2025-26', 'value': season_id}],
        'game_type': game_type,
        'game_types': [{'label': 'Regular', 'value': 'REGULAR'}, {'label': 'Playoff', 'value': 'PLAYOFF'}],
        'game_type_visible': True,
        'period': period,
        'period_chips': [{'label': 'All', 'value': 'all'}],
        'period_visible': True,
        'cards': None,
    }


class TeamStatsRenderTests(unittest.TestCase):
    def test_scope_stamps_applied_with_the_rendered_selects(self):
        intent = {
            'league': 'EASL',
            'season': 'plg-season',
            'game_type': None,
            'skeleton': True,
            'nonce': 3,
        }
        payload = _payload('easl-season', 'REGULAR')
        with patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch:
            result = team_stats_page.render_team_stats(
                intent, '1', 'b', 'v1', 'home', 'all', 'EASL', 'plg-season', None,
            )
        self.assertEqual(fetch.call_args.kwargs['reason'], 'scope')
        self.assertIsNone(fetch.call_args.kwargs['game_type'])
        self.assertEqual(fetch.call_args.kwargs['period'], 'all')
        self.assertEqual(fetch.call_args.kwargs['opponent'], 'all')
        self.assertEqual(fetch.call_args.kwargs['stadium'], 'all')
        self.assertEqual(fetch.call_args.kwargs['site'], 'all')
        self.assertEqual(fetch.call_args.kwargs['team'], 'all')
        self.assertEqual(result[3], 'easl-season')
        self.assertEqual(result[5], 'REGULAR')
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[10], {
            'league': 'EASL',
            'season': 'easl-season',
            'game_type': 'REGULAR',
            'ok': True,
        })
        self.assertEqual(result[12], 'all')
        self.assertEqual(result[15], 'all')
        self.assertEqual(result[17], 'all')
        self.assertIs(result[26], no_update)

    def test_intent_click_ignores_stale_control_state(self):
        intent = {
            'league': 'EASL',
            'season': 'easl-season',
            'game_type': None,
            'skeleton': True,
            'nonce': 4,
        }
        payload = _payload('easl-season', 'REGULAR')
        chrome = {'ok': True, 'needs_cards': False, 'season_id': 'easl-season'}
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-intent'), \
                patch.object(team_stats_page, 'schedule_chrome', return_value=chrome) as listed, \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch:
            result = team_stats_page.render_team_stats(
                intent, '1', 'b', 'v1', 'home', 'kept', 'PLG', 'plg-season', 'PLAYOFF',
            )
        self.assertTrue(listed.call_args.kwargs['reset'])
        self.assertEqual(listed.call_args.args[0], 'EASL')
        self.assertEqual(fetch.call_args.args[0], 'EASL')
        self.assertEqual(fetch.call_args.kwargs['season_id'], 'easl-season')
        self.assertIsNone(fetch.call_args.kwargs['game_type'])
        self.assertEqual(fetch.call_args.kwargs['reason'], 'scope')
        self.assertEqual(fetch.call_args.kwargs['team'], 'all')
        self.assertEqual(result[10], {
            'league': 'EASL',
            'season': 'easl-season',
            'game_type': 'REGULAR',
            'ok': True,
        })

    def test_intent_game_type_ignores_stale_control_state(self):
        intent = {
            'league': 'PLG',
            'season': 's',
            'game_type': 'PLAYOFF',
            'skeleton': False,
            'nonce': 8,
        }
        payload = _payload('s', 'PLAYOFF')
        chrome = {'ok': True, 'needs_cards': False, 'season_id': 's', 'game_type': 'PLAYOFF'}
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-intent'), \
                patch.object(team_stats_page, 'schedule_chrome', return_value=chrome), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, '_view', return_value='cards'):
            result = team_stats_page.render_team_stats(
                intent, '2', 'all', 'all', 'away', 'club', 'EASL', 'other', 'REGULAR',
            )
        self.assertEqual(fetch.call_args.args[0], 'PLG')
        self.assertEqual(fetch.call_args.kwargs['season_id'], 's')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'PLAYOFF')
        self.assertEqual(fetch.call_args.kwargs['team'], 'club')
        self.assertEqual(result[10]['league'], 'PLG')
        self.assertEqual(result[10]['season'], 's')
        self.assertEqual(result[10]['game_type'], 'PLAYOFF')

    def test_cached_game_type_swaps_cards_without_a_job(self):
        intent = {
            'league': 'PLG',
            'season': 's',
            'game_type': 'PLAYOFF',
            'skeleton': False,
            'nonce': 8,
        }
        payload = _payload('s', 'PLAYOFF')
        payload['site'] = 'away'
        chrome = {'ok': True, 'needs_cards': False, 'season_id': 's', 'game_type': 'PLAYOFF'}
        with patch.object(team_stats_page, 'schedule_chrome', return_value=chrome), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, '_view', return_value='cards'):
            result = team_stats_page.render_team_stats(
                intent, '2', 'all', 'all', 'away', 'all', 'PLG', 's', 'PLAYOFF',
            )
        self.assertEqual(result[0], 'cards')
        self.assertEqual(fetch.call_args.kwargs['reason'], 'type')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'PLAYOFF')
        self.assertIs(result[5], no_update)
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[10]['game_type'], 'PLAYOFF')
        self.assertEqual(fetch.call_args.kwargs['site'], 'away')
        self.assertIs(result[17], no_update)
        self.assertIs(result[26], no_update)

    def test_missing_play_by_play_paints_menus_and_arms_the_card_job(self):
        intent = {
            'league': 'PLG',
            'season': 's',
            'game_type': 'PLAYOFF',
            'skeleton': False,
            'nonce': 9,
        }
        chrome = {
            'ok': True,
            'needs_cards': True,
            'season_id': 's',
            'seasons': [{'label': '2025-26', 'value': 's'}],
            'game_type': 'PLAYOFF',
            'game_types': [{'label': 'Playoff', 'value': 'PLAYOFF'}],
            'game_type_visible': True,
            'period': 'all',
            'period_chips': [{'label': 'All', 'value': 'all'}],
            'period_visible': False,
            'team': 'aces',
            'team_options': [
                {'label': 'All Teams', 'value': 'all'},
                {'label': 'Aces', 'value': 'aces'},
            ],
            'team_visible': True,
            'opponent': 'all',
            'opponent_options': [{'label': 'vs All Teams', 'value': 'all'}],
            'opponent_width_labels': ['vs All Teams', 'vs Aces'],
            'opponent_visible': False,
            'stadium': 'all',
            'stadium_options': [{'label': 'All Stadiums', 'value': 'all'}],
            'stadium_visible': False,
            'site': 'home',
            'empty': True,
            'cards': None,
            'stamp': 'Last Update: old',
        }
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-intent'), \
                patch.object(team_stats_page, 'schedule_chrome', return_value=chrome), \
                patch.object(team_stats_page, 'team_stats_payload') as fetch:
            result = team_stats_page.render_team_stats(
                intent, '2', 'b', 'v1', 'home', 'aces', 'PLG', 's', 'REGULAR',
            )
        fetch.assert_not_called()
        self.assertIn('Skeleton', _names(result[0]))
        self.assertNotIn('Table', _names(result[0]))
        self.assertIs(result[1], no_update)
        self.assertEqual(result[5], 'PLAYOFF')
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[9], {'display': 'none'})
        self.assertEqual(result[23], [{'label': 'All', 'value': 'all'}])
        self.assertEqual(result[24], 'all')
        self.assertEqual(result[25], {'display': 'none'})
        self.assertEqual(result[10]['league'], 'PLG')
        self.assertEqual(result[10]['season'], 's')
        self.assertEqual(result[10]['game_type'], 'PLAYOFF')
        self.assertTrue(result[10]['ok'])
        self.assertIs(result[19], no_update)
        self.assertEqual(result[26]['phase'], 'cards')
        self.assertEqual(result[26]['game_type'], 'PLAYOFF')
        self.assertEqual(result[26]['team'], 'aces')
        self.assertEqual(result[26]['nonce'], 9)

    def test_period_chip_keeps_applied_and_does_not_arm_a_job(self):
        payload = _payload('s', 'REGULAR', '1')
        payload['period_chips'] = [
            {'label': 'All', 'value': 'all'},
            {'label': '1Q', 'value': '1'},
        ]
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-period'), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch:
            result = team_stats_page.render_team_stats(
                {'skeleton': True, 'nonce': 1, 'game_type': None},
                '1',
                'all',
                'all',
                'all',
                'all',
                'PLG',
                's',
                'REGULAR',
            )
        self.assertEqual(fetch.call_args.kwargs['reason'], 'chip')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'REGULAR')
        self.assertEqual(fetch.call_args.kwargs['period'], '1')
        self.assertIs(result[8], no_update)
        self.assertIs(result[10], no_update)
        self.assertEqual(result[23], payload['period_chips'])
        self.assertIs(result[24], no_update)
        self.assertIsNone(result[25])
        self.assertIs(result[26], no_update)

    def test_download_paints_the_armed_type_and_drops_a_stale_job(self):
        job = {
            'league': 'PLG',
            'season': 's',
            'game_type': 'PLAYOFF',
            'skeleton': False,
            'nonce': 9,
        }
        payload = _payload('s', 'PLAYOFF')
        with patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, '_view', return_value='cards'):
            result = team_stats_page.render_team_stats_download(
                job, dict(job), 'PLG', 's', 'REGULAR', '2',
            )
        self.assertEqual(len(result), 26)
        self.assertEqual(result[0], 'cards')
        self.assertEqual(fetch.call_args.kwargs['reason'], 'type')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'PLAYOFF')
        self.assertEqual(result[5], 'PLAYOFF')
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[10]['game_type'], 'PLAYOFF')
        with self.assertRaises(PreventUpdate):
            team_stats_page.render_team_stats_download(
                job, {'nonce': 10}, 'PLG', 's', 'PLAYOFF', 'all',
            )
        with self.assertRaises(PreventUpdate):
            team_stats_page.render_team_stats_download(
                None, job, 'PLG', 's', 'PLAYOFF', 'all',
            )

    def test_load_failure_still_stamps_applied(self):
        with patch.object(
            team_stats_page, 'team_stats_payload', side_effect=RuntimeError('secret'),
        ):
            result = team_stats_page.render_team_stats(
                None, 'all', 'all', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )
        self.assertEqual(result[0].title, 'Error')
        self.assertIn(ERROR_GAME, str(result[0].children))
        self.assertIsNone(result[5])
        self.assertEqual(result[10], {
            'league': 'PLG',
            'season': 's',
            'game_type': None,
            'ok': False,
        })
        self.assertIs(result[26], no_update)
        self.assertNotIn('secret', str(result[0]))

    def test_slice_keeps_the_period_and_does_not_ask_for_a_download(self):
        payload = _payload('s', 'REGULAR', '1')
        payload['period_chips'] = [
            {'label': 'All', 'value': 'all'},
            {'label': '1Q', 'value': '1'},
        ]
        payload['opponent'] = 'b'
        payload['opponent_visible'] = True
        payload['stadium'] = 'all'
        payload['site'] = 'home'
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-opponent'), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch:
            result = team_stats_page.render_team_stats(
                {'skeleton': True, 'nonce': 4, 'game_type': 'REGULAR'},
                '1',
                'b',
                'all',
                'home',
                'a',
                'PLG',
                's',
                'REGULAR',
            )
        self.assertEqual(fetch.call_args.kwargs['reason'], 'slice')
        self.assertEqual(fetch.call_args.kwargs['period'], '1')
        self.assertEqual(fetch.call_args.kwargs['opponent'], 'b')
        self.assertEqual(fetch.call_args.kwargs['site'], 'home')
        self.assertEqual(fetch.call_args.kwargs['team'], 'a')
        self.assertIs(result[8], no_update)
        self.assertIs(result[10], no_update)
        self.assertIs(result[26], no_update)

    def test_scope_click_holds_cards_until_the_card_paint(self):
        intent = {
            'league': 'EASL',
            'season': None,
            'game_type': None,
            'skeleton': True,
            'nonce': 11,
        }
        chrome = {
            'ok': True,
            'needs_cards': True,
            'season_id': 'easl-season',
            'seasons': [{'label': '2026-27', 'value': 'easl-season'}],
            'game_type': 'REGULAR',
            'game_types': [{'label': 'Regular', 'value': 'REGULAR'}],
            'game_type_visible': False,
            'period': 'all',
            'period_chips': [{'label': 'All', 'value': 'all'}],
            'period_visible': False,
            'team': 'all',
            'team_options': [
                {'label': 'All Teams', 'value': 'all'},
                {'label': 'Aces', 'value': 'aces'},
            ],
            'team_visible': True,
            'opponent': 'all',
            'opponent_options': [{'label': 'vs All Teams', 'value': 'all'}],
            'opponent_width_labels': ['vs All Teams', 'vs Aces'],
            'opponent_visible': False,
            'stadium': 'all',
            'stadium_options': [{'label': 'All Stadiums', 'value': 'all'}],
            'stadium_visible': False,
            'site': 'all',
            'empty': True,
            'cards': None,
            'stamp': 'Last Update: old',
        }
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-intent'), \
                patch.object(team_stats_page, 'schedule_chrome', return_value=chrome) as listed, \
                patch.object(team_stats_page, 'team_stats_payload') as fetch:
            result = team_stats_page.render_team_stats(
                intent, '1', 'b', 'v1', 'home', 'aces', 'PLG', 'plg-season', 'PLAYOFF',
            )
        fetch.assert_not_called()
        self.assertEqual(listed.call_args.args[0], 'EASL')
        self.assertEqual(listed.call_args.kwargs['season_id'], 'plg-season')
        self.assertTrue(listed.call_args.kwargs['reset'])
        self.assertIn('Skeleton', _names(result[0]))
        self.assertIs(result[1], no_update)
        self.assertEqual(result[3], 'easl-season')
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[9], {'display': 'none'})
        self.assertEqual(result[10]['league'], 'EASL')
        self.assertEqual(result[10]['season'], 'easl-season')
        self.assertEqual(result[10]['game_type'], 'REGULAR')
        self.assertTrue(result[10]['ok'])
        self.assertEqual(result[19], 'all')
        self.assertEqual(result[26]['phase'], 'cards')
        self.assertEqual(result[26]['season'], 'easl-season')
        self.assertEqual(result[26]['game_type'], 'REGULAR')
        self.assertEqual(result[26]['team'], 'all')
        self.assertEqual(result[26]['nonce'], 11)

    def test_card_job_downloads_the_chosen_type_without_scope_reset(self):
        job = {
            'league': 'EASL',
            'season': 'easl-season',
            'game_type': 'REGULAR',
            'team': 'all',
            'opponent': 'all',
            'stadium': 'all',
            'site': 'all',
            'phase': 'cards',
            'nonce': 11,
        }
        payload = _payload('easl-season', 'REGULAR')
        payload['team'] = 'all'
        with patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, '_view', return_value='cards'):
            result = team_stats_page.render_team_stats_download(
                job, dict(job), 'PLG', 'plg-season', 'PLAYOFF', '1',
                'b', 'v1', 'home', 'aces',
            )
        self.assertEqual(result[0], 'cards')
        self.assertEqual(fetch.call_args.kwargs['reason'], 'type')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'REGULAR')
        self.assertEqual(fetch.call_args.kwargs['team'], 'all')
        self.assertEqual(fetch.call_args.kwargs['opponent'], 'all')
        self.assertEqual(result[19], 'all')


def _walk(node):
    yield node
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float, dict)):
        yield from _walk(children)


class TeamStatsShowOppTests(unittest.TestCase):
    def test_switch_stays_outside_the_body(self):
        tree = team_stats_page.layout()
        body = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-body')
        self.assertNotIn('ts-show-opp', {getattr(node, 'id', None) for node in _walk(body)})
        switch = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-show-opp')
        self.assertIsInstance(switch, dmc.Switch)
        self.assertEqual(switch.label, 'Show Opp')
        self.assertEqual(switch.size, 'sm')
        self.assertEqual(switch.color, 'gray')
        self.assertFalse(bool(switch.checked))
        self.assertEqual(switch.ms, 'auto')
        bar = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-period-bar')
        self.assertIsInstance(bar, dmc.Group)
        self.assertIsNone(getattr(bar, 'style', None) or None)
        child_ids = [getattr(child, 'id', None) for child in bar.children]
        self.assertEqual(child_ids, ['ts-period-wrap', 'ts-show-opp'])
        wrap = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-period-wrap')
        self.assertEqual(wrap.style, {'display': 'none'})
        scope = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-filter-pack')
        self.assertIn('filter-pack-scope', scope.className)
        scope_classes = [child.className for child in scope.children]
        self.assertEqual(scope_classes, [
            'filter-cluster filter-cluster-league',
            'filter-cluster filter-cluster-type',
        ])
        match = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-match-pack')
        self.assertIn('filter-pack-match', match.className)
        self.assertEqual([child.className for child in match.children], [
            'filter-cluster filter-cluster-team',
            'filter-cluster filter-cluster-opp',
        ])
        team = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-team')
        self.assertIsInstance(team, dmc.Select)
        self.assertEqual(team.value, 'all')
        self.assertEqual(team.data[0]['label'], 'All Teams')
        self.assertFalse(team.searchable)
        self.assertFalse(team.clearable)
        self.assertFalse(team.allowDeselect)
        tabs = [
            node.value for node in _walk(tree)
            if isinstance(node, dmc.TabsTab)
        ]
        self.assertEqual(tabs, [
            'tab-bs', 'tab-rotation', 'tab-shot-chart', 'tab-lineup', 'tab-matchups',
        ])
        opponent = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-opponent')
        self.assertIsInstance(opponent, dmc.Select)
        self.assertEqual(opponent.value, 'all')
        self.assertEqual(opponent.data[0]['label'], 'vs All Teams')
        self.assertFalse(opponent.searchable)
        self.assertFalse(opponent.clearable)
        opponent_cluster = next(
            node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-opponent-cluster'
        )
        self.assertEqual(opponent_cluster.style, {'display': 'none'})
        place = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-place-pack')
        self.assertIn('filter-pack-place', place.className)
        place_classes = [child.className for child in place.children]
        self.assertEqual(place_classes, [
            'filter-cluster filter-cluster-stadium',
            'filter-cluster filter-cluster-site',
        ])
        stadium_cluster = next(
            node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-stadium-cluster'
        )
        self.assertEqual(stadium_cluster.style, {'display': 'none'})
        stadium = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-stadium')
        self.assertEqual(stadium.value, 'all')
        self.assertEqual(stadium.data[0]['label'], 'All Stadiums')
        site = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-site')
        self.assertIsInstance(site, dmc.SegmentedControl)
        self.assertEqual(site.value, 'all')
        self.assertEqual([item['label'] for item in site.data], ['All', 'Away', 'Home'])
        self.assertEqual(site.size, 'xs')

    def test_opp_row_uses_red_and_group_edges_on_data_cells(self):
        cell = lambda text, winner=False, opp_best=False: {
            'text': text, 'winner': winner, 'opp_best': opp_best,
        }

        def team_row(name, pts, winner=False):
            return {
                'Team': cell(name),
                'GP': cell('1'),
                'Min': cell('10:00'),
                '2M': cell('1.0'),
                '2A': cell('2.0'),
                '2FG%': cell('.500'),
                'PTS': cell(pts, winner=winner),
                'TO': cell('1.0'),
            }

        def opp_row(pts, opp_best=False):
            row = team_row('Opp', pts)
            row['opp'] = True
            row['Team'] = cell('Opp')
            row['GP'] = cell('')
            row['Min'] = cell('')
            row['PTS'] = cell(pts, opp_best=opp_best)
            return row

        paper = team_stats_page._paper({
            'id': 'team',
            'columns': ['Team', 'GP', 'Min', '2M', '2A', '2FG%', 'PTS', 'TO'],
            'rows': [team_row('Aces', '20.0', winner=True), team_row('Braves', '10.0')],
            'opp_rows': [opp_row('10.0'), opp_row('20.0', opp_best=True)],
        })
        table = next(node for node in _walk(paper) if isinstance(node, dmc.Table))
        body = table.children[1]
        classes = [row.className for row in body.children]
        self.assertEqual(classes, [
            'braves-clean-row',
            'braves-clean-row braves-opp-row',
            'braves-clean-row',
            'braves-clean-row braves-opp-row',
        ])
        aces_pts = next(td for td in body.children[0].children if td.children == '20.0')
        self.assertEqual(aces_pts.style.get('color'), '#0077b6')
        opp_pts = next(td for td in body.children[3].children if td.children == '20.0')
        self.assertEqual(opp_pts.style.get('color'), '#e63946')
        self.assertEqual(opp_pts.style.get('fontWeight'), 700)
        hidden_pts = next(td for td in body.children[1].children if td.children == '10.0')
        self.assertFalse(getattr(hidden_pts, 'style', None))
        opp_label = body.children[1].children[0]
        self.assertEqual(opp_label.children, 'Opp')
        self.assertIn('braves-opp-label', opp_label.className.split())
        self.assertEqual(body.children[1].children[1].children, '')
        self.assertEqual(body.children[1].children[2].children, '')
        headers = [th for th in _walk(table.children[0]) if isinstance(th, dmc.TableTh)]
        self.assertFalse(any(
            'braves-group-end' in (th.className or '').split() for th in headers
        ))
        def edge_flags(row):
            return [
                'braves-group-end' in (getattr(td, 'className', None) or '').split()
                for td in row.children
            ]
        self.assertEqual(edge_flags(body.children[0]), [
            False, False, True, False, False, True, False, False,
        ])
        self.assertEqual(edge_flags(body.children[1]), edge_flags(body.children[0]))
        pace = team_stats_page._paper({
            'id': 'pace',
            'columns': ['Team', 'GP', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R'],
            'rows': [{
                'Team': cell('Aces'), 'GP': cell('1'), 'Pace': cell('70.0'),
                'eFG%': cell('50.0%'), 'TO%': cell('12.0%'),
                'ORB%': cell('20.0%'), 'FT-R': cell('10.0%'),
            }],
            'opp_rows': [],
        })
        pace_headers = [
            th for th in _walk(pace) if isinstance(th, dmc.TableTh)
        ]
        self.assertFalse(any(
            'braves-group-end' in (th.className or '').split() for th in pace_headers
        ))
        pace_table = next(node for node in _walk(pace) if isinstance(node, dmc.Table))
        pace_body = [
            'braves-group-end' in (getattr(td, 'className', None) or '').split()
            for td in pace_table.children[1].children[0].children
        ]
        self.assertEqual(pace_body, [False, False, True, False, False, False, True])
        advanced = team_stats_page._paper({
            'id': 'advanced',
            'columns': ['Team', 'GP', 'PPP'],
            'rows': [{'Team': cell('Aces'), 'GP': cell('1'), 'PPP': cell('1.10')}],
            'opp_rows': [],
        })
        self.assertFalse(any(
            'braves-group-end' in ((th.className or '').split())
            for th in _walk(advanced) if isinstance(th, dmc.TableTh)
        ))


class TeamStatsMatchupLabelTests(unittest.TestCase):
    def test_long_names_keep_vs_on_the_first_phone_line(self):
        long_name = 'Anyang Jung Kwan Jang Red Boosters'
        cell = lambda text: {'text': text, 'winner': False, 'opp_best': False}
        paper = team_stats_page._paper({
            'id': 'team',
            'columns': ['Team', 'GP'],
            'rows': [
                {'Team': cell(long_name), 'GP': cell('4'), 'summary': True},
                {'Team': cell(long_name + ' vs'), 'GP': cell('2')},
            ],
            'opp_rows': [
                {'Team': cell('Opp'), 'GP': cell(''), 'opp': True, 'summary': True},
                {'Team': cell(long_name), 'GP': cell(''), 'opp': True},
            ],
        })
        body = next(node for node in _walk(paper) if isinstance(node, dmc.TableTbody))
        summary, summary_opp, matchup, opp = body.children
        self.assertIn('braves-summary-row', summary.className)
        self.assertNotIn('braves-summary-end', summary.className)
        self.assertIn('braves-summary-end', summary_opp.className)
        full = next(
            node for node in _walk(summary.children[0])
            if getattr(node, 'className', None) == 'ts-team-full'
        )
        self.assertEqual(full.children, long_name)
        match_lines = [
            node.children for node in _walk(matchup.children[0])
            if getattr(node, 'className', None) in ('ts-team-line1', 'ts-team-line2')
        ]
        self.assertEqual(match_lines, [
            'Anyang Jung Kwan Jang vs',
            'Red Boosters',
        ])
        opp_lines = [
            node.children for node in _walk(opp.children[0])
            if getattr(node, 'className', None) in ('ts-team-line1', 'ts-team-line2')
        ]
        self.assertEqual(opp_lines, ['Anyang Jung Kwan Jang', 'Red Boosters'])
        self.assertEqual(summary_opp.children[0].children, 'Opp')


class TeamStatsShowOppLockTests(unittest.TestCase):
    def test_single_team_forces_show_opp_and_remembers_the_old_choice(self):
        checked, disabled, memory = team_stats_page.lock_show_opp('aces', False, False, None)
        self.assertTrue(checked)
        self.assertTrue(disabled)
        self.assertIs(memory, False)

    def test_another_team_does_not_overwrite_the_remembered_choice(self):
        checked, disabled, memory = team_stats_page.lock_show_opp('braves', True, True, False)
        self.assertIs(checked, no_update)
        self.assertIs(disabled, no_update)
        self.assertIs(memory, no_update)

    def test_all_teams_restores_the_remembered_choice(self):
        checked, disabled, memory = team_stats_page.lock_show_opp('all', True, True, False)
        self.assertIs(checked, False)
        self.assertIs(disabled, False)
        self.assertIs(memory, no_update)


class TeamStatsRotationTests(unittest.TestCase):
    def test_rotation_waits_until_that_tab_is_open(self):
        with self.assertRaises(PreventUpdate):
            team_stats_page.render_team_rotation(
                'tab-bs', {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'aces', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )

    def test_all_teams_asks_for_one_team_without_a_fetch(self):
        with patch.object(team_stats_page, 'rotation_games') as fetch:
            view = team_stats_page.render_team_rotation(
                'tab-rotation',
                {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'all', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )
        fetch.assert_not_called()
        self.assertIn('Select a team.', str(view))
        self.assertIn('Choose one team.', str(view))

    def test_no_games_uses_the_filter_empty_copy(self):
        source = {'ok': True, 'select_team': False, 'empty': True, 'games': []}
        with patch.object(team_stats_page, 'rotation_games', return_value=source):
            view = team_stats_page.render_team_rotation(
                'tab-rotation',
                {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'aces', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )
        self.assertIn('No games in this view.', str(view))
        self.assertIn('Team', str(view))

    def test_no_usable_lineup_is_empty_not_an_error(self):
        source = {
            'ok': True, 'select_team': False, 'empty': False,
            'games': [{'fixture_id': 'g1'}], 'team': 'aces', 'id_table': {},
        }
        with patch.object(team_stats_page, 'rotation_games', return_value=source), \
                patch.object(team_stats_page, 'season_aggregate', return_value={'n': 0, 'players': []}):
            view = team_stats_page.render_team_rotation(
                'tab-rotation',
                {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'aces', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )
        self.assertIn('No rotation chart for this view.', str(view))
        self.assertNotIn('Traceback', str(view))

    def test_unpainted_scope_keeps_the_chart_skeleton(self):
        view = team_stats_page.render_team_rotation(
            'tab-rotation',
            {'league': 'PLG', 'season': 'old', 'game_type': 'REGULAR'},
            'aces', 'all', 'all', 'all', 'PLG', 'old', 'REGULAR',
            {'league': 'EASL', 'season': 'new', 'game_type': None, 'nonce': 1},
        )
        self.assertIn('Skeleton', _names(view))
        self.assertNotIn('Select a team.', str(view))

    def test_foreign_season_id_after_paint_asks_for_a_team(self):
        with patch.object(
            team_stats_page, 'selectable_seasons', return_value=[('2026-27', 'easl-season')],
        ), patch.object(team_stats_page, 'rotation_games') as fetch:
            view = team_stats_page.render_team_rotation(
                'tab-rotation',
                {
                    'league': 'EASL', 'season': 'easl-season',
                    'game_type': 'REGULAR', 'ok': True,
                },
                'all', 'all', 'all', 'all', 'EASL', 'easl-season', 'REGULAR',
                {'league': 'EASL', 'season': 'plg-season', 'game_type': None},
            )
        fetch.assert_not_called()
        self.assertIn('Select a team.', str(view))
        self.assertNotIn('Skeleton', _names(view))

    def test_rotation_graph_locks_range_selection(self):
        from plotly.graph_objects import Figure

        chart = team_stats_page._rotation_chart(
            Figure(), {'n': 1, 'columns': [], 'counts': []},
        )
        graph = next(
            node for node in _walk(chart)
            if getattr(node, 'id', None) == 'ts-rotation-graph'
        )
        self.assertFalse(graph.config.get('displayModeBar'))
        self.assertTrue(graph.config.get('responsive'))
        self.assertFalse(graph.config.get('scrollZoom'))
        self.assertFalse(graph.config.get('doubleClick'))
        self.assertNotIn('staticPlot', graph.config)

    def test_failed_schedule_shows_the_load_error(self):
        view = team_stats_page.render_team_rotation(
            'tab-rotation',
            {
                'league': 'EASL', 'season': 'easl-season',
                'game_type': 'REGULAR', 'ok': False,
            },
            'all', 'all', 'all', 'all', 'EASL', 'easl-season', 'REGULAR',
            {'league': 'EASL', 'season': None, 'game_type': None},
        )
        self.assertIn(ERROR_GAME, str(view))
        self.assertNotIn('Select a team.', str(view))


class TeamStatsShotChartTests(unittest.TestCase):
    def test_shot_chart_waits_until_that_tab_is_open(self):
        with self.assertRaises(PreventUpdate):
            team_stats_page.render_team_shot_chart(
                'tab-bs', {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'aces', 'all', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )

    def test_all_teams_asks_for_one_team_without_a_fetch(self):
        with patch.object(team_stats_page, 'rotation_games') as fetch:
            view = team_stats_page.render_team_shot_chart(
                'tab-shot-chart',
                {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'all', 'all', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            )
        fetch.assert_not_called()
        self.assertIn('Select a team.', str(view))
        self.assertIn('Choose one team.', str(view))

    def test_no_games_uses_the_filter_empty_copy(self):
        source = {'ok': True, 'select_team': False, 'empty': True, 'games': []}
        with patch.object(team_stats_page, 'rotation_games', return_value=source):
            view = team_stats_page.render_team_shot_chart(
                'tab-shot-chart',
                {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR'},
                'aces', 'all', 'all', 'all', '1', 'PLG', 's', 'REGULAR',
            )
        self.assertIn('No games in this view.', str(view))
        self.assertIn('Team', str(view))

    def test_two_courts_keep_opp_and_skip_a_missing_play_by_play(self):
        source = {
            'ok': True,
            'select_team': False,
            'empty': False,
            'team': 'aces',
            'opponent': 'all',
            'id_table': {'aces': 'Aces', 'bears': 'Bears'},
            'games': [
                {
                    'fixture_id': 'g1',
                    'home': 'aces',
                    'away': 'bears',
                    'pbp': [
                        {
                            'entityId': 'aces', 'eventType': '2pt', 'periodId': 1,
                            'success': True, 'x': 6, 'y': 50,
                        },
                        {
                            'entityId': 'bears', 'eventType': '2pt', 'periodId': 1,
                            'success': False, 'x': 6, 'y': 50,
                        },
                    ],
                },
                {'fixture_id': 'g2', 'home': 'aces', 'away': 'cubs', 'pbp': None},
            ],
        }
        with patch.object(team_stats_page, 'rotation_games', return_value=source):
            view = team_stats_page.render_team_shot_chart(
                'tab-shot-chart',
                {'league': 'PLG', 'season': 's', 'game_type': 'REGULAR', 'ok': True},
                'aces', 'all', 'all', 'all', '1', 'PLG', 's', 'REGULAR',
            )
        self.assertIsInstance(view, dmc.SimpleGrid)
        self.assertFalse(any(isinstance(node, dmc.SegmentedControl) for node in _walk(view)))
        self.assertFalse(any(isinstance(node, dmc.Select) for node in _walk(view)))
        names = [
            node.children for node in _walk(view)
            if getattr(node, 'fw', None) == 700
        ]
        self.assertEqual(names, ['Aces', 'Opp'])
        images = [node for node in _walk(view) if getattr(node, 'alt', None)]
        self.assertEqual(len(images), 2)
        self.assertIn('100.0', _svg(images[0].src))
        self.assertIn('0.0', _svg(images[1].src))
        self.assertEqual(images[0].style.get('width'), '100%')
        columns = [node for node in view.children if getattr(node, 'style', None)]
        self.assertEqual(columns[0].style.get('maxWidth'), '380px')

    def test_named_opponent_uses_the_bare_name(self):
        source = {
            'ok': True,
            'select_team': False,
            'empty': False,
            'team': 'aces',
            'opponent': 'bears',
            'id_table': {'aces': 'Aces', 'bears': 'Bears'},
            'games': [{
                'fixture_id': 'g1',
                'home': 'aces',
                'away': 'bears',
                'pbp': [{
                    'entityId': 'aces', 'eventType': '2pt', 'periodId': 2,
                    'success': True, 'x': 6, 'y': 50,
                }],
            }],
        }
        with patch.object(team_stats_page, 'rotation_games', return_value=source):
            view = team_stats_page.render_team_shot_chart(
                'tab-shot-chart',
                {'ok': True},
                'aces', 'bears', 'all', 'all', '1', 'PLG', 's', 'REGULAR',
            )
        names = [
            node.children for node in _walk(view)
            if getattr(node, 'fw', None) == 700
        ]
        self.assertEqual(names, ['Aces', 'Bears'])
        images = [node for node in _walk(view) if getattr(node, 'alt', None)]
        self.assertIn('font-size="16">-</text>', _svg(images[0].src))

    def test_period_control_stays_inside_the_card(self):
        tree = team_stats_page.layout()
        card = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-shot-card')
        self.assertEqual(card.style.get('maxWidth'), '808px')
        self.assertEqual(
            [getattr(child, 'id', None) for child in card.children],
            ['ts-shot-period-bar', 'ts-shot-body'],
        )
        bar = card.children[0]
        self.assertEqual(bar.mb, 'sm')
        self.assertEqual(bar.style, {'display': 'none'})
        control = next(node for node in _walk(bar) if getattr(node, 'id', None) == 'ts-shot-period')
        self.assertIsInstance(control, dmc.SegmentedControl)
        self.assertEqual(control.value, 'all')
        self.assertEqual(control.radius, 'md')
        self.assertEqual(control.size, 'xs')
        body = card.children[1]
        self.assertFalse(any(getattr(node, 'id', None) == 'ts-shot-period' for node in _walk(body)))
        self.assertFalse(any(isinstance(node, (dmc.Select, dmc.SegmentedControl)) for node in _walk(body)))
        pane = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-shot')
        self.assertIn(card, pane.children if isinstance(pane.children, (list, tuple)) else [pane.children])

        listed = _callbacks('ts-shot-period.value')
        mirror = [item for item in listed if item.get('clientside_function')]
        self.assertEqual(len(mirror), 1)
        self.assertEqual(
            _pairs(mirror[0]['inputs']),
            [('ts-period', 'value'), ('ts-shot-period', 'value')],
        )
        self.assertIn('ts-period.value', mirror[0]['output'])
        self.assertTrue(mirror[0]['prevent_initial_call'])
        paints = [
            item for item in _callbacks('ts-shot-body.children')
            if not item.get('clientside_function')
        ]
        self.assertEqual(len(paints), 1)
        self.assertIn(('ts-period', 'value'), _pairs(paints[0]['inputs']))
        self.assertNotIn('ts-shot-period', {item['id'] for item in paints[0]['inputs']})
        rotation = [
            item for item in _callbacks('ts-rotation.children')
            if not item.get('clientside_function')
        ]
        self.assertEqual(len(rotation), 1)
        rotation_ids = {item['id'] for item in rotation[0]['inputs'] + rotation[0]['state']}
        self.assertNotIn('ts-period', rotation_ids)
        self.assertNotIn('ts-shot-period', rotation_ids)

    def test_slice_callback_skeletons_the_shot_chart_on_a_team_change(self):
        text = Path('pages/team_stats.py').read_text(encoding='utf-8')
        self.assertIn("Output('ts-shot-body', 'children', allow_duplicate=True)", text)
        self.assertNotIn("Output('ts-shot', 'children'", text)
        self.assertIn("shot = __ROTATION_PICK__;", text)
        self.assertIn("var shot = skip;", text)
        self.assertIn("shot = __SHOT_LOADING__;", text)
        self.assertIn("!same(team, current.team)", text)
        self.assertIn(
            "return [__CHART_LOADING__, __SHOT_LOADING__, __TABLE_LOADING__, __TABLE_LOADING__];",
            text,
        )
        self.assertIn("lineup = __TABLE_LOADING__;", text)
        self.assertIn("matchup = __TABLE_LOADING__;", text)
        self.assertIn("var lineup = skip;", text)
        self.assertIn("tab === 'tab-lineup'", text)
        self.assertIn("tab === 'tab-matchups'", text)
        self.assertIn("Output('ts-lineup', 'style')", text)
        self.assertIn("Output('ts-matchups', 'style')", text)
        self.assertIn("Output('ts-show-opp', 'style')", text)
        self.assertIn("tab === 'tab-shot-chart'", text)

    def test_shot_chart_skeleton_matches_the_two_courts(self):
        view = team_stats_page.shot_chart_skeleton()
        self.assertIsInstance(view, dmc.SimpleGrid)
        self.assertEqual(view.cols, {'base': 1, 'sm': 2})
        self.assertEqual(view.spacing, '16px')
        self.assertEqual(len(view.children), 2)
        self.assertIsNot(view.children[0], view.children[1])
        self.assertFalse(any(
            isinstance(node, (dmc.Select, dmc.SegmentedControl)) for node in _walk(view)
        ))
        for column in view.children:
            self.assertEqual(column.style.get('maxWidth'), '380px')
            self.assertEqual(column.style.get('marginInline'), 'auto')
            skeletons = [node for node in _walk(column) if isinstance(node, dmc.Skeleton)]
            self.assertEqual(len(skeletons), 2)
            name, court = skeletons
            self.assertEqual(name.height, 14)
            self.assertEqual(name.width, 160)
            self.assertEqual(name.radius, 'sm')
            self.assertEqual(court.radius, 'md')
            self.assertEqual(court.style.get('width'), '100%')
            self.assertEqual(court.style.get('aspectRatio'), '380.05 / 400.51')

    def test_pending_scope_uses_the_court_skeleton(self):
        view = team_stats_page.render_team_shot_chart(
            'tab-shot-chart',
            {'league': 'PLG', 'season': 'old', 'game_type': 'REGULAR', 'ok': True},
            'aces', 'all', 'all', 'all', 'all', 'PLG', 's', 'REGULAR',
            {'league': 'EASL', 'season': 's', 'game_type': 'REGULAR', 'nonce': 1},
        )
        self.assertIsInstance(view, dmc.SimpleGrid)
        courts = [
            node for node in _walk(view)
            if isinstance(node, dmc.Skeleton)
            and (getattr(node, 'style', None) or {}).get('aspectRatio')
        ]
        self.assertEqual(len(courts), 2)


def _text_bits(node):
    found = []
    for item in _walk(node):
        children = getattr(item, 'children', None)
        if isinstance(children, str):
            found.append(children)
    return found


class TeamStatsLineupTabTests(unittest.TestCase):
    def test_lineup_controls_stay_outside_the_body(self):
        tree = team_stats_page.layout()
        pane = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-lineup')
        self.assertEqual(pane.style, {'display': 'none'})
        body = next(node for node in _walk(pane) if getattr(node, 'id', None) == 'ts-lineup-body')
        self.assertNotIn('ts-lineup-show-opp', {getattr(node, 'id', None) for node in _walk(body)})
        self.assertFalse(any(isinstance(node, dmc.SegmentedControl) for node in _walk(body)))
        switch = next(node for node in _walk(pane) if getattr(node, 'id', None) == 'ts-lineup-show-opp')
        self.assertIsInstance(switch, dmc.Switch)
        self.assertEqual(switch.label, 'Show Opp')
        self.assertEqual(switch.size, 'sm')
        self.assertEqual(switch.color, 'gray')
        self.assertFalse(bool(switch.checked))
        size = next(node for node in _walk(pane) if getattr(node, 'id', None) == 'ts-lineup-size')
        self.assertEqual([item['label'] for item in size.data], [
            '5 Players', '4 Players', '3 Players', '2 Players',
        ])
        self.assertEqual(size.value, '5')
        matchups = next(node for node in _walk(tree) if getattr(node, 'id', None) == 'ts-matchups')
        self.assertEqual(matchups.style, {'display': 'none'})
        self.assertFalse(any(
            isinstance(node, (dmc.SegmentedControl, dmc.Switch)) for node in _walk(matchups)
        ))

    def test_callbacks_ignore_period_and_the_page_switch(self):
        lineup = [
            item for item in _callbacks('ts-lineup-body.children')
            if not item.get('clientside_function')
        ]
        matchups = [
            item for item in _callbacks('ts-matchups-body.children')
            if not item.get('clientside_function')
        ]
        self.assertEqual(len(lineup), 1)
        self.assertEqual(len(matchups), 1)
        self.assertTrue(lineup[0]['prevent_initial_call'])
        self.assertTrue(matchups[0]['prevent_initial_call'])
        lineup_inputs = _pairs(lineup[0]['inputs'])
        lineup_state = _pairs(lineup[0]['state'])
        self.assertIn(('ts-lineup-size', 'value'), lineup_inputs)
        self.assertNotIn(('ts-lineup-show-opp', 'checked'), lineup_inputs)
        self.assertIn(('ts-lineup-show-opp', 'checked'), lineup_state)
        for item in (lineup[0], matchups[0]):
            names = {dep[0] for dep in _pairs(item['inputs']) + _pairs(item['state'])}
            self.assertNotIn('ts-period', names)
            self.assertNotIn('ts-show-opp', names)
            self.assertNotIn('ts-shot-period', names)
        self.assertNotIn('ts-lineup-size', {dep[0] for dep in _pairs(matchups[0]['inputs'])})

    def test_hidden_tab_does_not_load(self):
        with patch.object(team_stats_page, 'rotation_games') as games:
            with self.assertRaises(PreventUpdate):
                team_stats_page.render_team_lineup(
                    'tab-bs', {'ok': True}, 'aces', 'all', 'all', 'all', '5', False,
                    'PLG', 's', 'REGULAR', None,
                )
            with self.assertRaises(PreventUpdate):
                team_stats_page.render_team_matchups(
                    'tab-rotation', {'ok': True}, 'aces', 'all', 'all', 'all',
                    'PLG', 's', 'REGULAR', None,
                )
        games.assert_not_called()

    def test_all_teams_asks_for_one_team_without_a_fetch(self):
        with patch.object(team_stats_page, 'rotation_games') as games:
            lineup = team_stats_page.render_team_lineup(
                'tab-lineup', {'ok': True}, 'all', 'all', 'all', 'all', '5', False,
                'PLG', 's', 'REGULAR', None,
            )
            matchups = team_stats_page.render_team_matchups(
                'tab-matchups', {'ok': True}, 'all', 'all', 'all', 'all',
                'PLG', 's', 'REGULAR', None,
            )
        games.assert_not_called()
        self.assertIn('Select a team.', _text_bits(lineup))
        self.assertIn('Choose one team.', _text_bits(lineup))
        self.assertIn('Select a team.', _text_bits(matchups))

    def test_pending_scope_uses_the_table_skeleton(self):
        intent = {'league': 'EASL', 'season': 's', 'game_type': 'REGULAR', 'nonce': 1}
        applied = {'league': 'PLG', 'season': 'old', 'game_type': 'REGULAR', 'ok': True}
        view = team_stats_page.render_team_lineup(
            'tab-lineup', applied, 'aces', 'all', 'all', 'all', '5', False,
            'PLG', 's', 'REGULAR', intent,
        )
        self.assertIsInstance(view, dmc.Stack)
        self.assertGreaterEqual(
            len([node for node in _walk(view) if isinstance(node, dmc.Skeleton)]),
            1,
        )

    def test_failed_scope_is_an_alert(self):
        with patch.object(team_stats_page, 'rotation_games') as games:
            view = team_stats_page.render_team_matchups(
                'tab-matchups', {'ok': False}, 'aces', 'all', 'all', 'all',
                'PLG', 's', 'REGULAR', None,
            )
        games.assert_not_called()
        self.assertIsInstance(view, dmc.Alert)
        self.assertIn(ERROR_GAME, _text_bits(view))

    def test_empty_games_and_empty_tables_use_their_copy(self):
        empty_games = {'ok': True, 'select_team': False, 'empty': True, 'games': []}
        with patch.object(team_stats_page, 'rotation_games', return_value=empty_games):
            view = team_stats_page.render_team_lineup(
                'tab-lineup', {'ok': True}, 'aces', 'all', 'all', 'all', '5', False,
                'PLG', 's', 'REGULAR', None,
            )
        self.assertIn('No games in this view.', _text_bits(view))
        source = {
            'ok': True, 'select_team': False, 'empty': False,
            'games': [{'fixture_id': 'g1'}], 'team': 'aces',
        }
        with patch.object(team_stats_page, 'rotation_games', return_value=source), \
                patch.object(team_stats_page, 'season_lineup_records', return_value=[]), \
                patch.object(team_stats_page, 'season_matchup_records', return_value=[]):
            lineup = team_stats_page.render_team_lineup(
                'tab-lineup', {'ok': True}, 'aces', 'all', 'all', 'all', '5', False,
                'PLG', 's', 'REGULAR', None,
            )
            matchups = team_stats_page.render_team_matchups(
                'tab-matchups', {'ok': True}, 'aces', 'all', 'all', 'all',
                'PLG', 's', 'REGULAR', None,
            )
        self.assertIn('No lineups for this view.', _text_bits(lineup))
        self.assertIn('No 5-player matchups for this view.', _text_bits(matchups))
        self.assertIn('Switch Game Type, Team, Opponent, Stadium, or Home/Away.', _text_bits(lineup))

    def test_lineup_grid_paginates_every_size(self):
        source = {
            'ok': True, 'select_team': False, 'empty': False,
            'games': [{'fixture_id': 'g1'}], 'team': 'aces',
        }
        records = [
            {'Lineup': 'Lin-Wu', 'Min': '1:00', '+/-': 0, '_opp': False, '_pair': 'p'},
            {'Lineup': 'Lin-Wu', 'Min': '', '+/-': '', '_opp': True, '_pair': 'p'},
        ]
        with patch.object(team_stats_page, 'rotation_games', return_value=source), \
                patch.object(team_stats_page, 'season_lineup_records', return_value=records):
            sized = team_stats_page.render_team_lineup(
                'tab-lineup', {'ok': True}, 'aces', 'all', 'all', 'all', '4', True,
                'PLG', 's', 'REGULAR', None,
            )
            full = team_stats_page.render_team_lineup(
                'tab-lineup', {'ok': True}, 'aces', 'all', 'all', 'all', '5', False,
                'PLG', 's', 'REGULAR', None,
            )
            paired = team_stats_page.render_team_lineup(
                'tab-lineup', {'ok': True}, 'aces', 'all', 'all', 'all', '5', True,
                'PLG', 's', 'REGULAR', None,
            )
        grid = next(node for node in _walk(sized) if getattr(node, 'id', None) == 'ts-lineup-grid')
        self.assertIn('braves-lineup-grid', grid.className)
        self.assertEqual(grid.dashGridOptions['paginationPageSize'], 40)
        self.assertIs(grid.dashGridOptions['paginationPageSizeSelector'], False)
        self.assertEqual(grid.dashGridOptions['isExternalFilterPresent']['function'], 'false')
        self.assertEqual(grid.rowData[0]['+/-'], 0)
        self.assertTrue(grid.rowData[1]['_opp'])
        fields = []

        def _fields(columns):
            for column in columns:
                if column.get('children'):
                    _fields(column['children'])
                elif column.get('field'):
                    fields.append(column['field'])

        _fields(grid.columnDefs)
        self.assertEqual(len(fields), 27)
        self.assertNotIn('_opp', fields)
        full_grid = next(node for node in _walk(full) if getattr(node, 'id', None) == 'ts-lineup-grid')
        self.assertTrue(full_grid.dashGridOptions.get('pagination'))
        self.assertEqual(full_grid.dashGridOptions['paginationPageSize'], 20)
        self.assertIs(full_grid.dashGridOptions['paginationPageSizeSelector'], False)
        paired_grid = next(node for node in _walk(paired) if getattr(node, 'id', None) == 'ts-lineup-grid')
        self.assertEqual(paired_grid.dashGridOptions['paginationPageSize'], 40)
        self.assertIs(paired_grid.dashGridOptions['paginationPageSizeSelector'], False)

    def test_matchup_grid_keeps_both_names(self):
        source = {
            'ok': True, 'select_team': False, 'empty': False,
            'games': [{'fixture_id': 'g1'}], 'team': 'aces',
        }
        records = [
            {'Lineup': 'Lin-Wu', 'Min': '1:00', '+/-': 3, '_opp': False, '_pair': 'p', '_filter': 'Lin-Wu Chen'},
            {'Lineup': 'Chen-Liu', 'Min': '', '+/-': '', '_opp': True, '_pair': 'p', '_filter': 'Lin-Wu Chen'},
        ]
        with patch.object(team_stats_page, 'rotation_games', return_value=source), \
                patch.object(team_stats_page, 'season_matchup_records', return_value=records):
            view = team_stats_page.render_team_matchups(
                'tab-matchups', {'ok': True}, 'aces', 'all', 'all', 'all',
                'PLG', 's', 'REGULAR', None,
            )
        paper = next(
            node for node in _walk(view)
            if getattr(node, 'className', None) == 'braves-grid-wrap'
        )
        grid = next(node for node in _walk(paper) if getattr(node, 'id', None) == 'ts-matchup-grid')
        self.assertEqual(grid.rowData[1]['Lineup'], 'Chen-Liu')
        self.assertTrue(grid.dashGridOptions.get('pagination'))
        self.assertEqual(grid.dashGridOptions['paginationPageSize'], 40)
        self.assertIs(grid.dashGridOptions['paginationPageSizeSelector'], False)


def _svg(src):
    return base64.b64decode(src.split(',', 1)[1]).decode('utf-8')


class TeamStatsSortChromeTests(unittest.TestCase):
    def test_sort_store_is_memory_and_filters_clear_it(self):
        from dash import dcc

        layout = team_stats_page.layout()
        store = next(node for node in _walk(layout) if getattr(node, 'id', None) == 'ts-sort')
        self.assertIsInstance(store, dcc.Store)
        self.assertEqual(store.storage_type, 'memory')
        self.assertIsNone(store.data)
        listed = _callbacks('ts-sort.data')
        self.assertEqual(len(listed), 2)
        clear = next(
            item for item in listed
            if ('ts-intent', 'data') in _pairs(item['inputs'])
        )
        self.assertEqual(
            _pairs(clear['inputs']),
            [
                ('ts-intent', 'data'),
                ('ts-team', 'value'),
                ('ts-opponent', 'value'),
                ('ts-stadium', 'value'),
                ('ts-site', 'value'),
            ],
        )
        self.assertNotIn('ts-period', {item['id'] for item in clear['inputs']})
        self.assertNotIn('ts-show-opp', {item['id'] for item in clear['inputs']})
        self.assertIsNone(team_stats_page.clear_team_stats_sort(None, None, None, None, None))

    def test_leaf_headers_are_buttons_and_group_labels_are_not(self):
        from dash import html

        paper = team_stats_page._paper({
            'id': 'team',
            'columns': ['Team', 'GP', 'Min', '2M', '2A', '2FG%', 'PTS'],
            'rows': [],
            'opp_rows': [],
        }, {'column': 'PTS', 'direction': 'desc'})
        headers = [th for th in _walk(paper) if isinstance(th, dmc.TableTh)]
        buttons = [node for node in _walk(paper) if isinstance(node, html.Button)]
        labels = []
        for button in buttons:
            text = next(child for child in button.children if isinstance(child, str))
            labels.append((button.id['column'], text, button.className))
        self.assertIn(('PTS', 'PT', 'ts-sort-hit is-desc'), labels)
        self.assertIn(('2M', 'M', 'ts-sort-hit'), labels)
        self.assertIn(('Team', 'TEAM', 'ts-sort-hit'), labels)
        self.assertTrue(any(th.children == '2PT' for th in headers))
        plain = team_stats_page._header_rows('team', ['Team', 'PTS'])
        self.assertTrue(all(isinstance(th.children, str) for th in _walk(plain[0]) if isinstance(th, dmc.TableTh)))

    def test_period_keeps_sort_and_a_team_change_drops_it(self):
        payload = _payload()
        sort = {'column': 'PTS', 'direction': 'desc'}
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-period'), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload), \
                patch.object(team_stats_page, '_view', return_value='cards') as view:
            team_stats_page.render_team_stats(
                None, '1', 'all', 'all', 'all', 'all', 'PLG', 's', 'REGULAR', sort,
            )
        self.assertEqual(view.call_args.args[1], sort)
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-team'), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload), \
                patch.object(team_stats_page, '_view', return_value='cards') as view:
            team_stats_page.render_team_stats(
                None, 'all', 'all', 'all', 'all', 'aces', 'PLG', 's', 'REGULAR', sort,
            )
        self.assertIsNone(view.call_args.args[1])

    def test_header_click_sorts_from_the_cached_chip_path(self):
        payload = _payload()
        with patch.object(team_stats_page, 'ctx') as fake, \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, '_view', return_value='cards') as view:
            fake.triggered = [{'value': 0}]
            fake.triggered_id = {'type': 'ts-sort-th', 'card': 'team', 'column': 'PTS'}
            with self.assertRaises(PreventUpdate):
                team_stats_page.sort_team_stats_cards(
                    [0], {'column': 'PTS', 'direction': 'desc'},
                    'PLG', 's', 'REGULAR', '1', 'all', 'all', 'all', 'aces',
                )
            fake.triggered = [{'value': 1}]
            sort, body = team_stats_page.sort_team_stats_cards(
                [1], None, 'PLG', 's', 'REGULAR', '1', 'opp', 'gym', 'home', 'aces',
            )
        self.assertEqual(sort, {'column': 'PTS', 'direction': 'desc'})
        self.assertEqual(body, 'cards')
        self.assertEqual(fetch.call_args.kwargs['reason'], 'chip')
        self.assertEqual(fetch.call_args.kwargs['period'], '1')
        self.assertEqual(fetch.call_args.kwargs['team'], 'aces')
        self.assertEqual(view.call_args.args[1], sort)
        self.assertFalse(fetch.call_args.kwargs.get('force', False))
