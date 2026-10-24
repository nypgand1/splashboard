import unittest
from unittest.mock import patch

from dash import no_update
import dash_mantine_components as dmc
import pandas as pd

import app  # noqa: F401
from pages import home as home_page
from ui_kit import (
    EMPTY_HOME_FILTER,
    EMPTY_HOME_FILTER_NEXT,
    EMPTY_HOME_FILTER_TEAM_NEXT,
)


def _walk(node):
    yield node
    children = getattr(node, 'children', None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    else:
        yield from _walk(children)


def _node_id(node):
    return getattr(node, 'id', None)


def _game(
    fixture_id,
    home_id,
    away_id,
    home_name,
    away_name,
    status='SCHEDULED',
    fixture_type='REGULAR',
    start='2026-05-01T19:00:00',
):
    return {
        'fixtureId': fixture_id,
        'status': status,
        'fixtureType': fixture_type,
        'startTimeLocal': start,
        'homeTeam': home_name,
        'awayTeam': away_name,
        'teamIdHome': home_id,
        'teamIdAway': away_id,
        'league': 'PLG',
        'venue': 'Arena',
        'homeScore': None,
        'awayScore': None,
    }


def _season():
    return [
        _game('reg-live', 'braves', 'dreamers', 'Braves', 'Dreamers',
              status='IN_PROGRESS', start='2026-05-20T19:00:00'),
        _game('po-up', 'kings', 'dreamers', 'Kings', 'Dreamers',
              fixture_type='PLAYOFF', start='2026-05-22T19:00:00'),
        _game('po-done', 'kings', 'braves', 'Kings', 'Braves',
              status='FINISHED', fixture_type='PLAYOFF', start='2026-05-10T19:00:00'),
        _game('tbd', '', 'dreamers', 'TBD', 'Dreamers',
              fixture_type='FINAL', start='2026-06-01T19:00:00'),
    ]


class HomeTeamFilterTests(unittest.TestCase):
    def test_menu_uses_entity_ids_and_skips_tbd(self):
        options, visible = home_page.team_menu([
            _game('a', 'kings', 'braves', 'Kings', 'Braves'),
            _game('b', 'other', 'braves', 'Braves', 'Braves'),
            _game('c', '', 'dreamers', 'TBD', 'Dreamers'),
            _game('d', 'blank', 'dreamers', '  ', 'Dreamers'),
        ])
        self.assertTrue(visible)
        self.assertEqual(
            [(item['label'], item['value']) for item in options],
            [
                ('All Teams', 'all'),
                ('Braves', 'braves'),
                ('Braves', 'other'),
                ('Dreamers', 'dreamers'),
                ('Kings', 'kings'),
            ],
        )

    def test_menu_hides_when_fewer_than_two_named_teams(self):
        _options, visible = home_page.team_menu([
            _game('a', 'braves', '', 'Braves', 'TBD'),
        ])
        self.assertFalse(visible)
        self.assertEqual(home_page.coerce_team([
            _game('a', 'braves', '', 'Braves', 'TBD'),
        ], 'braves'), 'all')

    def test_either_side_keeps_one_row(self):
        rows = home_page.candidates_for_team(_season(), 'kings')
        self.assertEqual([row['fixtureId'] for row in rows], ['po-up', 'po-done'])

    def test_team_choice_jumps_only_when_the_stage_has_no_game(self):
        stored = home_page.initial_home_filters()
        stored['show'] = 'upcoming'
        stored['game_type'] = 'REGULAR'
        data, scope = home_page.apply_home_filters(
            'upcoming', 'REGULAR', 'PLG', stored['seasons']['PLG'], stored,
            'home-team', _season(), team='kings',
        )
        self.assertIsNone(scope)
        self.assertEqual(data['show'], 'upcoming')
        self.assertEqual(data['team'], 'kings')
        self.assertEqual(data['game_type'], 'PLAYOFF')

        stayed, _scope = home_page.apply_home_filters(
            'upcoming', 'REGULAR', 'PLG', stored['seasons']['PLG'], stored,
            'home-team', _season(), team='dreamers',
        )
        self.assertEqual(stayed['game_type'], 'REGULAR')
        self.assertEqual(stayed['team'], 'dreamers')

    def test_show_click_uses_the_selected_team(self):
        stored = home_page.initial_home_filters()
        stored['show'] = 'upcoming'
        stored['game_type'] = 'REGULAR'
        stored['team'] = 'kings'
        data, _scope = home_page.apply_home_filters(
            'results', 'REGULAR', 'PLG', stored['seasons']['PLG'], stored,
            'home-show', _season(), team='kings',
        )
        self.assertEqual(data['show'], 'results')
        self.assertEqual(data['team'], 'kings')
        self.assertEqual(data['game_type'], 'PLAYOFF')

    def test_game_type_click_does_not_jump(self):
        stored = home_page.initial_home_filters()
        stored['show'] = 'upcoming'
        stored['game_type'] = 'PLAYOFF'
        stored['team'] = 'kings'
        data, _scope = home_page.apply_home_filters(
            'upcoming', 'REGULAR', 'PLG', stored['seasons']['PLG'], stored,
            'home-game-type', _season(), team='kings',
        )
        self.assertEqual(data['show'], 'upcoming')
        self.assertEqual(data['game_type'], 'REGULAR')
        self.assertEqual(data['team'], 'kings')

    def test_all_teams_keeps_a_stage_that_still_has_a_game(self):
        stored = home_page.initial_home_filters()
        stored['show'] = 'upcoming'
        stored['game_type'] = 'PLAYOFF'
        stored['team'] = 'kings'
        data, _scope = home_page.apply_home_filters(
            'upcoming', 'PLAYOFF', 'PLG', stored['seasons']['PLG'], stored,
            'home-team', _season(), team='all',
        )
        self.assertEqual(data['team'], 'all')
        self.assertEqual(data['show'], 'upcoming')
        self.assertEqual(data['game_type'], 'PLAYOFF')

    def test_all_teams_jumps_when_the_stage_is_empty(self):
        stored = home_page.initial_home_filters()
        stored['show'] = 'upcoming'
        stored['game_type'] = 'FINAL'
        rows = [row for row in _season() if row['fixtureType'] != 'FINAL']
        data, _scope = home_page.apply_home_filters(
            'upcoming', 'FINAL', 'PLG', stored['seasons']['PLG'], stored,
            'home-team', rows, team='all',
        )
        self.assertEqual(data['show'], 'upcoming')
        self.assertEqual(data['game_type'], 'REGULAR')

    def test_league_change_clears_the_team(self):
        stored = home_page.initial_home_filters()
        stored['show'] = 'results'
        stored['team'] = 'kings'
        data, scope = home_page.apply_home_filters(
            'results', 'PLAYOFF', 'EASL', stored['seasons']['PLG'], stored,
            'home-league', team='kings',
        )
        self.assertEqual(data['team'], 'all')
        self.assertIsNotNone(scope)
        self.assertEqual(data['show'], 'results')

    def test_reload_keeps_a_live_team_and_drops_a_missing_one(self):
        filters = home_page.initial_home_filters()
        filters['show'] = 'upcoming'
        filters['game_type'] = 'REGULAR'
        filters['team'] = 'kings'
        frame = home_page._decorate_schedule(pd.DataFrame([
            {
                'startTimeLocal': '2026-05-22T19:00:00',
                'status': 'SCHEDULED',
                'fixtureType': 'PLAYOFF',
                'fixtureId': 'po-up',
                'venueId': 'v',
                'teamIdHome': 'kings',
                'teamIdAway': 'dreamers',
                'teamScoreHome': None,
                'teamScoreAway': None,
                'Home Team': 'Kings',
                'Away Team': 'Dreamers',
                'Venue': 'Arena',
            },
        ]))
        with patch.object(home_page, 'df_data', return_value=frame), \
                patch.object(home_page, 'refresh_summaries') as refresh:
            page, stored = home_page.load_home_game_list(3, None, filters)
        self.assertIs(stored, no_update)
        self.assertEqual(_select(page).value, 'kings')
        self.assertEqual(_segmented(page, 'home-game-type').value, 'REGULAR')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn(EMPTY_HOME_FILTER_TEAM_NEXT, listed)
        self.assertEqual(refresh.call_args[0][1], [])

        filters['team'] = 'gone'
        with patch.object(home_page, 'df_data', return_value=frame):
            page, stored = home_page.load_home_game_list(4, None, filters)
        self.assertEqual(stored['team'], 'all')
        self.assertEqual(stored['game_type'], 'REGULAR')
        self.assertEqual(stored['show'], 'upcoming')
        self.assertEqual(_select(page).value, 'all')
        listed = str(_by_class(page, 'home-schedule-list')[0])
        self.assertIn(EMPTY_HOME_FILTER_NEXT, listed)
        self.assertNotIn('Kings', listed)

    def test_empty_copy_and_results_label(self):
        tree = home_page.render_home_page(_season(), show='results', game_type='REGULAR', team='kings')
        listed = str(_by_class(tree, 'home-schedule-list')[0])
        self.assertIn(EMPTY_HOME_FILTER, listed)
        self.assertIn(EMPTY_HOME_FILTER_TEAM_NEXT, listed)
        show = _segmented(tree, 'home-show')
        self.assertEqual(
            [(item['label'], item['value']) for item in show.data],
            [('Upcoming', 'upcoming'), ('Results', 'results'), ('All', 'all')],
        )
        probes = [
            node.children for node in _walk(tree)
            if getattr(node, 'className', None) == 'home-team-sizer-probe'
        ]
        self.assertIn('All Teams', probes)
        self.assertIn('Kings', probes)
        self.assertIn('Dreamers', probes)
        self.assertNotIn('TBD', probes)

    def test_all_teams_empty_copy_omits_team(self):
        tree = home_page.render_home_page(
            _season(), show='results', game_type='REGULAR', team='all',
        )
        listed = str(_by_class(tree, 'home-schedule-list')[0])
        self.assertIn(EMPTY_HOME_FILTER_NEXT, listed)
        self.assertNotIn(EMPTY_HOME_FILTER_TEAM_NEXT, listed)

    def test_hidden_live_game_is_not_fetched(self):
        with patch.object(home_page, 'refresh_summaries') as refresh:
            home_page._apply_live_clocks(_season(), 'upcoming', 'REGULAR', 'PLG', 'kings')
        self.assertEqual(refresh.call_args[0][1], [])
        with patch.object(home_page, 'refresh_summaries') as refresh:
            home_page._apply_live_clocks(_season(), 'upcoming', 'REGULAR', 'PLG', 'all')
        visible = refresh.call_args[0][1]
        self.assertEqual([row['fixtureId'] for row in visible], ['reg-live'])


def _by_class(node, class_name):
    found = []
    for item in _walk(node):
        classes = getattr(item, 'className', None) or ''
        if class_name in str(classes).split():
            found.append(item)
    return found


def _segmented(node, node_id):
    for item in _walk(node):
        if _node_id(item) == node_id and isinstance(item, dmc.SegmentedControl):
            return item
    return None


def _select(node):
    for item in _walk(node):
        if _node_id(item) == 'home-team' and isinstance(item, dmc.Select):
            return item
    return None
