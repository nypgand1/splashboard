import json
import unittest
from unittest.mock import patch

import dash_mantine_components as dmc
import pandas as pd
from dash import no_update
from dash._callback import GLOBAL_CALLBACK_LIST

import app  # noqa: F401
from pages import game as game_page
from synergy_reporter.matchups import build_matchup_payload, matchup_grid_records
from synergy_reporter.post_game_report import PostGameReport
from tests.test_dmc_ui import find_type, walk
from ui_kit import EMPTY_GAME_NEXT, EMPTY_MATCHUPS, ERROR_GAME

HOME = 'home'
AWAY = 'away'
HOME_IDS = ('h1', 'h2', 'h3', 'h4', 'h5')
AWAY_IDS = ('a1', 'a2', 'a3', 'a4', 'a5')


def _names():
    return {
        'h1': 'Lin', 'h2': 'Wu', 'h3': 'Ho', 'h4': 'Kuo', 'h5': 'Yeh',
        'a1': 'Chen', 'a2': 'Liu', 'a3': 'Chang', 'a4': 'Wang', 'a5': 'Chou',
    }


def _shirts():
    return {
        'h1': 7, 'h2': 1, 'h3': 4, 'h4': 11, 'h5': 3,
        'a1': 10, 'a2': 8, 'a3': 12, 'a4': 9, 'a5': 15,
    }


def _row(period, clock, event, entity=None, success=0, subtype=None, home=None, away=None, options=None):
    return {
        'periodId': period,
        'clock': clock,
        'eventType': event,
        'entityId': entity,
        'subType': subtype,
        'success': success,
        'options': options,
        HOME: list(HOME_IDS if home is None else home),
        AWAY: list(AWAY_IDS if away is None else away),
    }


def _shared_frame():
    home = ['h4', 'h1', 'h5', 'h2', 'h3']
    away = ['a5', 'a3', 'a1', 'a4', 'a2']
    return pd.DataFrame([
        _row(1, 'PT10M00S', 'jumpBall', entity=HOME, subtype='won', home=home, away=away),
        _row(1, 'PT09M00S', '2pt', entity=HOME, success=1, subtype='layup', home=home, away=away,
             options={'pointsInThePaint': True}),
        _row(1, 'PT09M00S', 'assist', entity=HOME, home=home, away=away),
        _row(1, 'PT09M00S', 'rebound', entity=AWAY, subtype='defensive', home=home, away=away),
        _row(1, 'PT09M00S', 'turnover', entity=AWAY, home=home, away=away),
        _row(1, 'PT09M00S', 'steal', entity=HOME, home=home, away=away),
        _row(1, 'PT09M00S', 'block', entity=HOME, home=home, away=away),
        _row(1, 'PT09M00S', 'foul', entity=HOME, subtype='personal', home=home, away=away),
        _row(1, 'PT09M00S', 'foul', entity=AWAY, subtype='drawn', home=home, away=away),
        _row(1, 'PT09M00S', 'period', subtype='end', home=home, away=away),
    ])


