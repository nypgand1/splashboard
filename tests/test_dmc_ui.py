import datetime
import json
import os
import unittest
from unittest.mock import patch

import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
from dash import no_update
from dash_iconify import DashIconify

import app  # noqa: F401
from pages import game as game_page
from pages import home as home_page
from ui_kit import (
    EMPTY_GAME,
    EMPTY_GAME_NEXT,
    EMPTY_HOME,
    EMPTY_HOME_FILTER,
    EMPTY_HOME_FILTER_NEXT,
    EMPTY_HOME_NEXT,
    ERROR_GAME,
    ERROR_HOME,
    game_banner,
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
            err, err_store = home_page.load_home_game_list('home-game-list')
        self.assertIs(err_store, no_update)
        alerts = find_type(err, dmc.Alert)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].children, ERROR_HOME)
        self.assertEqual(alerts[0].title, 'Error')
        self.assertEqual(_last_update_text(err), 'Last Update: —')
        self.assertEqual(_segmented(err, 'home-show').value, 'upcoming')
        self.assertFalse(_by_class(err, 'home-schedule-list'))
        self.assertFalse(_by_class(err, 'game-info-banner'))
        type_wrap = next(
            node for node in walk(err) if _node_id(node) == 'home-game-type-wrap'
        )
        self.assertEqual((type_wrap.style or {}).get('display'), 'none')

        fixed = datetime.datetime(
            2026, 10, 3, 15, 4, 5, 123456,
            tzinfo=datetime.timezone(datetime.timedelta(hours=8)),
        )

        class _Frozen(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        with patch.object(home_page, 'df_data', return_value=pd.DataFrame()), \
                patch.object(home_page.datetime, 'datetime', _Frozen):
            empty = home_page.load_home_game_list('home-game-list')
        markup = str(empty)
        self.assertIn(EMPTY_HOME, markup)
        self.assertIn(EMPTY_HOME_NEXT, markup)
        self.assertEqual(
            _last_update_text(empty),
            'Last Update: 2026-10-03 15:04:05.123456+08:00',
        )
        self.assertTrue(_by_class(empty, 'home-schedule-list'))
        self.assertIsNotNone(_segmented(empty, 'home-league'))
        self.assertFalse(find_type(empty, dmc.Alert))

    def test_home_layout_uses_skeleton(self):
        from dash import dcc

        layout = home_page.layout()
        self.assertTrue(find_type(layout, dmc.Skeleton))
        self.assertFalse(find_type(layout, dcc.Loading))
        host = next(node for node in walk(layout) if _node_id(node) == 'home-game-list')
        self.assertTrue(find_type(host, dmc.Skeleton))

    def test_home_layout_polls_and_keeps_filters_in_a_store(self):
        from dash import dcc
        from synergy_inbounder.runtime_cache import LIVE_CADENCE_SECONDS

        layout = home_page.layout()
        interval = next(node for node in walk(layout) if _node_id(node) == 'home-interval')
        self.assertIsInstance(interval, dcc.Interval)
        self.assertEqual(interval.interval, LIVE_CADENCE_SECONDS * 1000)
        store = next(node for node in walk(layout) if _node_id(node) == 'home-filter-store')
        self.assertEqual(store.data, home_page.initial_home_filters())
        scope = next(node for node in walk(layout) if _node_id(node) == 'home-scope-store')
        self.assertEqual(scope.data, home_page.initial_home_scope())

    def test_later_home_tick_keeps_filters_and_replaces_scores(self):
        first_df = _schedule_df([
            _home_row(
                status='FINISHED', fixtureId='done', fixtureType='REGULAR',
                home_team='Night', away_team='Day',
                teamScoreHome=80, teamScoreAway=70,
            ),
        ])
        second_df = _schedule_df([
            _home_row(
                status='FINISHED', fixtureId='done', fixtureType='REGULAR',
                home_team='Night', away_team='Day',
                teamScoreHome=99, teamScoreAway=70,
            ),
        ])
        frames = [first_df, second_df]
        calls = []

        def _df(prefetch=True, **_kwargs):
            calls.append(prefetch)
            return frames.pop(0)

        filters = {'show': 'all', 'game_type': 'REGULAR'}
        with patch.object(home_page, 'df_data', side_effect=_df):
            first = home_page.load_home_game_list(0, None, filters)
            second = home_page.load_home_game_list(1, None, filters)
        self.assertEqual(calls, [True, False])
        self.assertEqual(_segmented(first, 'home-show').value, 'results')
        self.assertEqual(_segmented(first, 'home-game-type').value, 'REGULAR')
        self.assertEqual(_segmented(second, 'home-show').value, 'all')
        self.assertEqual(_segmented(second, 'home-game-type').value, 'REGULAR')
        first_store = next(node for node in walk(first) if _node_id(node) == 'home-schedule-store')
        second_store = next(node for node in walk(second) if _node_id(node) == 'home-schedule-store')
        self.assertEqual(first_store.data[0]['score'], '70 : 80')
        self.assertEqual(second_store.data[0]['score'], '70 : 99')

    def test_later_home_tick_keeps_the_list_when_reload_fails(self):
        with patch.object(home_page, 'df_data', side_effect=RuntimeError('boom')):
            page, stored = home_page.load_home_game_list(1, None, {'show': 'results'})
        self.assertIs(page, no_update)
        self.assertIs(stored, no_update)

    def test_home_refresh_does_not_prefetch(self):
        frame = pd.DataFrame([{
            'startTimeLocal': '2026-01-01T19:00:00',
            'status': 'SCHEDULED',
            'fixtureType': 'REGULAR',
            'fixtureId': 'g1',
            'venueId': 'v',
            'teamIdHome': 'h',
            'teamIdAway': 'a',
            'teamScoreHome': None,
            'teamScoreAway': None,
        }])
        with patch.object(home_page.Parser, 'parse_season_game_list_df', return_value=frame), \
                patch.object(home_page.Parser, 'parse_id_tables', return_value={'h': 'Home', 'a': 'Away', 'v': 'Arena'}), \
                patch('synergy_inbounder.runtime_cache.prefetch_latest_games') as prefetch:
            home_page.df_data(prefetch=False)
            prefetch.assert_not_called()
            home_page.df_data(prefetch=True)
            prefetch.assert_called_once()

    def test_remember_home_filters(self):
        stored = home_page.initial_home_filters()
        data, scope = home_page.apply_home_filters(
            'results', 'PLAYOFF', 'PLG', stored['seasons']['PLG'], stored, 'home-show',
        )
        self.assertIsNone(scope)
        self.assertEqual(data['show'], 'results')
        self.assertEqual(data['game_type'], 'PLAYOFF')
        self.assertEqual(data['seasons'], stored['seasons'])

        data, scope = home_page.apply_home_filters(
            None, None, 'PLG', stored['seasons']['PLG'], stored, 'home-game-type',
        )
        self.assertIsNone(scope)
        self.assertEqual(data['show'], 'upcoming')
        self.assertIsNone(data['game_type'])

        chosen, scope = home_page.apply_home_filters(
            'upcoming', 'PLAYOFF', 'PLG', stored['seasons']['PLG'],
            {'show': 'upcoming', 'game_type': 'REGULAR'}, 'home-game-type',
        )
        self.assertIsNone(scope)
        self.assertEqual(chosen['show'], 'upcoming')
        self.assertEqual(chosen['game_type'], 'PLAYOFF')

        staged = dict(stored)
        staged['show'] = 'results'
        staged['game_type'] = 'PLAYOFF'
        data, scope = home_page.apply_home_filters(
            'upcoming', 'PLAYOFF', 'PLG', stored['seasons']['PLG'], staged, 'home-show',
        )
        self.assertIsNone(scope)
        self.assertEqual(data['show'], 'upcoming')
        self.assertEqual(data['game_type'], 'PLAYOFF')

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

    def test_rotation_success_wraps_full_width_paper(self):
        payload = {
            'periods': [{'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0}],
            'buckets': [
                {'periodId': 1, 'period_label': '1Q', 'minute': 0, 'label': '1Q', 'start': 0.0, 'end': 60.0},
                {'periodId': 1, 'period_label': '1Q', 'minute': 1, 'label': '1Q', 'start': 60.0, 'end': 120.0},
            ],
            'teams': [
                {
                    'team_id': 'h',
                    'team_name': 'Home',
                    'side': 'home',
                    'players': [{'label': 'A', 'cells': [1, None]}],
                },
                {
                    'team_id': 'a',
                    'team_name': 'Away',
                    'side': 'away',
                    'players': [{'label': 'B', 'cells': [None, 1]}],
                },
            ],
            'margin': [{'t': 0.0, 'margin': 0}, {'t': 120.0, 'margin': 4}],
            'scoring': {'home': [1, 12], 'away': [None, 2]},
        }
        tree = game_page.render_rotation_children(json.dumps(payload))
        self.assertFalse(find_type(tree, dmc.Paper))
        self.assertNotIn('Last Update', str(tree))
        fig, graph_style, paper_style = game_page.update_rotation_graph(
            json.dumps(payload), {}, 'tab-rotation',
        )
        self.assertIn(fig.layout.dragmode, ('pan', False))
        self.assertEqual(graph_style.get('width'), '100%')
        self.assertTrue(graph_style.get('height', '').endswith('px'))
        self.assertEqual(paper_style.get('overflow'), 'hidden')
        self.assertNotEqual(paper_style.get('display'), 'none')

    def test_rotation_callback_hosts_live_in_page_layout(self):
        tree = game_page.layout('g1')
        ids = {getattr(node, 'id', None) for node in walk(tree)}
        self.assertIn('rotation-period', ids)
        self.assertIn('rotation-show-dnp', ids)
        self.assertIn('rotation-graph', ids)
        self.assertIn('rotation-graph-paper', ids)
        self.assertIn('rotation-live', ids)
        self.assertIn('rotation-last-update', ids)
        self.assertIn('rotation-click-t', ids)
        wrap = next(node for node in walk(tree) if getattr(node, 'id', None) == 'wrap-rotation')
        self.assertEqual(getattr(wrap.children[0], 'id', None), 'rotation-last-update')
        self.assertIn('Last Update', str(wrap.children[0]))
        self.assertTrue(find_type(tree, dmc.SegmentedControl))
        switches = [node for node in find_type(tree, dmc.Switch) if node.id == 'rotation-show-dnp']
        self.assertEqual(switches[0].label, 'Show DNP')
        graphs = [node for node in walk(tree) if getattr(node, '_type', None) == 'Graph'
                  or node.__class__.__name__ == 'Graph']
        rotation_graph = next(node for node in graphs if getattr(node, 'id', None) == 'rotation-graph')
        self.assertTrue(rotation_graph.config.get('responsive'))
        self.assertFalse(rotation_graph.config.get('displayModeBar'))
        self.assertFalse(rotation_graph.config.get('scrollZoom'))
        self.assertFalse(rotation_graph.config.get('doubleClick'))
        self.assertNotEqual(getattr(rotation_graph, 'className', None), 'braves-table-scroll')

    def test_lineup_wrap_puts_last_update_above_size_control(self):
        tree = game_page.layout('g1')
        wrap = next(node for node in walk(tree) if getattr(node, 'id', None) == 'wrap-lineup')
        self.assertEqual(getattr(wrap.children[0], 'id', None), 'lineup-last-update')
        self.assertIn('Last Update', str(wrap.children[0]))
        markup = str(wrap)
        self.assertNotIn('Combination', markup)
        self.assertNotIn('COMBINATION', markup)
        self.assertIn('5 Players', markup)
        self.assertIn('4 Players', markup)
        self.assertIn('3 Players', markup)
        self.assertIn('2 Players', markup)
        ids = {getattr(node, 'id', None) for node in walk(wrap)}
        self.assertIn('lineup_size_dropdown', ids)
        self.assertIn('lineup-show-opp', ids)
        self.assertNotIn('lineup_dropdown_container', ids)
        control = next(
            node for node in walk(wrap)
            if getattr(node, 'id', None) == 'lineup_size_dropdown'
        )
        self.assertFalse(bool(getattr(control, 'fullWidth', False)))
        switch = next(node for node in walk(wrap) if getattr(node, 'id', None) == 'lineup-show-opp')
        self.assertIsInstance(switch, dmc.Switch)
        self.assertEqual(switch.label, 'Show Opp')
        self.assertEqual(switch.size, 'sm')
        self.assertEqual(switch.color, 'gray')
        self.assertFalse(bool(switch.checked))
        self.assertEqual(switch.ms, 'auto')
        row = next(
            node for node in walk(wrap)
            if isinstance(node, dmc.Group)
            and any(getattr(child, 'id', None) == 'lineup_size_dropdown' for child in (node.children or []))
            and any(getattr(child, 'id', None) == 'lineup-show-opp' for child in (node.children or []))
        )
        self.assertEqual(row.w, '100%')

    def test_lineup_size_four_uses_same_chrome_and_paginates(self):
        teams = ['Taipei Fubon Braves', 'Formosa Dreamers']

        def split_json(frame):
            return frame.to_json(orient='split')

        store = json.dumps({
            '5': {
                teams[0]: split_json(pd.DataFrame({'Lineup': ['A-B'], 'PTS': [10]})),
            },
            '4': {
                teams[0]: split_json(pd.DataFrame({'Lineup': ['A-B-C-D'], 'PTS': [10]})),
                teams[1]: split_json(pd.DataFrame({'Lineup': ['E-F-G-H'], 'PTS': [8]})),
            },
        })
        tree = game_page.update_pane_lineup('4', 'tab-lineup', store, None)
        self.assertNotIn('Last Update', str(tree))
        self.assertFalse(any(isinstance(node, dmc.Title) for node in walk(tree)))
        dots = [
            node.style.get('backgroundColor')
            for node in walk(tree)
            if isinstance(node, dmc.Box) and isinstance(getattr(node, 'style', None), dict)
            and node.style.get('width') == '8px'
        ]
        self.assertEqual(dots, ['#00b4d8', '#94a3b8'])
        grids = find_type(tree, dag.AgGrid)
        self.assertEqual(len(grids), 2)
        for grid in grids:
            opts = grid.dashGridOptions
            self.assertTrue(opts.get('pagination'))
            self.assertEqual(opts.get('paginationPageSize'), 20)
            self.assertEqual(opts.get('isExternalFilterPresent'), {'function': 'true'})
            lineup_col = next(col for col in grid.columnDefs if col.get('field') == 'Lineup')
            self.assertTrue(lineup_col.get('filter'))
            self.assertEqual(lineup_col.get('minWidth'), 220)
            self.assertEqual(lineup_col.get('width'), 230)

        five = game_page.update_pane_lineup('5', 'tab-lineup', store, None)
        five_grids = find_type(five, dag.AgGrid)
        self.assertEqual(len(five_grids), 1)
        self.assertFalse(five_grids[0].dashGridOptions.get('pagination'))
        shown = game_page.update_pane_lineup('4', 'tab-lineup', store, None, True)
        shown_grids = find_type(shown, dag.AgGrid)
        self.assertEqual(shown_grids[0].dashGridOptions.get('paginationPageSize'), 40)
        self.assertEqual(
            shown_grids[0].dashGridOptions.get('isExternalFilterPresent'),
            {'function': 'false'},
        )
        five_on = game_page.update_pane_lineup('5', 'tab-lineup', store, None, True)
        self.assertFalse(find_type(five_on, dag.AgGrid)[0].dashGridOptions.get('pagination'))

    def test_lineup_missing_size_uses_render_path_not_title(self):
        teams = ['Home', 'Away']

        def split_json(frame):
            return frame.to_json(orient='split')

        store = json.dumps({
            '5': {teams[0]: split_json(pd.DataFrame({'Lineup': ['A'], 'PTS': [1]}))},
        })
        custom = {
            teams[0]: split_json(pd.DataFrame({'Lineup': ['A-B-C-D'], 'PTS': [4]})),
            teams[1]: split_json(pd.DataFrame({'Lineup': ['E-F-G-H'], 'PTS': [2]})),
        }

        class FakeReport:
            def get_lineup_stats_json_dict(self, lineup_size=5):
                self.size = lineup_size
                return custom

        fake = FakeReport()
        with patch.object(game_page, 'get_cached_report', return_value=fake):
            tree = game_page.update_pane_lineup('4', 'tab-lineup', store, 'g1')
        self.assertEqual(fake.size, 4)
        self.assertFalse(any(isinstance(node, dmc.Title) for node in walk(tree)))
        self.assertNotIn('Last Update', str(tree))
        dots = [
            node.style.get('backgroundColor')
            for node in walk(tree)
            if isinstance(node, dmc.Box) and isinstance(getattr(node, 'style', None), dict)
            and node.style.get('width') == '8px'
        ]
        self.assertEqual(dots, ['#00b4d8', '#94a3b8'])
        grids = find_type(tree, dag.AgGrid)
        self.assertEqual(len(grids), 2)
        self.assertEqual(grids[0].dashGridOptions.get('paginationPageSize'), 20)
        self.assertEqual(grids[0].id, 'lineup-grid-0')
        lineup_col = next(col for col in grids[0].columnDefs if col.get('field') == 'Lineup')
        self.assertTrue(lineup_col.get('filter'))
        self.assertEqual(lineup_col.get('minWidth'), 220)

    def test_lineup_tab_pairs_each_lineup_with_an_opp_row(self):
        store = json.dumps({
            '4': {
                'Braves': pd.DataFrame([{
                    'Lineup': 'A-B-C-D',
                    'Min': '5:00',
                    '+/-': 0,
                    'PTS': 2,
                    'PPP': '1.00',
                    'Opp_PTS': 4,
                    'Opp_PPP': '2.00',
                    'Opp_Min': 'should-not-show',
                }]).to_json(orient='split'),
            },
        })
        tree = game_page.render_lineup_children(store, lineup_size=4)
        grids = find_type(tree, dag.AgGrid)
        self.assertEqual(len(grids), 1)
        grid = grids[0]
        self.assertEqual(grid.id, 'lineup-grid-0')
        self.assertEqual(grid.dashGridOptions.get('paginationPageSize'), 20)
        self.assertEqual(grid.dashGridOptions['isExternalFilterPresent']['function'], 'true')
        self.assertIn(
            'params && params.data && params.data._opp',
            grid.dashGridOptions['doesExternalFilterPass']['function'],
        )
        shown = find_type(
            game_page.render_lineup_children(store, lineup_size=4, show_opp=True),
            dag.AgGrid,
        )[0]
        self.assertEqual(shown.dashGridOptions.get('paginationPageSize'), 40)
        self.assertEqual(shown.dashGridOptions['isExternalFilterPresent']['function'], 'false')
        fields = []

        def collect(cols):
            for col in cols:
                if col.get('children'):
                    collect(col['children'])
                elif col.get('field'):
                    fields.append(col['field'])

        collect(grid.columnDefs)
        self.assertNotIn('Opp_PTS', fields)
        self.assertNotIn('Opp_Min', fields)
        self.assertEqual([row['Lineup'] for row in grid.rowData], ['A-B-C-D', 'A-B-C-D'])
        our, opp = grid.rowData
        self.assertFalse(our['_opp'])
        self.assertTrue(opp['_opp'])
        self.assertEqual(opp['_pair'], 'A-B-C-D')
        self.assertEqual(opp['PTS'], 4)
        self.assertEqual(opp['PPP'], '2.00')
        self.assertEqual(opp['Min'], '')
        self.assertEqual(opp['+/-'], '')
        self.assertEqual(our['_own']['PTS'], 2)
        self.assertEqual(opp['_own']['PTS'], 2)
        lineup_col = next(col for col in grid.columnDefs if col.get('field') == 'Lineup')
        self.assertNotIn('cellClass', lineup_col)
        self.assertIn('ag-cell-align-right', lineup_col['cellClassRules'])
        self.assertEqual(
            lineup_col['cellStyle']['styleConditions'][0]['style']['textAlign'],
            'right',
        )
        self.assertEqual(lineup_col['cellStyle']['styleConditions'][0]['style']['color'], '#0f172a')
        self.assertEqual(lineup_col['cellStyle']['styleConditions'][0]['style']['fontWeight'], '400')
        self.assertEqual(lineup_col['cellStyle']['defaultStyle']['textAlign'], 'center')
        self.assertEqual(lineup_col['cellStyle']['defaultStyle']['fontWeight'], '700')
        self.assertIsNone(lineup_col.get('sortingOrder'))
        self.assertIsNone(lineup_col.get('sort'))
        plus = next(col for col in grid.columnDefs if col.get('field') == '+/-')
        minutes = next(col for col in grid.columnDefs if col.get('field') == 'Min')
        self.assertEqual(plus.get('sortingOrder'), ['desc', 'asc', None])
        self.assertEqual(minutes.get('sortingOrder'), ['desc', 'asc', None])
        self.assertIn("indexOf(':')", minutes['comparator']['function'])
        self.assertIsNone(plus.get('sort'))
        self.assertIn("'Opp'", lineup_col['valueGetter']['function'])
        self.assertIn('params.data["Lineup"]', lineup_col['filterValueGetter']['function'])
        self.assertIn('_own', lineup_col['comparator']['function'])
        self.assertIn('_opp', grid.dashGridOptions['postSortRows']['function'])
        self.assertNotIn('_opp', lineup_col['comparator']['function'])
        self.assertEqual(grid.getRowStyle['styleConditions'][0]['style']['backgroundColor'], '#f1f5f9')
        self.assertEqual(grid.getRowStyle['defaultStyle']['backgroundColor'], '#ffffff')
        self.assertIn(':opp', grid.getRowId)
        self.assertEqual(grid.rowClassRules['lineup-opp-row'], 'params.data && params.data._opp')

    def test_same_lineup_label_with_different_keys_keeps_two_row_ids(self):
        frame = pd.DataFrame([
            {
                'Lineup': 'A-B-C-D-E',
                'Min': '14:13',
                'PTS': 26,
                '_lineup_key': 'p1|p2|p3|p4|p5',
            },
            {
                'Lineup': 'A-B-C-D-E',
                'Min': '5:23',
                'PTS': 9,
                '_lineup_key': 'p2|p3|p4|p5|p9',
            },
        ])
        records = game_page._lineup_pair_records(frame)
        ours = [row for row in records if not row['_opp']]
        opps = [row for row in records if row['_opp']]
        self.assertEqual([row['Lineup'] for row in ours], ['A-B-C-D-E', 'A-B-C-D-E'])
        self.assertEqual([row['Lineup'] for row in opps], ['A-B-C-D-E', 'A-B-C-D-E'])
        self.assertEqual(
            [row['_pair'] for row in ours],
            ['p1|p2|p3|p4|p5', 'p2|p3|p4|p5|p9'],
        )
        self.assertEqual([row['_pair'] for row in opps], [row['_pair'] for row in ours])
        self.assertNotIn('_lineup_key', ours[0])
        self.assertNotIn('_lineup_key', opps[0])

    def test_game_change_turns_show_opp_off(self):
        self.assertIs(game_page.reset_lineup_show_opp('next-game'), False)

    def test_rotation_run_buttons_use_short_clock_label(self):
        payload = {
            'periods': [{'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0}],
            'teams': [
                {'team_id': 'h', 'team_name': 'Home', 'side': 'home', 'players': [{'label': 'A'}]},
                {'team_id': 'a', 'team_name': 'Away', 'side': 'away', 'players': [{'label': 'B'}]},
            ],
            'margin': [{'t': 0.0, 'margin': 0}],
            'runs': [{'side': 'home', 'home_pts': 10, 'away_pts': 2, 'start': 0.0, 'end': 60.0, 'delta': 8}],
        }
        tree = game_page.render_rotation_children(json.dumps(payload))
        buttons = find_type(tree, dmc.Button)
        self.assertTrue(buttons)
        self.assertEqual(buttons[0].children, '1Q 02:00–01:00  10–2')
        self.assertEqual(buttons[0].id, {'type': 'rotation-run', 'index': 0})
        self.assertEqual(buttons[0].variant, 'light')

    def test_kills_do_not_become_chips(self):
        payload = {
            'periods': [{'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0}],
            'teams': [
                {'team_id': 'h', 'team_name': 'Home', 'side': 'home', 'players': [{'label': 'A'}]},
                {'team_id': 'a', 'team_name': 'Away', 'side': 'away', 'players': [{'label': 'B'}]},
            ],
            'runs': [{'side': 'home', 'home_pts': 10, 'away_pts': 2, 'start': 40.0, 'end': 80.0, 'delta': 8}],
            'kills': [
                {'side': 'away', 'stops': 4, 'start': 10.0, 'end': 30.0},
                {'side': 'home', 'stops': 3, 'start': 50.0, 'end': 90.0},
            ],
        }
        tree = game_page.render_rotation_children(json.dumps(payload))
        buttons = find_type(tree, dmc.Button)
        self.assertEqual(
            [button.children for button in buttons],
            ['1Q 01:20–00:40  10–2'],
        )
        self.assertEqual(buttons[0].id, {'type': 'rotation-run', 'index': 0})
        self.assertEqual(buttons[0].variant, 'light')


def _schedule_df(rows):
    return pd.DataFrame(rows)


def _home_row(**kwargs):
    status = kwargs.pop('status', kwargs.pop('Status', 'SCHEDULED'))
    fixture_type = kwargs.pop('fixtureType', kwargs.pop('Game Type', 'REGULAR'))
    start = kwargs.pop('startTimeLocal', kwargs.pop('Time', '2026-01-01T19:00:00'))
    home_team = kwargs.pop('home_team', kwargs.pop('Home Team', 'Braves'))
    away_team = kwargs.pop('away_team', kwargs.pop('Away Team', 'Dreamers'))
    row = {
        'Time': start,
        'startTimeLocal': start,
        'Status': status,
        'rawStatus': status,
        'status': status,
        'Game Type': fixture_type,
        'fixtureType': fixture_type,
        'Venue': 'Arena',
        'Home Team': home_team,
        'Away Team': away_team,
        'Score': '—',
        'fixtureId': 'g1',
        'teamScoreHome': None,
        'teamScoreAway': None,
        'statusBucket': 'unplayed',
        'scoreClickable': False,
    }
    row.update(kwargs)
    row['Time'] = row.get('startTimeLocal', start)
    row['Status'] = row.get('status', status)
    row['Game Type'] = row.get('fixtureType', fixture_type)
    return row


def _node_id(node):
    return getattr(node, 'id', None)


def _segmented(tree, control_id):
    for node in walk(tree):
        if isinstance(node, dmc.SegmentedControl) and _node_id(node) == control_id:
            return node
    return None


def _papers(tree):
    return find_type(tree, dmc.Paper)


def _last_update_text(tree):
    node = next(item for item in walk(tree) if _node_id(item) == 'home-last-update')
    return ''.join(_string_values(node))


def _anchors(tree):
    found = []
    for node in walk(tree):
        href = getattr(node, 'href', None)
        if href:
            found.append(node)
    return found


def _string_values(tree):
    values = []
    for node in walk(tree):
        children = getattr(node, 'children', None)
        if isinstance(children, str):
            values.append(children)
    return values


def _style(node):
    return getattr(node, 'style', None) or {}


def _by_class(tree, name):
    found = []
    for node in walk(tree):
        class_name = getattr(node, 'className', None) or ''
        if name in str(class_name).split():
            found.append(node)
    return found


class HomeScheduleTests(unittest.TestCase):
    def _load(self, rows):
        df = _schedule_df(rows)
        with patch.object(home_page, 'df_data', return_value=df), \
                patch(
                    'synergy_inbounder.communicator.Communicator.get_fixture_live_summary',
                    return_value={},
                ):
            return home_page.load_home_game_list('home-game-list')

    def test_success_is_not_ag_grid(self):
        tree = self._load([_home_row(status='FINISHED', fixtureId='g1')])
        self.assertFalse(find_type(tree, dag.AgGrid))
        self.assertTrue(_papers(tree))

    def test_live_game_is_in_the_list_and_empty_season_keeps_filters(self):
        live_upcoming = self._load([
            _home_row(
                status='SCHEDULED', fixtureId='up1',
                startTimeLocal='2026-03-02T19:00:00',
                away_team='Upcoming Away', home_team='Upcoming Home',
            ),
            _home_row(
                status='IN_PROGRESS', fixtureId='live1',
                startTimeLocal='2026-03-01T19:00:00',
                away_team='Live Away', home_team='Live Home',
                teamScoreHome=10, teamScoreAway=8, Score='10 : 8',
            ),
            _home_row(
                status='FINISHED', fixtureId='fin1',
                startTimeLocal='2026-02-01T19:00:00',
                away_team='Finished Away', home_team='Finished Home',
            ),
        ])
        self.assertFalse(_by_class(live_upcoming, 'game-info-banner'))
        listed = str(_by_class(live_upcoming, 'home-schedule-list')[0])
        self.assertIn('Live Away', listed)
        self.assertIn('Live Home', listed)
        self.assertIn('Upcoming Away', listed)
        self.assertNotIn('Finished Away', listed)
        self.assertTrue(_last_update_text(live_upcoming).startswith('Last Update: '))
        self.assertNotEqual(_last_update_text(live_upcoming), 'Last Update: —')
        season = next(
            node for node in walk(live_upcoming) if _node_id(node) == 'home-season'
        )
        self.assertIs(season.searchable, False)
        self.assertIs(season.clearable, False)
        self.assertIs(season.allowDeselect, False)
        self.assertEqual(season.w, 132)

        empty = self._load([])
        markup = str(empty)
        self.assertIn(EMPTY_HOME, markup)
        self.assertIn(EMPTY_HOME_NEXT, markup)
        self.assertTrue(_by_class(empty, 'home-schedule-list'))
        self.assertIsNotNone(_segmented(empty, 'home-show'))
        self.assertFalse(_by_class(empty, 'game-info-banner'))

    def test_show_defaults_to_upcoming_and_game_type_from_live(self):
        tree = self._load([
            _home_row(status='FINISHED', fixtureType='PLAYOFF', fixtureId='f1',
                      startTimeLocal='2026-01-01T19:00:00'),
            _home_row(status='IN_PROGRESS', fixtureType='REGULAR', fixtureId='l1',
                      startTimeLocal='2026-01-02T19:00:00', Score='1 : 2',
                      teamScoreHome=1, teamScoreAway=2),
        ])
        show = _segmented(tree, 'home-show')
        game_type = _segmented(tree, 'home-game-type')
        self.assertIsNotNone(show)
        self.assertEqual(show.value, 'upcoming')
        self.assertEqual(
            [item['value'] for item in show.data],
            ['upcoming', 'results', 'all'],
        )
        self.assertEqual(game_type.value, 'REGULAR')

    def test_game_type_control_hidden_when_one_distinct_type(self):
        one = self._load([
            _home_row(status='SCHEDULED', fixtureType='REGULAR', fixtureId='g1'),
            _home_row(status='FINISHED', fixtureType='REGULAR', fixtureId='g2',
                      startTimeLocal='2026-01-02T19:00:00', Score='1 : 2'),
        ])
        wrap = next(
            node for node in walk(one)
            if _node_id(node) == 'home-game-type-wrap'
        )
        self.assertEqual((wrap.style or {}).get('display'), 'none')

        two = self._load([
            _home_row(status='SCHEDULED', fixtureType='REGULAR', fixtureId='g1'),
            _home_row(status='FINISHED', fixtureType='PLAYOFF', fixtureId='g2',
                      startTimeLocal='2026-01-02T19:00:00', Score='1 : 2'),
        ])
        wrap = next(
            node for node in walk(two)
            if _node_id(node) == 'home-game-type-wrap'
        )
        self.assertNotEqual((wrap.style or {}).get('display'), 'none')
        control = _segmented(two, 'home-game-type')
        self.assertEqual(
            [item['value'] for item in control.data],
            ['REGULAR', 'PLAYOFF'],
        )
        self.assertEqual(
            [item['label'] for item in control.data],
            ['Regular', 'Playoff'],
        )

    def test_upcoming_excludes_finished_and_void_all_includes_void(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(status='IN_PROGRESS', fixtureId='live', startTimeLocal='2026-01-03T19:00:00'),
            _home_row(status='SCHEDULED', fixtureId='up', startTimeLocal='2026-01-04T19:00:00'),
            _home_row(status='FINISHED', fixtureId='fin', startTimeLocal='2026-01-01T19:00:00'),
            _home_row(status='CANCELLED', fixtureId='void', startTimeLocal='2026-01-02T19:00:00'),
        ]))
        upcoming = home_page.filter_schedule_records(records, 'upcoming', None)
        self.assertEqual([row['fixtureId'] for row in upcoming], ['live', 'up'])
        finished = home_page.filter_schedule_records(records, 'results', None)
        self.assertEqual([row['fixtureId'] for row in finished], ['fin'])
        all_rows = home_page.filter_schedule_records(records, 'all', None)
        self.assertEqual([row['fixtureId'] for row in all_rows], ['up', 'live', 'void', 'fin'])

    def test_all_and_finished_put_the_later_same_day_game_first(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(status='FINISHED', fixtureId='early', startTimeLocal='2026-05-01T09:00:00'),
            _home_row(status='FINISHED', fixtureId='late', startTimeLocal='2026-05-01T21:00:00'),
            _home_row(status='CONFIRMED', fixtureId='missing', startTimeLocal=''),
            _home_row(status='FINISHED', fixtureId='older', startTimeLocal='2026-04-01T21:00:00'),
        ]))
        expected = ['late', 'early', 'older', 'missing']
        self.assertEqual(
            [row['fixtureId'] for row in home_page.filter_schedule_records(records, 'all', None)],
            expected,
        )
        self.assertEqual(
            [row['fixtureId'] for row in home_page.filter_schedule_records(records, 'results', None)],
            expected,
        )

    def _load_filtered(self, rows, n_intervals='home-game-list', filters=None, scope=None):
        with patch.object(home_page, 'df_data', return_value=_schedule_df(rows)), \
                patch(
                    'synergy_inbounder.communicator.Communicator.get_fixture_live_summary',
                    return_value={},
                ):
            return home_page.load_home_game_list(n_intervals, scope, filters)

    def test_empty_upcoming_uses_the_latest_finished_stage(self):
        page, stored = self._load_filtered([
            _home_row(
                status='FINISHED', fixtureId='old-po', fixtureType='PLAYOFF',
                startTimeLocal='2026-04-01T19:00:00', away_team='Old Playoff',
            ),
            _home_row(
                status='CONFIRMED', fixtureId='new-reg', fixtureType='REGULAR',
                startTimeLocal='2026-05-02T19:00:00', away_team='New Regular',
            ),
            _home_row(
                status='CANCELLED', fixtureId='void', fixtureType='FINAL',
                startTimeLocal='2026-05-03T19:00:00', away_team='Void Final',
            ),
        ])
        self.assertEqual(_segmented(page, 'home-show').value, 'results')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'REGULAR')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn('New Regular', listed)
        self.assertNotIn('Old Playoff', listed)
        self.assertNotIn('Void Final', listed)
        self.assertEqual(stored['show'], 'results')
        self.assertEqual(stored['game_type'], 'REGULAR')
        self.assertEqual(stored['league'], 'PLG')

    def test_later_tick_keeps_an_empty_upcoming_view(self):
        filters = home_page.initial_home_filters()
        filters['show'] = 'upcoming'
        filters['game_type'] = 'PLAYOFF'
        page, stored = self._load_filtered([
            _home_row(
                status='FINISHED', fixtureId='po', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-02T19:00:00', away_team='Playoff Done',
            ),
            _home_row(
                status='FINISHED', fixtureId='reg', fixtureType='REGULAR',
                startTimeLocal='2026-04-01T19:00:00', away_team='Regular Done',
            ),
        ], n_intervals=2, filters=filters)
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'PLAYOFF')
        self.assertIn(EMPTY_HOME_FILTER, str(_by_class(page, 'home-schedule-list')[0]))
        self.assertNotIn('Playoff Done', str(_by_class(page, 'home-schedule-list')[0]))
        self.assertIs(stored, no_update)

    def test_later_tick_does_not_follow_a_new_stage(self):
        filters = home_page.initial_home_filters()
        filters['show'] = 'upcoming'
        filters['game_type'] = 'REGULAR'
        page, stored = self._load_filtered([
            _home_row(
                status='FINISHED', fixtureId='reg', fixtureType='REGULAR',
                startTimeLocal='2026-05-01T19:00:00', away_team='Regular Done',
            ),
            _home_row(
                status='IN_PROGRESS', fixtureId='po', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-02T19:00:00', away_team='Playoff Live',
                Score='1 : 2', teamScoreHome=2, teamScoreAway=1,
            ),
        ], n_intervals=2, filters=filters)
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'REGULAR')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertNotIn('Playoff Live', listed)
        self.assertIn(EMPTY_HOME_FILTER, listed)
        self.assertIs(stored, no_update)

    def test_scope_change_recomputes_show(self):
        filters = home_page.initial_home_filters()
        filters['show'] = 'results'
        filters['game_type'] = 'FINAL'
        with patch.object(home_page, '_triggered_id', return_value='home-scope-store'):
            page, stored = self._load_filtered([
                _home_row(
                    status='SCHEDULED', fixtureId='sched', fixtureType='REGULAR',
                    startTimeLocal='2026-10-24T19:00:00', away_team='Next Regular',
                ),
                _home_row(
                    status='FINISHED', fixtureId='old', fixtureType='FINAL',
                    startTimeLocal='2026-05-01T19:00:00', away_team='Old Final',
                ),
            ], n_intervals=4, filters=filters, scope={'league': 'PLG', 'season_id': 'season'})
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'REGULAR')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn('Next Regular', listed)
        self.assertNotIn('Old Final', listed)
        self.assertEqual(stored['show'], 'upcoming')
        self.assertEqual(stored['game_type'], 'REGULAR')

    def test_entry_discards_a_stored_show(self):
        filters = home_page.initial_home_filters()
        filters['show'] = 'all'
        page, stored = self._load_filtered([
            _home_row(status='FINISHED', fixtureId='fin', startTimeLocal='2026-04-01T19:00:00'),
        ], filters=filters)
        self.assertEqual(_segmented(page, 'home-show').value, 'results')
        self.assertEqual(stored['show'], 'results')
        self.assertEqual(stored['game_type'], 'REGULAR')

    def test_stored_all_stays_on_a_later_tick(self):
        filters = home_page.initial_home_filters()
        filters['show'] = 'all'
        filters['game_type'] = 'REGULAR'
        page, stored = self._load_filtered([
            _home_row(status='FINISHED', fixtureId='fin', startTimeLocal='2026-04-01T19:00:00'),
        ], n_intervals=2, filters=filters)
        self.assertEqual(_segmented(page, 'home-show').value, 'all')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'REGULAR')
        self.assertIs(stored, no_update)

    def test_no_finished_game_keeps_upcoming_and_the_filtered_empty_copy(self):
        page, stored = self._load_filtered([
            _home_row(status='CANCELLED', fixtureId='void', away_team='Called Off'),
        ])
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn(EMPTY_HOME_FILTER, listed)
        self.assertNotIn('No games available.', listed)
        self.assertNotIn('Called Off', listed)
        self.assertEqual(stored['show'], 'upcoming')
        self.assertEqual(stored['game_type'], 'REGULAR')

    def test_empty_season_does_not_switch_show(self):
        with patch.object(home_page, 'df_data', return_value=pd.DataFrame()):
            page, stored = home_page.load_home_game_list('home-game-list')
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        self.assertIn(EMPTY_HOME, str(_by_class(page, 'home-schedule-list')[0]))
        self.assertEqual(stored['show'], 'upcoming')
        self.assertIsNone(stored['game_type'])

    def test_if_needed_default_runs_on_entry_and_not_on_a_later_tick(self):
        rows = [
            _home_row(
                status='FINISHED', fixtureId='po', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-01T19:00:00', away_team='Playoff Done',
                Score='80 : 70', teamScoreHome=70, teamScoreAway=80,
            ),
            _home_row(
                status='IF_NEEDED', fixtureId='final', fixtureType='FINAL',
                startTimeLocal='2026-06-01T19:00:00', away_team='Final If Needed',
            ),
        ]
        page, stored = self._load_filtered(rows)
        self.assertEqual(_segmented(page, 'home-show').value, 'results')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'PLAYOFF')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn('Playoff Done', listed)
        self.assertNotIn('Final If Needed', listed)
        self.assertEqual(stored['show'], 'results')
        self.assertEqual(stored['game_type'], 'PLAYOFF')

        records = home_page.schedule_records(_schedule_df(rows))
        kept = home_page.apply_home_filters(
            'upcoming', 'PLAYOFF', 'PLG', stored['seasons']['PLG'], stored, 'home-show',
            records,
        )[0]
        self.assertEqual(kept['show'], 'upcoming')
        self.assertEqual(kept['game_type'], 'FINAL')
        self.assertEqual(
            [row['fixtureId'] for row in home_page.filter_schedule_records(
                records, 'upcoming', 'FINAL',
            )],
            ['final'],
        )

        tick_page, tick_store = self._load_filtered(rows, n_intervals=3, filters=kept)
        self.assertEqual(_segmented(tick_page, 'home-show').value, 'upcoming')
        self.assertEqual(_segmented(tick_page, 'home-game-type').value, 'FINAL')
        tick_listed = str(_by_class(tick_page, 'home-schedule-list')[0])
        self.assertIn('Final If Needed', tick_listed)
        self.assertNotIn('Playoff Done', tick_listed)
        self.assertIs(tick_store, no_update)

    def test_show_click_keeps_a_stage_that_still_has_rows(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(
                status='FINISHED', fixtureId='late-reg', fixtureType='REGULAR',
                startTimeLocal='2026-05-20T19:00:00',
            ),
            _home_row(
                status='FINISHED', fixtureId='po', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-01T19:00:00',
            ),
            _home_row(
                status='SCHEDULED', fixtureId='next-po', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-22T19:00:00',
            ),
        ]))
        kept = home_page.apply_home_filters(
            'results', 'PLAYOFF', 'PLG', None, {'show': 'upcoming', 'game_type': 'PLAYOFF'},
            'home-show', records,
        )[0]
        self.assertEqual(kept['show'], 'results')
        self.assertEqual(kept['game_type'], 'PLAYOFF')

    def test_entry_tie_break_and_blank_status(self):
        tied = home_page.schedule_records(_schedule_df([
            _home_row(
                status='FINISHED', fixtureId='first', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-01T19:00:00',
            ),
            _home_row(
                status='FINISHED', fixtureId='second', fixtureType='REGULAR',
                startTimeLocal='2026-05-01T19:00:00',
            ),
            _home_row(
                status='CONFIRMED', fixtureId='undated', fixtureType='FINAL',
                startTimeLocal='',
            ),
        ]))
        self.assertEqual(home_page.entry_home_view(tied), ('results', 'REGULAR'))
        live = home_page.schedule_records(_schedule_df([
            _home_row(
                status='IN_PROGRESS', fixtureId='a', fixtureType='REGULAR',
                startTimeLocal='2026-05-01T19:00:00',
            ),
            _home_row(
                status='IN_PROGRESS', fixtureId='b', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-01T19:00:00',
            ),
        ]))
        self.assertEqual(home_page.entry_home_view(live), ('upcoming', 'REGULAR'))
        self.assertEqual(
            home_page.entry_home_view([
                {'status': ' IF_NEEDED ', 'fixtureType': 'FINAL', 'startTimeLocal': '2026-06-01T19:00:00'},
                {'status': 'FINISHED', 'fixtureType': 'PLAYOFF', 'startTimeLocal': '2026-05-01T19:00:00'},
            ]),
            ('results', 'PLAYOFF'),
        )
        self.assertEqual(
            home_page.entry_home_view([
                {'status': '', 'fixtureType': 'REGULAR', 'startTimeLocal': '2026-05-20T19:00:00'},
            ]),
            ('upcoming', 'REGULAR'),
        )

    def test_a_scheduled_game_keeps_the_upcoming_default(self):
        page, stored = self._load_filtered([
            _home_row(
                status='IF_NEEDED', fixtureId='ifn', fixtureType='FINAL',
                startTimeLocal='2026-06-01T19:00:00', away_team='If Needed',
            ),
            _home_row(
                status='SCHEDULED', fixtureId='sched', fixtureType='REGULAR',
                startTimeLocal='2026-05-20T19:00:00', away_team='Still Scheduled',
            ),
            _home_row(
                status='FINISHED', fixtureId='fin', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-01T19:00:00', away_team='Already Done',
            ),
        ])
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'REGULAR')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn('Still Scheduled', listed)
        self.assertNotIn('If Needed', listed)
        self.assertNotIn('Already Done', listed)
        self.assertEqual(stored['show'], 'upcoming')
        self.assertEqual(stored['game_type'], 'REGULAR')

    def test_if_needed_without_a_finished_game_stays_on_upcoming(self):
        page, stored = self._load_filtered([
            _home_row(status='IF_NEEDED', fixtureId='ifn', away_team='Only If Needed'),
        ])
        self.assertEqual(_segmented(page, 'home-show').value, 'upcoming')
        self.assertIn('Only If Needed', str(_by_class(page, 'home-schedule-list')[0]))
        self.assertEqual(stored['show'], 'upcoming')
        self.assertEqual(stored['game_type'], 'REGULAR')

    def test_scope_change_applies_the_if_needed_default_for_that_league(self):
        from synergy_inbounder.settings import EASL_SEASON_ID

        filters = home_page.initial_home_filters()
        filters['game_type'] = 'REGULAR'
        with patch.object(home_page, 'df_data', return_value=_schedule_df([
            _home_row(
                status='FINISHED', fixtureId='po', fixtureType='PLAYOFF',
                startTimeLocal='2026-05-01T19:00:00', away_team='Easl Playoff',
            ),
            _home_row(
                status='IF_NEEDED', fixtureId='final', fixtureType='FINAL',
                startTimeLocal='2026-06-01T19:00:00', away_team='Easl Final',
            ),
        ])), patch.object(home_page, '_triggered_id', return_value='home-scope-store'):
            page, stored = home_page.load_home_game_list(
                4,
                {'league': 'EASL', 'season_id': EASL_SEASON_ID},
                filters,
            )
        self.assertEqual(_segmented(page, 'home-league').value, 'EASL')
        self.assertEqual(_segmented(page, 'home-show').value, 'results')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'PLAYOFF')
        self.assertNotIn('Easl Final', str(_by_class(page, 'home-schedule-list')[0]))
        self.assertEqual(stored['league'], 'EASL')
        self.assertEqual(stored['seasons']['EASL'], EASL_SEASON_ID)
        self.assertEqual(stored['show'], 'results')
        self.assertEqual(stored['game_type'], 'PLAYOFF')

    def test_date_header_and_row_time_have_no_iso_t(self):
        tree = self._load([
            _home_row(
                status='SCHEDULED', fixtureId='g1',
                startTimeLocal='2026-03-15T18:30:00',
            ),
        ])
        values = _string_values(tree)
        self.assertIn('2026-03-15 Sun', values)
        self.assertIn('18:30 | Arena', values)
        self.assertNotIn('2026-03-15 Sun | 18:30 | Arena', values)
        self.assertFalse(any('T' in value and value.startswith('2026-') for value in values))

    def test_clickable_rows_and_non_links(self):
        tree = home_page.render_home_page(home_page.schedule_records(_schedule_df([
            _home_row(status='PENDING', fixtureId='pending', startTimeLocal='2026-01-05T19:00:00'),
            _home_row(status='FINISHED', fixtureId='fin', startTimeLocal='2026-01-01T19:00:00',
                      Score='88 : 79', teamScoreHome=88, teamScoreAway=79),
            _home_row(status='ABANDONED', fixtureId='abd', startTimeLocal='2026-01-02T19:00:00',
                      Score='12 : 10', teamScoreHome=12, teamScoreAway=10),
            _home_row(status='SCHEDULED', fixtureId='sched', startTimeLocal='2026-01-06T19:00:00'),
            _home_row(status='IF_NEEDED', fixtureId='ifn', startTimeLocal='2026-01-07T19:00:00'),
            _home_row(status='CANCELLED', fixtureId='can', startTimeLocal='2026-01-03T19:00:00'),
        ])), show='all', game_type=None)
        hrefs = {node.href for node in _anchors(tree)}
        self.assertIn('/game/plg/pending', hrefs)
        self.assertIn('/game/plg/fin', hrefs)
        self.assertIn('/game/plg/abd', hrefs)
        self.assertNotIn('/game/plg/sched', hrefs)
        self.assertNotIn('/game/plg/ifn', hrefs)
        self.assertNotIn('/game/plg/can', hrefs)

    def test_filtered_empty_keeps_filters_not_season_empty_copy(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(
                status='IN_PROGRESS', fixtureId='live', fixtureType='REGULAR',
                startTimeLocal='2026-01-02T19:00:00',
                away_team='Live Away', Score='1 : 2', teamScoreHome=2, teamScoreAway=1,
            ),
            _home_row(
                status='FINISHED', fixtureId='fin', fixtureType='PLAYOFF',
                startTimeLocal='2026-01-01T19:00:00', Score='88 : 79',
                teamScoreHome=88, teamScoreAway=79,
            ),
        ]))
        tree = home_page.render_home_page(records, show='results', game_type='REGULAR')
        listed = str(_by_class(tree, 'home-schedule-list')[0])
        self.assertIn(EMPTY_HOME_FILTER, listed)
        self.assertIn(EMPTY_HOME_FILTER_NEXT, listed)
        self.assertNotIn(EMPTY_HOME, listed)
        self.assertNotIn('Live Away', listed)
        self.assertTrue(_last_update_text(tree).startswith('Last Update: '))
        self.assertIsNotNone(_segmented(tree, 'home-show'))

    def test_show_change_keeps_the_clock_and_error_slot(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(status='FINISHED', fixtureId='fin', startTimeLocal='2026-01-01T19:00:00'),
        ]))
        listed = home_page.update_home_view(records, 'results', None)
        self.assertNotIn('Last Update', str(listed))
        self.assertIn('fin', str(listed))
        alert = home_page.update_home_view({'_ui': 'error'}, 'all', None)
        self.assertIsInstance(alert, dmc.Alert)
        self.assertEqual(alert.children, ERROR_HOME)
        self.assertEqual(alert.title, 'Error')
        self.assertFalse(_by_class(alert, 'home-schedule-list'))

    def test_failed_scope_change_clears_the_clock(self):
        from synergy_inbounder.settings import EASL_SEASON_ID

        with patch.object(home_page, 'df_data', side_effect=RuntimeError('boom')), \
                patch.object(home_page, '_triggered_id', return_value='home-scope-store'):
            tree, stored = home_page.load_home_game_list(
                4,
                {'league': 'EASL', 'season_id': EASL_SEASON_ID},
                {'show': 'results', 'game_type': 'REGULAR', 'league': 'PLG'},
            )
        self.assertIs(stored, no_update)
        self.assertEqual(_last_update_text(tree), 'Last Update: —')
        self.assertEqual(find_type(tree, dmc.Alert)[0].children, ERROR_HOME)
        self.assertFalse(_by_class(tree, 'home-schedule-list'))
        self.assertEqual(_segmented(tree, 'home-league').value, 'EASL')
        self.assertEqual(_segmented(tree, 'home-show').value, 'results')
        season = next(node for node in walk(tree) if _node_id(node) == 'home-season')
        self.assertEqual(season.value, EASL_SEASON_ID)
        line = next(node for node in walk(tree) if _node_id(node) == 'home-last-update')
        text = find_type(line, dmc.Text)[0]
        self.assertEqual(text.size, 'sm')
        self.assertEqual(text.c, 'dimmed')
        self.assertEqual(text.mb, 8)
        self.assertEqual(text.className, 'no-print')

    def test_compact_row_three_digit_well_meta_and_badge(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(
                status='IN_PROGRESS',
                fixtureId='live',
                startTimeLocal='2026-03-15T18:30:00',
                away_team='Taipei Fubon Braves',
                home_team='Formosa Dreamers',
                teamScoreAway=108,
                teamScoreHome=112,
                Venue='Taipei Heping Basketball Gymnasium',
            ),
        ]))
        tree = home_page.render_schedule_list(records, 'upcoming', None)
        score_line = _by_class(tree, 'home-schedule-score-line')[0]
        meta_line = _by_class(tree, 'home-schedule-meta-line')[0]
        well = _by_class(tree, 'home-score-well')[0]

        self.assertFalse(find_type(score_line, dmc.Badge))
        self.assertEqual(meta_line.justify, 'center')
        badges = find_type(meta_line, dmc.Badge)
        self.assertEqual(len(badges), 1)
        self.assertEqual(badges[0].size, 'xs')
        self.assertEqual(badges[0].children, 'IN_PROGRESS')
        self.assertIn('18:30 | Taipei Heping Basketball Gymnasium', _string_values(meta_line))
        meta_texts = [
            node for node in walk(meta_line)
            if isinstance(node, dmc.Text) and node.children == (
                '18:30 | Taipei Heping Basketball Gymnasium'
            )
        ]
        self.assertEqual(len(meta_texts), 1)
        self.assertTrue(meta_texts[0].truncate)
        self.assertEqual(meta_texts[0].miw, 0)
        self.assertNotEqual(getattr(meta_texts[0], 'flex', None), 1)

        well_texts = [node for node in walk(well) if isinstance(node, dmc.Text)]
        self.assertEqual([node.children for node in well_texts], ['108', ':', '112'])
        for node in well_texts:
            if node.children in ('108', '112'):
                self.assertEqual(node.miw, '3ch')
                self.assertEqual(_style(node).get('fontVariantNumeric'), 'tabular-nums')
                self.assertEqual(node.c, '#0077b6')
                self.assertEqual(node.fw, 900)
                self.assertEqual(node.fz, '22px')
        for node in walk(tree):
            self.assertNotIn(getattr(node, 'w', None), (68, 140, '68', '140'))

        names = [
            node for node in walk(score_line)
            if isinstance(node, dmc.Text)
            and node.children in ('Taipei Fubon Braves', 'Formosa Dreamers')
        ]
        self.assertEqual(len(names), 2)
        for node in names:
            self.assertTrue(node.truncate)
            self.assertEqual(node.flex, 1)
            self.assertEqual(node.miw, 0)
            self.assertEqual(node.fw, 800)
            self.assertEqual(node.fz, '16px')

    def test_compact_row_at_well_and_omits_dangling_meta_pipe(self):
        records = home_page.schedule_records(_schedule_df([
            _home_row(
                status='SCHEDULED',
                fixtureId='up',
                startTimeLocal='2026-03-16T19:00:00',
                Venue='',
            ),
        ]))
        tree = home_page.render_schedule_list(records, 'upcoming', None)
        well = _by_class(tree, 'home-score-well')[0]
        meta_line = _by_class(tree, 'home-schedule-meta-line')[0]
        well_values = _string_values(well)
        self.assertEqual(well_values, ['@'])
        spacers = [
            node for node in walk(well)
            if getattr(node, 'miw', None) == '3ch'
        ]
        self.assertEqual(len(spacers), 2)
        self.assertIn('19:00', _string_values(meta_line))
        self.assertFalse(any('|' in value for value in _string_values(meta_line)))


