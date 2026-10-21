# -*- coding: utf-8 -*-
import unittest

import pandas as pd

import dash_mantine_components as dmc

from synergy_inbounder.names import (
    TEAM_TBD,
    display_name,
    lineup_token,
    person_full_name,
    person_name,
    player_label,
    player_sort_key,
    shared_short_labels,
)
from synergy_reporter.matchups import lineup_name
from synergy_reporter.rotation import _shirt_label
from ui_kit import team_name_lines, team_name_text


LABELS = {
    'Jarrod JONES': 'J.Jones',
    'TANAKA Makoto': 'M.Tanaka',
    'LEE Kai-Yan': 'K.Y.Lee',
    'CHEN Fan-Po-Yen': 'F.P.Y.Chen',
    'KU Mao-Wei-Chia': 'M.W.C.Ku',
    'CJ CANSINO': 'C.Cansino',
    'D.J. NEWBILL': 'D.Newbill',
    'D.J Stephens': 'D.Stephens',
    'Henry Galinato, Jr.': 'H.Galinato',
    'Tomlinson, William Leslie': 'W.Tomlinson',
    'Juan Gomez De Liano': 'J.De Liano',
    'Joshua DE VILLA': 'J.De Villa',
    'Mathew Douglas VAN PELT': 'M.Van Pelt',
    'Stephen Eric ZIMMERMAN JR': 'S.Zimmerman',
    'Kavell Chevano BIGBY-WILLIAMS': 'K.Bigby-Williams',
    'Bono, Anna Liza Montecillo': 'A.Bono',
    'Tsung-Lin, Lu': 'L.Tsung-Lin',
    'Ganuelas-Rosser, Matt': 'M.Ganuelas-Rosser',
    'MENDOZA, ALFONSO, JR.': 'A.Mendoza',
    'ABANILLA III, GELACIO': 'G.Abanilla',
    'Lastimosa jr., Isabelo': 'I.Lastimosa',
    'TOGTOKHBAYAR Amgalanbayar': 'A.Togtokhbayar',
    'Rahlir Hollis-Jefferson': 'R.Hollis-Jefferson',
    'AHN Jeonguk': 'J.Ahn',
    'GANZAM Gan-Erdene': 'G.E.Ganzam',
    'AU Man Fai': 'M.Au',
    'LEE SEUNG MIN': 'L.Min',
    'KI TAE KIM': 'K.Kim',
    'Olivia': 'Olivia',
    'Lin': 'Lin',
    '林書豪': '林書豪',
}


class PlayerLabelTests(unittest.TestCase):
    def test_locked_shapes(self):
        for full, short in LABELS.items():
            with self.subTest(full=full):
                self.assertEqual(player_label(full), short)

    def test_blank_is_empty(self):
        self.assertEqual(player_label(''), '')
        self.assertEqual(player_label(None), '')
        self.assertEqual(player_label('   '), '')

    def test_sort_groups_family_then_initial(self):
        self.assertEqual(
            sorted(['K.Lee', 'J.Lee', 'A.Ahn', 'K.Y.Lee'], key=player_sort_key),
            ['A.Ahn', 'J.Lee', 'K.Lee', 'K.Y.Lee'],
        )
        self.assertEqual(player_sort_key('J.De Liano'), ('de liano', 'j.'))
        self.assertEqual(player_sort_key('林書豪'), ('林書豪', ''))
        self.assertEqual(player_sort_key('Olivia'), ('olivia', ''))

    def test_lookup_keeps_full_name_and_raw_id_on_a_miss(self):
        table = {'p1': 'LEE Kai-Yan'}
        self.assertEqual(person_name(table, 'p1'), 'K.Y.Lee')
        self.assertEqual(person_full_name(table, 'p1'), 'LEE Kai-Yan')
        self.assertEqual(person_name(table, 'missing'), 'missing')
        self.assertEqual(person_full_name({'p1': '  '}, 'p1'), 'p1')
        self.assertEqual(person_name(None, None), '')
        self.assertEqual(display_name({}, 'missing'), TEAM_TBD)