class MatchupAggregateTests(unittest.TestCase):
    def test_shared_fives_sum_the_overlap_and_order_names_by_jersey(self):
        payload = build_matchup_payload(_shared_frame(), HOME, AWAY, _names(), _shirts())
        self.assertEqual(len(payload['pairs']), 1)
        pair = payload['pairs'][0]
        self.assertEqual(pair['id'], 'h1,h2,h3,h4,h5|a1,a2,a3,a4,a5')
        self.assertEqual(pair['duration'], 60)
        self.assertEqual(pair['home_name'], 'Wu-Yeh-Ho-Lin-Kuo')
        self.assertEqual(pair['away_name'], 'Liu-Wang-Chen-Chang-Chou')

    def test_same_team_short_label_keeps_the_suffix_when_the_twin_sits(self):
        names = _names()
        names['h6'] = 'Lin'
        names['a1'] = 'Lin'
        shirts = _shirts()
        shirts['h6'] = 20
        payload = build_matchup_payload(
            _shared_frame(), HOME, AWAY, names, shirts,
            team_people={HOME: list(HOME_IDS) + ['h6'], AWAY: list(AWAY_IDS)},
        )
        pair = payload['pairs'][0]
        self.assertEqual(pair['home_name'], 'Wu-Yeh-Ho-Lin#7-Kuo')
        self.assertEqual(pair['away_name'], 'Liu-Wang-Lin-Chang-Chou')
        self.assertEqual(pair['home']['PTS'], 2)
        self.assertEqual(pair['home']['2M'], 1)
        self.assertEqual(pair['home']['2A'], 1)
        self.assertEqual(pair['home']['POSS'], 1)
        self.assertEqual(pair['home']['PIP'], 2)
        self.assertEqual(pair['home']['AST'], 1)
        self.assertEqual(pair['home']['STL'], 1)
        self.assertEqual(pair['home']['BLK'], 1)
        self.assertEqual(pair['home']['PF'], 1)
        self.assertEqual(pair['away']['PTS'], 0)
        self.assertEqual(pair['away']['POSS'], 1)
        self.assertEqual(pair['away']['DR'], 1)
        self.assertEqual(pair['away']['REB'], 1)
        self.assertEqual(pair['away']['TOV'], 1)
        self.assertEqual(pair['away']['FD'], 1)

    def test_short_handed_stretch_is_left_out(self):
        short = ['h1', 'h2', 'h3', 'h4']
        frame = pd.DataFrame([
            _row(1, 'PT10M00S', '2pt', entity=HOME, success=1, home=short),
            _row(1, 'PT09M00S', 'jumpBall', entity=HOME, subtype='won'),
            _row(1, 'PT08M30S', 'period', subtype='end'),
        ])
        payload = build_matchup_payload(frame, HOME, AWAY, _names(), _shirts())
        self.assertEqual(len(payload['pairs']), 1)
        pair = payload['pairs'][0]
        self.assertEqual(pair['duration'], 30)
        self.assertEqual(pair['home']['PTS'], 0)
        self.assertEqual(pair['home']['2M'], 0)

    def test_same_fives_sum_across_periods(self):
        frame = pd.DataFrame([
            _row(1, 'PT10M00S', 'jumpBall', entity=HOME, subtype='won'),
            _row(1, 'PT09M00S', 'period', subtype='end'),
            _row(2, 'PT05M00S', '3pt', entity=AWAY, success=1),
            _row(2, 'PT04M30S', 'period', subtype='end'),
        ])
        payload = build_matchup_payload(frame, HOME, AWAY, _names(), _shirts())
        self.assertEqual(len(payload['pairs']), 1)
        pair = payload['pairs'][0]
        self.assertEqual(pair['duration'], 90)
        self.assertEqual(pair['away']['PTS'], 3)
        self.assertEqual(pair['away']['3M'], 1)
        self.assertEqual(pair['home']['PTS'], 0)

    def test_different_opposing_five_stays_a_separate_pair(self):
        other = ['a1', 'a2', 'a3', 'a4', 'a9']
        frame = pd.DataFrame([
            _row(1, 'PT10M00S', 'jumpBall', entity=HOME, subtype='won'),
            _row(1, 'PT09M30S', 'jumpBall', entity=AWAY, subtype='won', away=other),
            _row(1, 'PT09M00S', 'period', subtype='end', away=other),
        ])
        payload = build_matchup_payload(frame, HOME, AWAY, _names(), _shirts())
        self.assertEqual(len(payload['pairs']), 2)
        durations = sorted(pair['duration'] for pair in payload['pairs'])
        self.assertEqual(durations, [30, 30])

    def test_zero_overlap_is_omitted(self):
        frame = pd.DataFrame([
            _row(1, 'PT10M00S', '2pt', entity=HOME, success=1),
            _row(2, 'PT10M00S', 'period', subtype='start'),
        ])
        payload = build_matchup_payload(frame, HOME, AWAY, _names(), _shirts())
        self.assertEqual(payload['pairs'], [])


