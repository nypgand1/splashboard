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