class TeamNameLineTests(unittest.TestCase):
    def test_phone_split_budget(self):
        self.assertEqual(team_name_lines('Ryukyu Golden Kings'), ('Ryukyu', 'Golden Kings'))
        self.assertEqual(team_name_lines('Taoyuan Pauian Pilots'), ('Taoyuan', 'Pauian Pilots'))
        self.assertEqual(
            team_name_lines('Anyang Jung Kwan Jang Red Boosters'),
            ('Anyang Jung Kwan Jang', 'Red Boosters'),
        )
        self.assertEqual(team_name_lines('Goyang Sono Skygunners'), ('Goyang Sono', 'Skygunners'))
        self.assertEqual(team_name_lines('Hong Kong Eastern'), ('Hong Kong', 'Eastern'))
        self.assertEqual(team_name_lines('Taipei Fubon Braves'), ('Taipei Fubon', 'Braves'))
        self.assertEqual(team_name_lines('Macau Hou Chon'), ('Macau Hou', 'Chon'))
        self.assertEqual(team_name_lines('New Taipei Kings'), ('New Taipei', 'Kings'))
        self.assertEqual(team_name_lines('Formosa Dreamers'), ('Formosa', 'Dreamers'))
        self.assertEqual(team_name_lines('Hiroshima Dragonflies'), ('Hiroshima', 'Dragonflies'))
        self.assertEqual(team_name_lines('Chiba Jets'), ('Chiba Jets', None))
        self.assertEqual(team_name_lines('Alvark Tokyo'), ('Alvark Tokyo', None))
        self.assertEqual(team_name_lines('臺北富邦勇士'), ('臺北富邦勇士', None))
        self.assertEqual(team_name_lines('Braves'), ('Braves', None))
        self.assertEqual(team_name_lines('TBD'), ('TBD', None))
        self.assertEqual(team_name_lines('ABCDEFGHIJKLM'), ('ABCDEFGHIJKLM', None))

    def test_split_block_keeps_the_wide_name(self):
        node = team_name_text('Formosa Dreamers', 'left')
        self.assertIsInstance(node, dmc.Box)
        wide = node.children[0]
        narrow = node.children[1]
        self.assertEqual(wide.children, 'Formosa Dreamers')
        self.assertEqual(wide.className, 'team-name-wide')
        self.assertTrue(wide.truncate)
        self.assertEqual(wide.flex, 1)
        self.assertEqual(wide.fw, 800)
        self.assertEqual(wide.fz, '16px')
        self.assertEqual(narrow.className, 'team-name-narrow')
        self.assertEqual([child.children for child in narrow.children], ['Formosa', 'Dreamers'])
        self.assertTrue(narrow.children[0].truncate)
        self.assertFalse(narrow.children[1].truncate)

    def test_short_and_cjk_names_stay_one_text(self):
        short = team_name_text('Braves', 'right')
        self.assertIsInstance(short, dmc.Text)
        self.assertEqual(short.children, 'Braves')
        self.assertIsNone(getattr(short, 'className', None))
        cjk = team_name_text('臺北富邦勇士', 'left')
        self.assertIsInstance(cjk, dmc.Text)
        self.assertEqual(cjk.children, '臺北富邦勇士')


class PlayerColumnContractTests(unittest.TestCase):
    def test_lineup_column_is_not_the_player_sort(self):
        import app  # noqa: F401
        from pages.game import _build_stats_column_defs

        defs = _build_stats_column_defs(['Lineup', 'Min', '+/-'], lineup_size=5)
        lineup = next(col for col in defs if col.get('field') == 'Lineup')
        self.assertNotIn('comparator', lineup)
        self.assertNotIn('tooltipValueGetter', lineup)
        self.assertNotIn('tooltipField', lineup)

    def test_report_paint_drops_underscore_columns(self):
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'report_canvas.js')
        with open(path, encoding='utf-8') as handle:
            js = handle.read()
        body = js.split('function parseSplit', 1)[1].split('function rotationFigure', 1)[0]
        self.assertIn("charAt(0) === '_'", body)

    def test_phone_css_swaps_the_team_name_lines(self):
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'report.css')
        with open(path, encoding='utf-8') as handle:
            css = handle.read()
        start = css.find('.team-name-narrow')
        self.assertGreater(start, 0)
        media = css.find('@media (max-width: 768px)', start)
        self.assertIn('display: none !important', css[start:media])
        self.assertGreater(media, start)
        phone = css[media:css.find('.home-schedule-list', media)]
        wide = phone.split('.team-name-narrow', 1)[0]
        self.assertIn('.team-name-wide', wide)
        self.assertIn('display: none !important', wide)
        self.assertIn('visibility: hidden !important', wide)
        self.assertIn('position: absolute !important', wide)
        self.assertIn('width: 0 !important', wide)
        self.assertIn('height: 0 !important', wide)
        self.assertIn('overflow: hidden !important', wide)
        self.assertIn('display: flex !important', phone)