class MatchupViewpointTests(unittest.TestCase):
    def _rows(self, viewpoint):
        payload = build_matchup_payload(_shared_frame(), HOME, AWAY, _names(), _shirts())
        return matchup_grid_records(payload, viewpoint)

    def test_away_is_the_default_top_row(self):
        rows = self._rows(None)
        self.assertEqual(len(rows), 2)
        top, other = rows
        self.assertEqual(top['Lineup'], 'Liu-Wang-Chen-Chang-Chou')
        self.assertFalse(top['_opp'])
        self.assertEqual(top['Min'], '1:00')
        self.assertEqual(top['+/-'], -2)
        self.assertEqual(top['PPP'], '0.00')
        self.assertEqual(top['PTS'], '')
        self.assertEqual(top['TO'], 1)
        self.assertEqual(other['Lineup'], 'Wu-Yeh-Ho-Lin-Kuo')
        self.assertNotEqual(other['Lineup'], 'Opp')
        self.assertTrue(other['_opp'])
        self.assertEqual(other['Min'], '')
        self.assertEqual(other['+/-'], '')
        self.assertEqual(other['PTS'], 2)
        self.assertEqual(other['2FG%'], '1.000')
        self.assertEqual(other['PPP'], '2.00')
        self.assertEqual(other['PIP'], 2)
        self.assertEqual(top['_own'], other['_own'])
        self.assertIn('Wu-Yeh-Ho-Lin-Kuo', top['_filter'])
        self.assertIn('Liu-Wang-Chen-Chang-Chou', other['_filter'])
        self.assertEqual(top['_own']['+/-'], -2)
        self.assertEqual(top['_own']['Lineup'], top['Lineup'])

    def test_home_viewpoint_flips_the_top_row_and_the_sign(self):
        rows = self._rows(HOME)
        top, other = rows
        self.assertEqual(top['Lineup'], 'Wu-Yeh-Ho-Lin-Kuo')
        self.assertEqual(top['+/-'], 2)
        self.assertEqual(top['PTS'], 2)
        self.assertEqual(top['Min'], '1:00')
        self.assertEqual(other['Lineup'], 'Liu-Wang-Chen-Chang-Chou')
        self.assertEqual(other['Min'], '')
        self.assertEqual(other['+/-'], '')
        self.assertEqual(other['PPP'], '0.00')
        self.assertEqual(top['_own']['+/-'], 2)

    def test_sort_uses_the_viewpoint_plus_minus_then_the_viewpoint_name(self):
        payload = {
            'home_id': HOME,
            'away_id': AWAY,
            'pairs': [
                {'id': 'b', 'home_name': 'H1', 'away_name': 'B', 'duration': 60,
                 'home': {'PTS': 0}, 'away': {'PTS': 1}},
                {'id': 'a', 'home_name': 'H2', 'away_name': 'A', 'duration': 60,
                 'home': {'PTS': 0}, 'away': {'PTS': 1}},
                {'id': 'z', 'home_name': 'H3', 'away_name': 'Z', 'duration': 60,
                 'home': {'PTS': 0}, 'away': {'PTS': 4}},
            ],
        }
        away_names = [row['Lineup'] for row in matchup_grid_records(payload, AWAY) if not row['_opp']]
        self.assertEqual(away_names, ['Z', 'A', 'B'])
        home_names = [row['Lineup'] for row in matchup_grid_records(payload, HOME) if not row['_opp']]
        self.assertEqual(home_names, ['H1', 'H2', 'H3'])

    def test_ties_break_on_ppp_then_minutes_then_name(self):
        def side(pts, poss):
            return {'PTS': pts, 'POSS': poss}

        payload = {
            'home_id': HOME,
            'away_id': AWAY,
            'pairs': [
                {'id': 'long-low', 'home_name': 'H', 'away_name': 'B', 'duration': 90,
                 'home': side(0, 0), 'away': side(2, 1)},
                {'id': 'short-high', 'home_name': 'H', 'away_name': 'A', 'duration': 30,
                 'home': side(0, 0), 'away': side(4, 1)},
                {'id': 'long-high', 'home_name': 'H', 'away_name': 'C', 'duration': 120,
                 'home': side(0, 0), 'away': side(4, 1)},
                {'id': 'blank', 'home_name': 'H', 'away_name': 'D', 'duration': 400,
                 'home': side(0, 0), 'away': side(0, 0)},
                {'id': 'better', 'home_name': 'H', 'away_name': 'E', 'duration': 10,
                 'home': side(0, 1), 'away': side(9, 1)},
            ],
        }
        names = [row['Lineup'] for row in matchup_grid_records(payload, AWAY) if not row['_opp']]
        self.assertEqual(names, ['E', 'C', 'A', 'B', 'D'])