class PlayerDotColorTests(unittest.TestCase):
    def test_player_and_lineup_section_dots_use_home_and_away_colors(self):
        def split_json(frame):
            return frame.to_json(orient='split')

        teams = ['Taipei Fubon Braves', 'Formosa Dreamers']
        bs = {
            'qt_pts_df': split_json(pd.DataFrame({'Team': teams, '1Q': [20, 18]})),
            'qt_foul_df': split_json(pd.DataFrame({'Team': teams, '1Q': [2, 3]})),
            'qt_tout_df': split_json(pd.DataFrame({'Team': teams, '1Q': [1, 0]})),
            't_adv_df': split_json(pd.DataFrame({'Team': teams, 'Pace': [70.0, 68.0]})),
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

    def test_away_section_stays_above_when_the_home_name_sorts_first(self):
        def split_json(frame):
            return frame.to_json(orient='split')

        home = 'Alpha'
        away = 'Zebra'
        match = {'away_team': away, 'home_team': home}
        bs = {
            'qt_pts_df': split_json(pd.DataFrame({'Team': [home, away], '1Q': [20, 18]})),
            'qt_foul_df': split_json(pd.DataFrame({'Team': [home, away], '1Q': [2, 3]})),
            'qt_tout_df': split_json(pd.DataFrame({'Team': [home, away], '1Q': [1, 0]})),
            't_adv_df': split_json(pd.DataFrame({'Team': [home, away], 'Pace': [70.0, 68.0]})),
            't_df': split_json(pd.DataFrame({'Team': [home, away], 'PTS': [88, 79]})),
            'k_df': split_json(pd.DataFrame({'Team': [home, away], 'PIP': [20, 18]})),
            'p_df_dict': {
                home: split_json(pd.DataFrame({'Player': ['A'], 'PTS': [10]})),
                away: split_json(pd.DataFrame({'Player': ['B'], 'PTS': [8]})),
            },
            'p_summary_dict': {},
        }
        tree = game_page.render_bs_children(json.dumps(bs), 'all', match)
        names = [
            node.children for node in walk(tree)
            if isinstance(node, dmc.Text) and getattr(node, 'fw', None) == 800 and node.children in (home, away)
        ]
        self.assertEqual(names, [away, home])
        dots = [
            node.style.get('backgroundColor')
            for node in walk(tree)
            if isinstance(node, dmc.Box) and isinstance(getattr(node, 'style', None), dict)
            and node.style.get('width') == '8px'
        ]
        self.assertEqual(dots, ['#94a3b8', '#00b4d8'])
        team_cells = [
            node for node in walk(tree)
            if isinstance(node, dmc.TableTd) and node.children in (home, away)
        ]
        self.assertEqual(team_cells[0].children, away)
        self.assertEqual(team_cells[0].style.get('borderLeft'), '3.5px solid #94a3b8')
        self.assertEqual(team_cells[1].children, home)
        self.assertEqual(team_cells[1].style.get('borderLeft'), '3.5px solid #0077b6')

        lineup_store = json.dumps({
            '5': {
                home: split_json(pd.DataFrame({'Lineup': ['A-B'], 'PTS': [10]})),
                away: split_json(pd.DataFrame({'Lineup': ['C-D'], 'PTS': [8]})),
            }
        })
        lineup_tree = game_page.render_lineup_children(lineup_store, 5, False, match)
        lineup_names = [
            node.children for node in walk(lineup_tree)
            if isinstance(node, dmc.Text) and getattr(node, 'fw', None) == 800 and node.children in (home, away)
        ]
        self.assertEqual(lineup_names, [away, home])
        lineup_dots = [
            node.style.get('backgroundColor')
            for node in walk(lineup_tree)
            if isinstance(node, dmc.Box) and isinstance(getattr(node, 'style', None), dict)
            and node.style.get('width') == '8px'
        ]
        self.assertEqual(lineup_dots, ['#94a3b8', '#00b4d8'])


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


class PlayerGridSortTests(unittest.TestCase):
    def test_minutes_and_jersey_sort_as_numbers_and_names_stay_ascending_first(self):
        df = pd.DataFrame([{
            '#': '10',
            'Player': 'Lin',
            'S': '○',
            'Min': '20:00',
            '+/-': 5,
            '2M': 1,
            '2A': 2,
            '2FG%': '.500',
            'eFG%': '50.0%',
            'USG%': '20.0%',
            'PM': '12-10',
            'PTS': 2,
        }])
        grid = find_type(game_page._ag_grid_from_df(df), dag.AgGrid)[0]

        def field(name, cols=None):
            for col in cols if cols is not None else grid.columnDefs:
                if col.get('field') == name:
                    return col
                found = field(name, col.get('children') or [])
                if found:
                    return found
            return None

        desc = ['desc', 'asc', None]
        for name in ('#', 'Min', 'eFG%', 'USG%', '+/-', 'PTS'):
            col = field(name)
            self.assertIsNotNone(col, name)
            self.assertEqual(col.get('sortingOrder'), desc, name)
            self.assertIn('isDescending', col['comparator']['function'])
        self.assertIn("indexOf(':')", field('Min')['comparator']['function'])
        self.assertIn("replace('%'", field('eFG%')['comparator']['function'])
        self.assertIn('DNP', field('Min')['comparator']['function'])
        for name in ('S', 'PM'):
            col = field(name)
            self.assertIsNone(col.get('sortingOrder'), name)
            self.assertIsNone(col.get('comparator'), name)
        player = field('Player')
        self.assertIsNone(player.get('sortingOrder'))
        self.assertIn('match[2].toLowerCase()', player['comparator']['function'])
        self.assertIn('!ka || !kb', player['comparator']['function'])
        self.assertEqual(player.get('tooltipField'), '_playerFull')
        self.assertNotIn('tooltipValueGetter', player)


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
        self.assertIn('2026-01-01 | 19:00 | Arena', _string_values(tree))
        self.assertNotIn('2026-01-01 • 19:00 • Arena', _string_values(tree))
        badges = find_type(tree, dmc.Badge)
        self.assertEqual(badges[0].size, 'md')
        well = _by_class(tree, 'home-score-well')[0]
        self.assertEqual(_string_values(well), ['2', ':', '1'])
        for node in walk(well):
            if getattr(node, 'children', None) in ('2', '1'):
                self.assertEqual(node.miw, '3ch')
                self.assertEqual(_style(node).get('fontVariantNumeric'), 'tabular-nums')
        self.assertFalse(find_type(_by_class(tree, 'home-schedule-score-line')[0], dmc.Badge))
        meta_line = _by_class(tree, 'home-schedule-meta-line')[0]
        self.assertEqual(meta_line.justify, 'center')
        self.assertEqual(find_type(meta_line, dmc.Badge)[0].size, 'md')

    def test_banner_shares_two_line_composition_with_date_in_cluster(self):
        tree = game_banner(
            home_team='Taipei Fubon Braves',
            away_team='Formosa Dreamers',
            home_score=112,
            away_score=108,
            status='FINISHED',
            date='2026-05-30',
            time='19:00',
            venue='Taipei Heping Basketball Gymnasium',
        )
        values = _string_values(tree)
        self.assertIn('2026-05-30 | 19:00 | Taipei Heping Basketball Gymnasium', values)
        self.assertNotIn('19:00 | Taipei Heping Basketball Gymnasium', values)
        self.assertEqual(find_type(tree, dmc.Badge)[0].size, 'md')
        well_values = _string_values(_by_class(tree, 'home-score-well')[0])
        self.assertEqual(well_values, ['108', ':', '112'])
        self.assertFalse(find_type(_by_class(tree, 'home-schedule-score-line')[0], dmc.Badge))
        self.assertEqual(_by_class(tree, 'home-schedule-meta-line')[0].justify, 'center')


class PageDeleteSvgTests(unittest.TestCase):
    def test_js_page_delete_uses_inline_svg(self):
        js_path = os.path.join(REPO, 'assets', 'report_canvas.js')
        with open(js_path, 'r', encoding='utf-8') as handle:
            js = handle.read()
        self.assertIn('<svg', js)
        self.assertNotIn('bi-x-lg', js)
        self.assertNotIn('LIVE 🔴', js)
        self.assertNotIn('ScheduleStatusBadge', js)
        self.assertNotIn('ScheduleScoreLink', js)

    def test_table_pan_is_bound_without_visible_scrollbar_contract(self):
        js_path = os.path.join(REPO, 'assets', 'ag_grid_cells.js')
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
        self.assertIn('.braves-clean-table thead tr:first-child > th:first-child', css)
        self.assertIn('.braves-clean-table tbody td:first-child', css)
        self.assertNotIn('.braves-clean-table th:first-child,', css)
        self.assertNotIn('.braves-clean-table td:first-child', css)
        fit = js.split('function _applyLineupWidth')[1].split('function splashboardFitLineupWidth')[0]
        self.assertLess(fit.index('if (unchanged)'), fit.index('api.setColumnWidths(updates)'))
        self.assertLess(fit.index('api.setColumnWidths(updates)'), fit.index('api.resetRowHeights()'))


class GameLayoutContractTests(unittest.TestCase):
    def test_game_layout_uses_skeleton_and_dash_iconify(self):
        layout = game_page.layout('abc')
        self.assertTrue(find_type(layout, dmc.Skeleton))
        self.assertTrue(find_type(layout, DashIconify))
        markup = str(layout)
        self.assertNotIn('bi bi-', markup)
        self.assertNotIn('Loading...', markup)