class ShortLabelWiringTests(unittest.TestCase):
    def test_lineup_and_rotation_use_the_short_label(self):
        names = {'a': 'LEE Kai-Yan', 'b': 'TANAKA Makoto'}
        self.assertEqual(
            lineup_name(['a', 'b'], {'a': 7, 'b': 4}, names),
            'M.Tanaka-K.Y.Lee',
        )
        self.assertEqual(
            _shirt_label('a', names, {'a': {'shirtNumber': '7'}}),
            '#7 K.Y.Lee',
        )

    def test_a_shared_short_label_gains_the_shirt_only(self):
        names = {
            'a': 'LEE Junghyun',
            'b': 'LEE Jaedo',
            'c': 'KIM Jinyoo',
            'd': 'LEE Geunjoon',
        }
        self.assertEqual(
            lineup_name(['a', 'b', 'c'], {'a': 6, 'b': 4, 'c': 55}, names),
            'J.Lee#4-J.Lee#6-J.Kim',
        )
        self.assertEqual(
            lineup_name(['b', 'c'], {'b': 4.0, 'c': 55}, names, team_ids=['a', 'd']),
            'J.Lee#4-J.Kim',
        )
        self.assertEqual(
            lineup_name(['b', 'c'], {'b': 4, 'c': 55}, names),
            'J.Lee-J.Kim',
        )
        self.assertEqual(
            lineup_name(['a', 'b'], {'a': 6}, names),
            'J.Lee#6-J.Lee',
        )
        shared = shared_short_labels(names, ['a', 'b'])
        self.assertEqual(lineup_token(names, 'a', None, shared), 'J.Lee')
        self.assertEqual(lineup_token(names, 'c', 55, shared), 'J.Kim')
        self.assertNotIn('#', player_label('LEE Junghyun'))

    def test_player_stats_keep_the_full_name_beside_the_short_label(self):
        from unittest.mock import patch

        from synergy_inbounder.parser import Parser
        from synergy_reporter.post_game_report import PostGameReport

        players = pd.DataFrame([{
            'entityId': 'home',
            'personId': 'p1',
            'minutes': 'PT12M00S',
            'participated': True,
            'plusMinus': 1,
            'pointsTwoMade': 1,
            'pointsTwoAttempted': 2,
            'pointsThreeMade': 0,
            'pointsThreeAttempted': 1,
            'freeThrowsMade': 0,
            'freeThrowsAttempted': 0,
            'reboundsOffensive': 0,
            'reboundsDefensive': 1,
            'rebounds': 1,
            'assists': 0,
            'turnovers': 0,
            'steals': 0,
            'blocks': 0,
            'foulsTotal': 1,
            'points': 2,
            'starter': True,
        }])
        bundle = (
            pd.DataFrame([{'entityId': 'home', 'minutes': 'PT38M12S'}]),
            pd.DataFrame([{'entityId': 'home', 'periodId': 1, 'points': 2}]),
            players,
            {'home': ['p1']},
            pd.DataFrame(),
            {'home': 'Braves', 'p1': 'LEE Kai-Yan'},
            [],
            pd.DataFrame(),
        )
        with patch.object(Parser, 'parse_game_bundle', return_value=bundle):
            report = PostGameReport('game-1')
        row = report._get_player_stats_df_dict()['Braves'].iloc[0]
        self.assertEqual(row['Player'], 'K.Y.Lee')
        self.assertEqual(row['_playerFull'], 'LEE Kai-Yan')

    def test_player_box_keeps_a_shared_short_label(self):
        from unittest.mock import patch

        from synergy_inbounder.parser import Parser
        from synergy_reporter.post_game_report import PostGameReport

        def player(person_id):
            return {
                'entityId': 'home',
                'personId': person_id,
                'minutes': 'PT12M00S',
                'participated': True,
                'plusMinus': 0,
                'points': 1,
                'starter': False,
            }

        bundle = (
            pd.DataFrame([{'entityId': 'home'}]),
            pd.DataFrame(),
            pd.DataFrame([player('p1'), player('p2')]),
            {'home': []},
            pd.DataFrame(),
            {'home': 'Braves', 'p1': 'LEE Junghyun', 'p2': 'LEE Jaedo'},
            [
                {'personId': 'p1', 'shirtNumber': '6', 'entityId': 'home'},
                {'personId': 'p2', 'shirtNumber': '4', 'entityId': 'home'},
            ],
            pd.DataFrame(),
        )
        with patch.object(Parser, 'parse_game_bundle', return_value=bundle):
            report = PostGameReport('game-1')
        names = set(report._get_player_stats_df_dict()['Braves']['Player'])
        self.assertEqual(names, {'J.Lee'})