class MatchupReportTests(unittest.TestCase):
    def test_report_reads_on_court_lists_from_starters(self):
        report = PostGameReport.__new__(PostGameReport)
        report.playbyplay_df = pd.DataFrame([
            {'periodId': 1, 'clock': 'PT10M00S', 'eventType': 'jumpBall', 'entityId': HOME,
             'subType': 'won', 'success': 0, 'personId': None},
            {'periodId': 1, 'clock': 'PT09M00S', 'eventType': '2pt', 'entityId': HOME,
             'subType': 'layup', 'success': 1, 'personId': 'h1'},
            {'periodId': 1, 'clock': 'PT09M00S', 'eventType': 'period', 'entityId': None,
             'subType': 'end', 'success': 0, 'personId': None},
        ])
        report.starter_dict = {HOME: list(HOME_IDS), AWAY: list(AWAY_IDS)}
        report.id_table = _names()
        report.roster = [
            {'personId': player_id, 'shirtNumber': _shirts()[player_id]}
            for player_id in HOME_IDS + AWAY_IDS
        ]
        report._matchup_payload = None
        payload = report.get_matchup_payload(HOME, AWAY)
        self.assertEqual(len(payload['pairs']), 1)
        self.assertEqual(payload['pairs'][0]['duration'], 60)
        self.assertEqual(payload['pairs'][0]['home']['PTS'], 2)
        self.assertEqual(payload['pairs'][0]['home_name'], 'Wu-Yeh-Ho-Lin-Kuo')

    def test_report_pool_includes_a_dnp_twin(self):
        report = PostGameReport.__new__(PostGameReport)
        report.playbyplay_df = pd.DataFrame([
            {'periodId': 1, 'clock': 'PT10M00S', 'eventType': 'jumpBall', 'entityId': HOME,
             'subType': 'won', 'success': 0, 'personId': None},
            {'periodId': 1, 'clock': 'PT09M00S', 'eventType': 'period', 'entityId': None,
             'subType': 'end', 'success': 0, 'personId': None},
        ])
        report.starter_dict = {HOME: list(HOME_IDS), AWAY: list(AWAY_IDS)}
        report.id_table = _names()
        report.id_table['h6'] = 'Lin'
        report.roster = [
            {'personId': player_id, 'shirtNumber': _shirts()[player_id], 'entityId': HOME}
            for player_id in HOME_IDS
        ]
        report.roster.append({'personId': 'h6', 'shirtNumber': 20, 'entityId': HOME})
        report.roster.extend(
            {'personId': player_id, 'shirtNumber': _shirts()[player_id], 'entityId': AWAY}
            for player_id in AWAY_IDS
        )
        report._matchup_payload = None
        payload = report.get_matchup_payload(HOME, AWAY)
        self.assertEqual(payload['pairs'][0]['home_name'], 'Wu-Yeh-Ho-Lin#7-Kuo')
        self.assertEqual(payload['pairs'][0]['away_name'], 'Liu-Wang-Chen-Chang-Chou')


def _plain(node):
    if node is None or node is no_update:
        return ''
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return ' '.join(_plain(child) for child in node)
    return _plain(getattr(node, 'children', None))


def _output_entries(item):
    output = item['output']
    if isinstance(output, str):
        text = output
        if text.startswith('..') and text.endswith('..'):
            parts = text[2:-2].split('...')
        else:
            parts = [text]
    else:
        parts = []
        for entry in output:
            if isinstance(entry, str):
                parts.append(entry)
            elif isinstance(entry, dict):
                parts.append(f"{entry.get('id')}.{entry.get('property')}")
    entries = []
    for part in parts:
        ident, _, prop = part.rpartition('.')
        entries.append((ident, prop))
    return entries


def _callbacks_for(component_id, prop):
    found = []
    for item in GLOBAL_CALLBACK_LIST:
        if (component_id, prop) in _output_entries(item):
            found.append(item)
    return found


def _leaf_widths(column_defs):
    widths = {}
    for col in column_defs:
        children = col.get('children')
        if children:
            widths.update(_leaf_widths(children))
        elif col.get('field'):
            widths[col['field']] = col.get('width')
    return widths


def _field(column_defs, name):
    for col in column_defs:
        if col.get('field') == name:
            return col
        children = col.get('children')
        if children:
            found = _field(children, name)
            if found:
                return found
    return None


