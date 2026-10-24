# -*- coding: utf-8 -*-
import unittest
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


class TeamStatsCallbackTests(unittest.TestCase):
    def test_skeleton_follows_intent_and_scope_only(self):
        listed = _callbacks('ts-body.children')
        clientside = [item for item in listed if item.get('clientside_function')]
        server = [item for item in listed if not item.get('clientside_function')]
        self.assertEqual(len(clientside), 1)
        self.assertEqual(len(server), 2)
        self.assertEqual(_pairs(clientside[0]['inputs']), [('ts-intent', 'data')])
        self.assertTrue(clientside[0]['prevent_initial_call'])
        self.assertNotIn('ts-league', {item['id'] for item in clientside[0]['inputs']})
        self.assertNotIn('ts-game-type', {item['id'] for item in clientside[0]['inputs']})
        self.assertNotIn('ts-period', {item['id'] for item in clientside[0]['inputs']})

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
        download = [item for item in server if 'ts-job.data' not in item['output']]
        self.assertEqual(len(render), 1)
        self.assertEqual(len(download), 1)
        self.assertEqual(
            _pairs(render[0]['inputs']),
            [('ts-intent', 'data'), ('ts-period', 'value')],
        )
        self.assertEqual(
            _pairs(render[0]['state']),
            [
                ('ts-league', 'value'),
                ('ts-season', 'value'),
                ('ts-game-type', 'value'),
            ],
        )
        self.assertIn('ts-applied.data', render[0]['output'])
        self.assertFalse(render[0]['prevent_initial_call'])
        self.assertEqual(_pairs(download[0]['inputs']), [('ts-job', 'data')])
        self.assertIn(('ts-intent', 'data'), _pairs(download[0]['state']))
        self.assertIn(('ts-period', 'value'), _pairs(download[0]['state']))
        self.assertIn('ts-applied.data', download[0]['output'])
        self.assertNotIn('ts-job.data', download[0]['output'])
        self.assertTrue(download[0]['prevent_initial_call'])


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
                intent, '1', 'EASL', 'plg-season', None,
            )
        self.assertEqual(fetch.call_args.kwargs['reason'], 'scope')
        self.assertIsNone(fetch.call_args.kwargs['game_type'])
        self.assertEqual(fetch.call_args.kwargs['period'], 'all')
        self.assertEqual(result[3], 'easl-season')
        self.assertEqual(result[5], 'REGULAR')
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[10], {
            'league': 'EASL',
            'season': 'easl-season',
            'game_type': 'REGULAR',
        })
        self.assertIs(result[11], no_update)

    def test_cached_game_type_swaps_cards_without_a_job(self):
        intent = {
            'league': 'PLG',
            'season': 's',
            'game_type': 'PLAYOFF',
            'skeleton': False,
            'nonce': 8,
        }
        payload = _payload('s', 'PLAYOFF')
        with patch.object(team_stats_page, 'type_needs_download', return_value=False), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, '_view', return_value='cards'):
            result = team_stats_page.render_team_stats(
                intent, '2', 'PLG', 's', 'PLAYOFF',
            )
        self.assertEqual(result[0], 'cards')
        self.assertEqual(fetch.call_args.kwargs['reason'], 'type')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'PLAYOFF')
        self.assertIs(result[5], no_update)
        self.assertEqual(result[8], 'all')
        self.assertEqual(result[10]['game_type'], 'PLAYOFF')
        self.assertIs(result[11], no_update)

    def test_missing_play_by_play_returns_the_skeleton_and_arms_the_job(self):
        intent = {
            'league': 'PLG',
            'season': 's',
            'game_type': 'PLAYOFF',
            'skeleton': False,
            'nonce': 9,
        }
        with patch.object(team_stats_page, 'type_needs_download', return_value=True), \
                patch.object(team_stats_page, 'team_stats_payload') as fetch:
            result = team_stats_page.render_team_stats(
                intent, '2', 'PLG', 's', 'PLAYOFF',
            )
        fetch.assert_not_called()
        self.assertIn('Skeleton', _names(result[0]))
        self.assertNotIn('Table', _names(result[0]))
        self.assertTrue(all(item is no_update for item in result[1:8]))
        self.assertEqual(result[8], 'all')
        self.assertIs(result[9], no_update)
        self.assertIs(result[10], no_update)
        self.assertEqual(result[11], intent)

    def test_period_chip_keeps_applied_and_does_not_arm_a_job(self):
        payload = _payload('s', 'REGULAR', '1')
        payload['period_chips'] = [
            {'label': 'All', 'value': 'all'},
            {'label': '1Q', 'value': '1'},
        ]
        with patch.object(team_stats_page, '_triggered_id', return_value='ts-period'), \
                patch.object(team_stats_page, 'team_stats_payload', return_value=payload) as fetch, \
                patch.object(team_stats_page, 'type_needs_download') as needs:
            result = team_stats_page.render_team_stats(
                {'skeleton': True, 'nonce': 1, 'game_type': None},
                '1',
                'PLG',
                's',
                'REGULAR',
            )
        needs.assert_not_called()
        self.assertEqual(fetch.call_args.kwargs['reason'], 'chip')
        self.assertEqual(fetch.call_args.kwargs['game_type'], 'REGULAR')
        self.assertEqual(fetch.call_args.kwargs['period'], '1')
        self.assertIs(result[8], no_update)
        self.assertIs(result[10], no_update)
        self.assertIs(result[11], no_update)

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
        self.assertEqual(len(result), 11)
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
            result = team_stats_page.render_team_stats(None, 'all', 'PLG', 's', 'REGULAR')
        self.assertEqual(result[0].title, 'Error')
        self.assertIn(ERROR_GAME, str(result[0].children))
        self.assertIsNone(result[5])
        self.assertEqual(result[10], {
            'league': 'PLG',
            'season': 's',
            'game_type': None,
        })
        self.assertIs(result[11], no_update)
        self.assertNotIn('secret', str(result[0]))
