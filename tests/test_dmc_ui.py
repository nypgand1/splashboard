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
        papers = find_type(tree, dmc.Paper)
        graphs = [node for node in walk(tree) if getattr(node, '_type', None) == 'Graph'
                  or node.__class__.__name__ == 'Graph']
        self.assertTrue(find_type(tree, dmc.Text))
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].className, 'braves-card-wrapper')
        self.assertEqual(len(graphs), 1)
        self.assertEqual(graphs[0].style.get('width'), '100%')
        self.assertTrue(graphs[0].config.get('responsive'))
        self.assertFalse(graphs[0].config.get('displayModeBar'))
        self.assertFalse(graphs[0].config.get('scrollZoom'))
        self.assertNotEqual(getattr(graphs[0], 'className', None), 'braves-table-scroll')
        fig = graphs[0].figure
        self.assertIn(fig.layout.dragmode, ('pan', False))
        self.assertIn('Last Update', str(tree))


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
        with patch.object(home_page, 'df_data', return_value=df):
            return home_page.load_home_game_list('home-game-list')

    def test_success_is_not_ag_grid(self):
        tree = self._load([_home_row(status='FINISHED', fixtureId='g1')])
        self.assertFalse(find_type(tree, dag.AgGrid))
        self.assertTrue(_papers(tree))

    def test_hero_is_live_else_first_upcoming_and_hidden_when_empty(self):
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
            ),
        ])
        hero = str(_papers(live_upcoming)[0])
        self.assertIn('Live Away', hero)
        self.assertIn('Live Home', hero)
        self.assertNotIn('Upcoming Away', hero)

        upcoming_only = self._load([
            _home_row(
                status='FINISHED', fixtureId='fin1',
                startTimeLocal='2026-02-01T19:00:00',
            ),
            _home_row(
                status='SCHEDULED', fixtureId='up1',
                startTimeLocal='2026-03-02T19:00:00',
                away_team='Upcoming Away', home_team='Upcoming Home',
            ),
        ])
        hero = str(_papers(upcoming_only)[0])
        self.assertIn('Upcoming Away', hero)

        empty = self._load([])
        markup = str(empty)
        self.assertIn(EMPTY_HOME, markup)
        self.assertFalse(find_type(empty, dmc.Paper))

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
            ['upcoming', 'finished', 'all'],
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
        finished = home_page.filter_schedule_records(records, 'finished', None)
        self.assertEqual([row['fixtureId'] for row in finished], ['fin'])
        all_rows = home_page.filter_schedule_records(records, 'all', None)
        self.assertEqual([row['fixtureId'] for row in all_rows], ['fin', 'void', 'live', 'up'])

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
        self.assertIn('2026-03-15 Sun | 18:30 | Arena', values)
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
        self.assertIn('/game/pending', hrefs)
        self.assertIn('/game/fin', hrefs)
        self.assertIn('/game/abd', hrefs)
        self.assertNotIn('/game/sched', hrefs)
        self.assertNotIn('/game/ifn', hrefs)
        self.assertNotIn('/game/can', hrefs)

    def test_filtered_empty_keeps_hero_not_season_empty_copy(self):
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
        tree = home_page.render_home_page(records, show='finished', game_type='REGULAR')
        markup = str(tree)
        self.assertIn(EMPTY_HOME_FILTER, markup)
        self.assertIn(EMPTY_HOME_FILTER_NEXT, markup)
        self.assertNotIn(EMPTY_HOME, markup)
        self.assertIn('Live Away', str(_papers(tree)[0]))

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