class MatchupTabTests(unittest.TestCase):
    def test_tab_sits_between_lineup_and_play_by_play(self):
        tree = game_page.layout('g1')
        tabs = find_type(tree, dmc.TabsTab)
        values = [tab.value for tab in tabs]
        self.assertEqual(
            values,
            ['tab-bs', 'tab-rotation', 'tab-shot-chart', 'tab-lineup', 'tab-matchups', 'tab-pbp', 'tab-report'],
        )
        matchups = next(tab for tab in tabs if tab.value == 'tab-matchups')
        self.assertEqual(matchups.children, 'Matchups')
        self.assertEqual(matchups.leftSection.icon, 'tabler:users-group')
        ids = {getattr(node, 'id', None) for node in walk(tree)}
        self.assertIn('matchup-team', ids)
        self.assertIn('matchup-grid', ids)
        self.assertIn('wrap-matchups', ids)
        segment = next(node for node in walk(tree) if getattr(node, 'id', None) == 'matchup-team')
        self.assertIsNot(getattr(segment, 'fullWidth', False), True)
        grid = next(node for node in walk(tree) if getattr(node, 'id', None) == 'matchup-grid')
        self.assertIn('braves-lineup-grid', grid.className)
        self.assertNotIn('pagination', grid.dashGridOptions)
        self.assertIn(':view', grid.getRowId)
        self.assertIn(':other', grid.getRowId)
        lineup = _field(grid.columnDefs, 'Lineup')
        plus = _field(grid.columnDefs, '+/-')
        minutes = _field(grid.columnDefs, 'Min')
        jersey_order = ['desc', 'asc', None]
        self.assertIsNone(lineup.get('sort'))
        self.assertIsNone(lineup.get('sortIndex'))
        self.assertIsNone(plus.get('sort'))
        self.assertIsNone(plus.get('sortIndex'))
        self.assertIsNone(lineup.get('sortingOrder'))
        self.assertEqual(plus.get('sortingOrder'), jersey_order)
        self.assertEqual(minutes.get('sortingOrder'), jersey_order)
        self.assertEqual(_field(grid.columnDefs, 'PPP').get('sortingOrder'), jersey_order)
        self.assertIn("indexOf(':')", minutes['comparator']['function'])
        self.assertIn('DNP', minutes['comparator']['function'])
        self.assertNotIn('valueGetter', lineup)
        self.assertIn('_filter', lineup['filterValueGetter']['function'])
        opp_style = lineup['cellStyle']['styleConditions'][0]['style']
        self.assertEqual(opp_style['textAlign'], 'right')
        self.assertEqual(opp_style['fontWeight'], '400')
        self.assertEqual(opp_style['color'], '#0f172a')
        self.assertEqual(lineup['cellStyle']['defaultStyle']['textAlign'], 'left')
        self.assertEqual(lineup['cellStyle']['defaultStyle']['fontWeight'], '700')
        self.assertEqual(
            lineup['cellClassRules']['ag-cell-align-left'],
            '!(params.data && params.data._opp)',
        )
        self.assertEqual(sum(_leaf_widths(grid.columnDefs).values()), 1022)
        self.assertNotIn('onGridSizeChanged', grid.dashGridOptions)
        self.assertEqual(
            grid.eventListeners['gridSizeChanged'],
            ['splashboardFitLineupWidth(params)'],
        )
        self.assertEqual(
            grid.eventListeners['firstDataRendered'],
            ['splashboardFitLineupWidth(params)'],
        )
        with open(game_page.__file__, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn("active_tab === 'tab-matchups'", source)

    def test_hidden_tab_does_not_rewrite_rows(self):
        rows, status, style = game_page.update_matchup_rows({'pairs': []}, 'away', 'tab-lineup')
        self.assertIs(rows, no_update)
        self.assertIs(status, no_update)
        self.assertIs(style, no_update)

    def test_empty_and_error_copy(self):
        rows, status, style = game_page.update_matchup_rows(
            {'home_id': HOME, 'away_id': AWAY, 'pairs': []},
            AWAY,
            'tab-matchups',
        )
        self.assertEqual(rows, [])
        self.assertEqual(style, {'display': 'none'})
        self.assertIn(EMPTY_MATCHUPS, _plain(status))
        self.assertIn(EMPTY_GAME_NEXT, _plain(status))

        rows, status, style = game_page.update_matchup_rows(
            {'_ui': 'error', 'message': ERROR_GAME},
            AWAY,
            'tab-matchups',
        )
        self.assertEqual(rows, [])
        self.assertTrue(find_type(status, dmc.Alert))
        self.assertIn(ERROR_GAME, _plain(status))

    def test_open_tab_paints_viewpoint_rows_without_touching_column_state(self):
        payload = build_matchup_payload(_shared_frame(), HOME, AWAY, _names(), _shirts())
        rows, status, style = game_page.update_matchup_rows(
            json.dumps(payload), None, 'tab-matchups',
        )
        self.assertEqual(style, {'display': 'block'})
        self.assertEqual(status, [])
        self.assertEqual(rows[0]['Lineup'], 'Liu-Wang-Chen-Chang-Chou')
        self.assertEqual(rows[1]['Lineup'], 'Wu-Yeh-Ho-Lin-Kuo')
        self.assertNotEqual(rows[1]['Lineup'], 'Opp')

        specs = _callbacks_for('matchup-grid', 'rowData')
        self.assertEqual(len(specs), 1)
        outputs = set(_output_entries(specs[0]))
        self.assertNotIn(('matchup-grid', 'columnState'), outputs)
        self.assertNotIn(('matchup-grid', 'filterModel'), outputs)
        self.assertNotIn(('matchup-grid', 'columnDefs'), outputs)
        inputs = {(item['id'], item['property']) for item in specs[0]['inputs']}
        self.assertIn(('matchup_store', 'data'), inputs)
        self.assertIn(('matchup-team', 'value'), inputs)
        self.assertIn(('tabs', 'value'), inputs)

        store_specs = _callbacks_for('matchup_store', 'data')
        self.assertEqual(len(store_specs), 1)
        store_inputs = {(item['id'], item['property']) for item in store_specs[0]['inputs']}
        self.assertIn(('interval-component', 'n_intervals'), store_inputs)
        self.assertIn(('game_id', 'children'), store_inputs)
        self.assertIn(('match_info_store', 'data'), store_inputs)
        self.assertNotIn(('tabs', 'value'), store_inputs)

    def test_live_match_info_keeps_a_valid_viewpoint(self):
        info = json.dumps({
            'away_team_id': 'a',
            'home_team_id': 'h',
            'away_team': 'Formosa Dreamers',
            'home_team': 'Taipei Fubon Braves',
        })
        options, value = game_page.sync_matchup_team(info, 'g1', 'h')
        self.assertIs(value, no_update)
        self.assertEqual([item['value'] for item in options], ['a', 'h'])
        self.assertEqual(
            [item['label'] for item in options],
            ['Formosa Dreamers', 'Taipei Fubon Braves'],
        )
        _options, fresh = game_page.sync_matchup_team(info, 'g1', None)
        self.assertEqual(fresh, 'a')
        self.assertEqual(game_page.matchup_team_value('h', 'a', 'h', 'game_id'), 'a')
        self.assertIs(game_page.matchup_team_value('h', 'a', 'h', 'match_info_store'), no_update)

    def test_store_asks_the_report_for_both_team_ids(self):
        class _Report:
            def get_matchup_payload(self, home_team_id=None, away_team_id=None):
                self.args = (home_team_id, away_team_id)
                return {'home_id': home_team_id, 'away_id': away_team_id, 'pairs': []}

        report = _Report()
        with patch.object(game_page, 'get_cached_report', return_value=report):
            raw = game_page.update_matchup_store(2, 'g1', json.dumps({
                'home_team_id': 'h',
                'away_team_id': 'a',
            }))
        self.assertEqual(report.args, ('h', 'a'))
        self.assertEqual(json.loads(raw)['pairs'], [])

        with patch.object(game_page, 'get_cached_report', side_effect=RuntimeError('boom')):
            raw = game_page.update_matchup_store(3, 'g1', json.dumps({
                'home_team_id': 'h',
                'away_team_id': 'a',
            }))
        self.assertEqual(json.loads(raw)['_ui'], 'error')
        self.assertEqual(json.loads(game_page.update_matchup_store(0, None, '{}')), {})
        with patch.object(game_page, 'get_cached_report') as cached:
            waiting = game_page.update_matchup_store(1, 'g1', '{}')
        cached.assert_not_called()
        self.assertEqual(json.loads(waiting), {})
