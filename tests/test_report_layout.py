import unittest

try:
    from synergy_reporter import report_layout
except ImportError:
    report_layout = None

ALLOWED_TABLE_KEYS = (
    'score_group',
    't_adv_df',
    't_df',
    'k_df',
    'p_df_home',
    'p_df_away',
    'lineup_home',
    'lineup_away',
)
ALLOWED_BLOCK_TYPES = ('builtin_table', 'text', 'image', 'spacer')


def _layout():
    if report_layout is None:
        raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
    return report_layout.default_layout()


def _blocks(layout, page_index):
    return layout['pages'][page_index]['blocks']


def _table_keys(blocks):
    return [b.get('table_key') for b in blocks if b.get('type') == 'builtin_table']


def _occupied_rows(blocks):
    return max(b['y'] + b['h'] for b in blocks)


class DefaultLayoutTests(unittest.TestCase):
    def test_version_and_five_pages(self):
        layout = _layout()
        self.assertEqual(layout['version'], 1)
        self.assertEqual(len(layout['pages']), 5)

    def test_header_is_not_a_block(self):
        layout = _layout()
        for page in layout['pages']:
            types = [b.get('type') for b in page['blocks']]
            self.assertNotIn('header', types)
            for block in page['blocks']:
                self.assertNotEqual(block.get('role'), 'header')

    def test_each_page_has_empty_text(self):
        layout = _layout()
        for page in layout['pages']:
            texts = [b for b in page['blocks'] if b.get('type') == 'text']
            self.assertTrue(texts)
            self.assertTrue(any((b.get('content') or '') == '' for b in texts))
            for text in texts:
                self.assertEqual(text.get('h'), 2)

    def test_default_has_no_spacer(self):
        layout = _layout()
        for page in layout['pages']:
            types = [b.get('type') for b in page['blocks']]
            self.assertNotIn('spacer', types)

    def test_no_shot_chart_or_play_type(self):
        layout = _layout()
        for page in layout['pages']:
            for block in page['blocks']:
                self.assertNotEqual(block.get('type'), 'shot_chart')
                self.assertNotEqual(block.get('table_key'), 'play_type')
        self.assertEqual(len(layout['pages']), 5)

    def test_builtin_keys_are_allowlisted(self):
        layout = _layout()
        if report_layout is not None:
            self.assertNotIn('lineup_dict', report_layout.ALLOWED_TABLE_KEYS)
            self.assertEqual(
                report_layout.ALLOWED_TABLE_KEYS,
                ALLOWED_TABLE_KEYS,
            )
        for page in layout['pages']:
            for block in page['blocks']:
                self.assertIn(block['type'], ALLOWED_BLOCK_TYPES)
                if block['type'] == 'builtin_table':
                    self.assertIn(block['table_key'], ALLOWED_TABLE_KEYS)
                    self.assertNotEqual(block['table_key'], 'lineup_dict')

    def test_page_one_score_and_four_factors(self):
        self.assertEqual(
            set(_table_keys(_blocks(_layout(), 0))),
            {'score_group', 't_adv_df'},
        )
        texts = [b for b in _blocks(_layout(), 0) if b.get('type') == 'text']
        self.assertEqual(len(texts), 1)

    def test_page_two_team_and_key_only(self):
        self.assertEqual(
            set(_table_keys(_blocks(_layout(), 1))),
            {'t_df', 'k_df'},
        )

    def test_page_three_player_boxes(self):
        self.assertEqual(
            set(_table_keys(_blocks(_layout(), 2))),
            {'p_df_home', 'p_df_away'},
        )

    def test_page_four_lineup_home(self):
        self.assertEqual(
            set(_table_keys(_blocks(_layout(), 3))),
            {'lineup_home'},
        )

    def test_page_five_lineup_away(self):
        self.assertEqual(
            set(_table_keys(_blocks(_layout(), 4))),
            {'lineup_away'},
        )

    def test_page_two_leaves_whitespace(self):
        layout = _layout()
        page2 = _blocks(layout, 1)
        self.assertLess(_occupied_rows(page2), 12)
        self.assertNotIn('spacer', [b.get('type') for b in page2])
        self.assertTrue(any(b.get('type') == 'text' for b in page2))


class PaperAndStorageTests(unittest.TestCase):
    def test_a4_landscape_not_portrait(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertEqual(report_layout.A4_WIDTH_MM, 297)
        self.assertEqual(report_layout.A4_HEIGHT_MM, 210)
        self.assertGreater(report_layout.A4_WIDTH_MM, report_layout.A4_HEIGHT_MM)
        self.assertEqual(report_layout.GRID_COLUMNS, 12)

    def test_storage_key_includes_game_id(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertEqual(
            report_layout.layout_storage_key('abc'),
            'splashboard.report.layout.abc',
        )
        self.assertNotEqual(
            report_layout.layout_storage_key('abc'),
            report_layout.layout_storage_key('def'),
        )

    def test_missing_game_id_has_no_storage_key(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        with self.assertRaises(ValueError):
            report_layout.layout_storage_key('')
        with self.assertRaises(ValueError):
            report_layout.layout_storage_key(None)


class ImageUploadTests(unittest.TestCase):
    def test_accepts_raster_at_limit(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        for mime in ('image/jpeg', 'image/png', 'image/webp'):
            report_layout.validate_image_upload(mime=mime, size_bytes=1_000_000)

    def test_rejects_oversize(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        with self.assertRaises(ValueError):
            report_layout.validate_image_upload(mime='image/png', size_bytes=1_000_001)

    def test_rejects_svg_gif_and_empty(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        with self.assertRaises(ValueError):
            report_layout.validate_image_upload(mime='image/svg+xml', size_bytes=100)
        with self.assertRaises(ValueError):
            report_layout.validate_image_upload(mime='image/gif', size_bytes=100)
        with self.assertRaises(ValueError):
            report_layout.validate_image_upload(mime='image/png', size_bytes=0)


class ReadOnlyAndPdfContractTests(unittest.TestCase):
    def test_builtin_blocks_do_not_store_cell_values(self):
        layout = _layout()
        for page in layout['pages']:
            for block in page['blocks']:
                if block.get('type') == 'builtin_table':
                    self.assertNotIn('cells', block)
                    self.assertNotIn('cell_styles', block)

    def test_no_cell_style_api(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertFalse(hasattr(report_layout, 'set_cell_bold'))
        self.assertFalse(hasattr(report_layout, 'set_cell_background'))

    def test_pdf_export_is_landscape_a4_in_page_order(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        spec = report_layout.pdf_export_spec()
        self.assertEqual(spec['orientation'], 'landscape')
        self.assertEqual(spec['page_format'], 'a4')
        self.assertEqual(spec['page_order'], 'layout_pages')
        self.assertIn('report-toolbar', spec['no_print_selectors'])
        self.assertIn('report-page-list', spec['no_print_selectors'])
        self.assertIn('grid-stack-item-handle', spec['no_print_selectors'])
        self.assertIn('report-page-delete', spec['no_print_selectors'])
        self.assertIn('report-dialog', spec['no_print_selectors'])
        self.assertEqual(spec['filename'], 'match_date_yyyymmdd')
        self.assertEqual(spec['filename_fallback'], 'splashboard-report.pdf')
        self.assertEqual(spec['engine'], 'jspdf_dom')
        self.assertEqual(spec['text'], 'selectable')
        self.assertEqual(spec['visual'], 'approximate')
        self.assertEqual(spec['font'], 'Noto Sans TC')
        self.assertEqual(spec['font_url'], '/assets/NotoSansTC-Regular.ttf')
        self.assertTrue(spec['font_url'].startswith('/assets/'))
        self.assertTrue(spec['font_url'].endswith('.ttf'))
        self.assertNotIn('jsdelivr', spec['font_url'])
        self.assertEqual(spec['table_style'], 'as_on_screen')
        self.assertTrue(spec['rich_text_notes'])
        self.assertTrue(spec['nested_lists_support'])
        self.assertEqual(spec['image_format'], 'png')
        self.assertEqual(spec['fallback'], 'print')
        self.assertEqual(spec['export_busy'], 'disable_button')
        self.assertNotEqual(spec['engine'], 'html2canvas')

    def test_pdf_filename_uses_match_date(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertEqual(
            report_layout.pdf_filename({'date': '2026年04月11日'}),
            '20260411.pdf',
        )
        self.assertEqual(
            report_layout.pdf_filename({'date': '2026-04-11'}),
            '20260411.pdf',
        )
        self.assertEqual(report_layout.pdf_filename({}), 'splashboard-report.pdf')
        self.assertEqual(report_layout.pdf_filename(None), 'splashboard-report.pdf')


class ReportTableComponentTests(unittest.TestCase):
    def test_report_helper_is_dmc_not_ag_grid(self):
        from synergy_reporter import report_components
        self.assertFalse(hasattr(report_components, 'create_ag_grid'))
        self.assertTrue(hasattr(report_components, 'create_report_table'))

    def test_header_renders_two_lines_with_venue_after_time(self):
        from synergy_reporter.report_components import render_header
        header = render_header({
            'home_team': 'Braves',
            'away_team': 'Lions',
            'home_score': '88',
            'away_score': '79',
            'date': '2026年04月11日',
            'time': '17:00',
            'venue': 'Arena',
        })
        self.assertEqual(len(header.children), 2)
        title = header.children[0].children
        meta = header.children[1].children
        self.assertIn('Braves', title)
        self.assertIn('Lions', title)
        self.assertIn('88', title)
        self.assertIn('@', title)
        self.assertTrue(title.index('Lions') < title.index('@') < title.index('Braves'))
        self.assertIn('Arena', meta)
        self.assertIn('17:00', meta)
        self.assertIn('2026年04月11日', meta)
        self.assertNotIn('Arena', title)

    def test_toolbar_add_table_is_icon_menu(self):
        from synergy_reporter.report_components import render_toolbar
        toolbar = render_toolbar()
        markup = str(toolbar)
        self.assertIn('tabler:table', markup)
        self.assertIn('Add table', markup)
        self.assertIn('report-table-menu', markup)
        self.assertIn('Reset layout', markup)
        self.assertIn('tabler:restore', markup)
        self.assertNotIn('report-add-table-key', markup)
        self.assertNotIn('html.Select', markup)
        self.assertNotIn('Player Box', markup)
        player_pos = markup.find('Home Player Stats')
        lineup_pos = markup.find('Home Lineup Stats')
        self.assertGreater(player_pos, 0)
        self.assertGreater(lineup_pos, player_pos)

    def test_page_list_has_add_but_no_minus(self):
        from synergy_reporter.report_components import render_page_list
        page_list = render_page_list(4)
        markup = str(page_list)
        self.assertIn('report-add-page', markup)
        self.assertNotIn('report-remove-page', markup)
        self.assertNotIn('report-page-remove', markup)

    def test_empty_page_has_no_blocks(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        page = report_layout.empty_page('page-x')
        self.assertEqual(page['blocks'], [])

    def test_paper_has_no_page_number(self):
        from synergy_reporter.report_components import render_paper
        paper = render_paper(
            {'id': 'page-1', 'blocks': []},
            0, {}, {}, {}, 4,
        )
        markup = str(paper)
        self.assertNotIn('report-page-number', markup)

    def test_paper_has_corner_delete(self):
        from synergy_reporter.report_components import render_paper
        paper = render_paper(
            {'id': 'page-1', 'blocks': []},
            0, {}, {}, {}, 4,
        )
        markup = str(paper)
        self.assertIn('report-page-delete', markup)
        self.assertIn('data-delete-page', markup)
        self.assertIn('tabler:x', markup)

    def test_table_handle_is_in_title_row(self):
        from synergy_reporter.report_components import render_grid_item
        item = render_grid_item(
            {'id': 't1', 'type': 'builtin_table', 'table_key': 'k_df', 'x': 0, 'y': 0, 'w': 12, 'h': 3},
            {}, {}, {},
        )
        card = item.children
        row = next(
            child for child in card.children
            if getattr(child, 'className', '') == 'report-block-title-row'
        )
        self.assertEqual(row.children[0].className, 'grid-stack-item-handle no-print')
        self.assertEqual(row.children[1].className, 'report-block-title')

    def test_note_block_uses_tiptap_js_with_placeholder(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        chrome = report_layout.chrome_spec()
        self.assertEqual(chrome['notes_editor'], 'tiptap_js')
        self.assertEqual(chrome['notes_placeholder'], 'Notes')


class TableEngineAndChromeContractTests(unittest.TestCase):
    def test_report_uses_dmc_table_pbp_keeps_ag_grid(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        engine = report_layout.report_table_engine()
        self.assertEqual(engine['report'], 'dmc.Table')
        self.assertEqual(engine['play_by_play'], 'ag_grid')
        self.assertEqual(engine['box_score_summary'], 'dmc.Table')
        self.assertEqual(engine['player_stats'], 'ag_grid')
        self.assertEqual(engine['lineup'], 'ag_grid')
        self.assertEqual(engine['home'], 'ag_grid')

    def test_block_overflow_is_hidden(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertEqual(report_layout.block_overflow_spec(), 'hidden')
        self.assertNotEqual(report_layout.block_overflow_spec(), 'auto')
        self.assertNotEqual(report_layout.block_overflow_spec(), 'scroll')

    def test_toolbar_has_no_title_and_dash_iconify_icons(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        chrome = report_layout.chrome_spec()
        self.assertIsNone(chrome['toolbar_title'])
        self.assertEqual(chrome['icon_set'], 'dash-iconify')
        self.assertEqual(chrome['icon_scope'], 'app')
        self.assertEqual(chrome['add_note_icon'], 'tabler:notebook')
        self.assertEqual(chrome['add_image_icon'], 'tabler:photo')
        self.assertEqual(chrome['add_table_icon'], 'tabler:table')
        self.assertEqual(chrome['add_note_label'], 'Add note')
        self.assertEqual(chrome['add_image_label'], 'Add image')
        self.assertEqual(chrome['add_table_label'], 'Add table')
        self.assertEqual(chrome['add_table_control'], 'icon_menu')
        self.assertEqual(chrome['reset_icon'], 'tabler:restore')
        self.assertEqual(chrome['reset_label'], 'Reset layout')
        self.assertEqual(
            chrome['reset_confirm'],
            'Reset to the default layout? This cannot be undone.',
        )
        self.assertEqual(chrome['delete_confirm'], 'Delete this page?')
        self.assertEqual(chrome['dialog_cancel'], 'Cancel')
        self.assertEqual(chrome['dialog_reset'], 'Reset')
        self.assertEqual(chrome['dialog_delete'], 'Delete')
        self.assertEqual(chrome['page_delete'], 'paper_corner')
        self.assertEqual(chrome['page_delete_icon'], 'tabler:x')
        self.assertFalse(chrome['page_list_has_delete'])
        self.assertEqual(chrome['min_pages'], 1)
        self.assertEqual(chrome['toolbar_align'], 'paper')
        self.assertEqual(chrome['drag_handle'], 'title_left')
        self.assertEqual(chrome['note_drag_handle'], 'overlay')
        self.assertFalse(chrome['page_number'])
        self.assertEqual(chrome['notes_default_h'], 2)
        self.assertEqual(chrome['notes_resize'], 'content')
        self.assertEqual(chrome['notes_editor'], 'tiptap_js')
        self.assertEqual(chrome['notes_placeholder'], 'Notes')
        self.assertEqual(chrome['notes_content_format'], 'html')
        self.assertEqual(chrome['notes_toolbar_location'], 'report_toolbar')
        self.assertEqual(chrome['notes_toolbar_visibility'], 'on_focus')
        self.assertIn('Bold', chrome['notes_toolbar_controls'])
        self.assertIn('Italic', chrome['notes_toolbar_controls'])
        self.assertIn('Underline', chrome['notes_toolbar_controls'])
        self.assertIn('Strikethrough', chrome['notes_toolbar_controls'])
        self.assertIn('BulletList', chrome['notes_toolbar_controls'])
        self.assertIn('OrderedList', chrome['notes_toolbar_controls'])
        self.assertIn('ColorPicker', chrome['notes_toolbar_controls'])
        self.assertIn('Highlight', chrome['notes_toolbar_controls'])
        self.assertEqual(len(chrome['notes_toolbar_controls']), 8)
        self.assertEqual(
            chrome['notes_color_palette'],
            (
                '#e74c3c', '#e67e22', '#f1c40f', '#2ecc71',
                '#3498db', '#9b59b6', '#ffffff', '#000000',
            )
        )
        self.assertEqual(len(chrome['notes_color_palette']), 8)
        self.assertEqual(chrome['notes_palette_rows'], 1)
        self.assertTrue(chrome['notes_custom_color_picker'])
        self.assertTrue(chrome['notes_nested_lists'])
        self.assertEqual(chrome['notes_old_plain_text'], 'forward_compatible')
        self.assertEqual(chrome['notes_dynamic_mount'], 'tiptap_js')
        self.assertNotIn('mantine_provider_scope', chrome)
        self.assertEqual(chrome['header_size'], 'compact')
        self.assertEqual(chrome['header_line_gap'], 'loose')
        self.assertEqual(chrome['table_menu_order'], ALLOWED_TABLE_KEYS)
        self.assertIn('report-toolbar', chrome['sticky_selectors'])
        self.assertIn('report-page-list', chrome['sticky_selectors'])
        titles = list(report_layout.TABLE_TITLES.values())
        self.assertEqual(report_layout.TABLE_TITLES['p_df_home'], 'Home Player Stats')
        self.assertEqual(report_layout.TABLE_TITLES['p_df_away'], 'Away Player Stats')
        self.assertLess(titles.index('Home Player Stats'), titles.index('Home Lineup Stats'))

    def test_python_does_not_rebuild_on_layout_store(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        paint = report_layout.paint_spec()
        self.assertEqual(paint['python_inputs'], ('tabs',))
        self.assertEqual(
            paint['python_states'],
            ('bs_store', 'lineup_store', 'match_info_store', 'game_id'),
        )
        self.assertEqual(paint['lineup_precompute'], 'game_id_trigger_size5')
        self.assertFalse(paint['layout_store_rebuilds_pane'])
        self.assertEqual(paint['layout_mutations'], 'clientside')
        self.assertEqual(paint['add_table'], 'clone_template')
        self.assertEqual(paint['add_target'], 'current_page')
        self.assertEqual(paint['current_page'], 'scroll_spy')
        self.assertEqual(paint['place'], 'auto')
        self.assertEqual(paint['page_full'], 'no_fit')
        self.assertEqual(paint['overflow_page'], 'add_page')
        self.assertTrue(paint['grid_fills_paper'])
        self.assertEqual(paint['new_page_blocks'], ())
        self.assertEqual(paint['table_block_height'], 'fit_content_with_handle')
        self.assertEqual(paint['fit_batch'], 'read_then_write')
        self.assertEqual(paint['compact'], 'first_paint_and_reset')
        self.assertEqual(paint['report_tab'], 'finished_only')
        self.assertEqual(paint['player_stats_sort'], '+/-_desc')
        self.assertEqual(paint['image_validate'], 'clientside')
        self.assertNotIn('report_layout_store', paint['python_inputs'])
        self.assertNotIn('lineup_store', paint['python_inputs'])

    def test_header_is_two_lines_with_venue_after_time(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        header = report_layout.header_spec()
        self.assertEqual(header['lines'], 2)
        self.assertEqual(
            header['line_1_fields'],
            ('away', 'away_score', '@', 'home_score', 'home'),
        )
        self.assertEqual(header['score_separator'], '@')
        self.assertEqual(header['line_2_fields'], ('date', 'time', 'venue'))
        self.assertEqual(header['venue_placement'], 'after_time')
        self.assertEqual(header['height'], 'taller')
        self.assertEqual(header['type_size'], 'smaller')
        self.assertFalse(header['draggable'])


class ReportTabAndPlayerSortTests(unittest.TestCase):
    def test_report_tab_only_for_finished_games(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertTrue(report_layout.report_tab_is_visible('FINISHED'))
        self.assertTrue(report_layout.report_tab_is_visible(' CONFIRMED '))
        self.assertFalse(report_layout.report_tab_is_visible('IN_PROGRESS'))
        self.assertFalse(report_layout.report_tab_is_visible('PENDING'))
        self.assertFalse(report_layout.report_tab_is_visible(''))
        self.assertFalse(report_layout.report_tab_is_visible(None))

    def test_report_player_stats_sort_by_plus_minus_desc(self):
        import pandas as pd
        from synergy_reporter.report_components import sort_player_stats_for_report
        df = pd.DataFrame({
            'Player': ['A', 'B', 'C', 'D', 'E'],
            '#': ['12', '5', '7', '3', '1'],
            'S': ['○', '', '○', '', ''],
            'Min': ['20:00', '18:00', 'DNP', '12:00', '8:00'],
            'PTS': [20, 8, 0, 8, 8],
            '+/-': [1, 9, 4, 9, 9],
        })
        sorted_df = sort_player_stats_for_report(df)
        self.assertEqual(list(sorted_df['Player']), ['E', 'D', 'B', 'A', 'C'])
        self.assertEqual(list(sorted_df['+/-']), [9, 9, 9, 1, 4])

    def test_bundled_pdf_font_exists(self):
        import os
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        font_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'assets',
            'NotoSansTC-Regular.ttf',
        )
        self.assertTrue(os.path.isfile(font_path))
        self.assertGreater(os.path.getsize(font_path), 100000)


class DmcInfrastructureContractTests(unittest.TestCase):
    def test_requirements_declares_dmc(self):
        import os
        req_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'requirements.txt')
        with open(req_path, 'r') as f:
            content = f.read()
        self.assertIn('dash-mantine-components==2.8.0', content)
        self.assertIn('dash-iconify', content)

    def test_app_uses_react_18_and_mantine_provider_without_dbc_theme(self):
        import os
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
        with open(app_path, 'r') as f:
            code = f.read()
        self.assertIn("_set_react_version('18.2.0')", code)
        self.assertIn('MantineProvider', code)
        self.assertIn('forceColorScheme="light"', code)
        self.assertNotIn('dbc.themes.LITERA', code)
        self.assertNotIn('dbc.themes.FLATLY', code)
        self.assertNotIn('bootstrap-icons', code)
        self.assertIn('AppShell', code)
        self.assertIn('AppShellHeader', code)
        self.assertIn('AppShellMain', code)


class NavbarDmcContractTests(unittest.TestCase):
    def test_navbar_does_not_import_dbc(self):
        import os
        nav_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'navbar.py')
        with open(nav_path, 'r') as f:
            code = f.read()
        self.assertNotIn('import dash_bootstrap_components', code)
        self.assertNotIn('import dbc', code)
        self.assertNotIn('dbc.Navbar', code)

    def test_create_navbar_renders_dmc_with_brand_and_menu(self):
        from navbar import create_navbar
        nav = create_navbar()
        markup = str(nav)
        self.assertIn('Splashboard', markup)
        self.assertIn('TFB', markup)
        self.assertIn('Home', markup)


class TableDmcAndAgGridContractTests(unittest.TestCase):
    def test_no_dbc_table_across_pages_and_components(self):
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        targets = [
            os.path.join(base_dir, 'pages', 'home.py'),
            os.path.join(base_dir, 'pages', 'game.py'),
            os.path.join(base_dir, 'synergy_reporter', 'report_components.py'),
        ]
        for path in targets:
            with open(path, 'r') as f:
                code = f.read()
            self.assertNotIn('dbc.Table', code, f"{path} should not contain dbc.Table")

    def test_game_page_uses_ag_grid_for_player_and_lineup(self):
        import os
        game_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', 'game.py')
        with open(game_path, 'r') as f:
            code = f.read()
        self.assertIn('dag.AgGrid', code)
        self.assertIn('domLayout', code)

    def test_home_page_does_not_use_ag_grid(self):
        import os
        home_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', 'home.py')
        with open(home_path, 'r') as f:
            code = f.read()
        self.assertNotIn('dag.AgGrid', code)
        self.assertNotIn('dash_ag_grid', code)


class DbcEliminationContractTests(unittest.TestCase):
    def test_requirements_does_not_declare_dbc(self):
        import os
        req_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'requirements.txt')
        with open(req_path, 'r') as f:
            content = f.read()
        self.assertNotIn('dash-bootstrap-components', content)

    def test_no_python_file_imports_dbc(self):
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        py_files = []
        for root, _, files in os.walk(base_dir):
            if any(part.startswith('.') or part in ('venv', '__pycache__', 'scratch') for part in root.split(os.sep)):
                continue
            for file in files:
                if file.endswith('.py') and not file.startswith('test_'):
                    py_files.append(os.path.join(root, file))
        for path in py_files:
            with open(path, 'r') as f:
                code = f.read()
            self.assertNotIn('import dash_bootstrap_components', code, f"{path} should not import dash_bootstrap_components")
            self.assertNotIn('import dbc', code, f"{path} should not import dbc")


class AlignmentAndRwdContractTests(unittest.TestCase):
    def test_css_defines_rwd_media_queries_and_alignment_rules(self):
        import os
        css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'report.css')
        with open(css_path, 'r') as f:
            css = f.read()
        self.assertIn('@media (max-width: 768px)', css)
        self.assertIn('@media (max-width: 1024px) and (min-width: 769px)', css)
        self.assertIn('overflow-x: auto', css)
        self.assertIn('scrollbar-width: none', css)
        self.assertIn('ag-header-align-center', css)
        self.assertIn('ag-cell-align-center', css)
        self.assertIn('justify-content: center', css)
        self.assertIn('.app-shell', css)
        self.assertIn('--app-shell-header-offset: 0px', css)
        self.assertIn('position: relative !important', css)
        self.assertIn('.braves-table-scroll', css)
        self.assertIn('position: sticky', css)
        self.assertIn('cursor: grab', css)
        self.assertIn('cursor: grabbing', css)
        self.assertIn('.is-scrollable', css)
        self.assertIn('.braves-lineup-grid', css)
        self.assertIn('160px', css)

    def test_home_page_column_alignments(self):
        import os
        home_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages', 'home.py')
        with open(home_path, 'r') as f:
            code = f.read()
        self.assertNotIn('rightAligned', code)
        self.assertNotIn('dag.AgGrid', code)


class StatsMultiLevelHeaderAndTeamSummaryContractTests(unittest.TestCase):
    def test_box_score_column_defs_structure_and_order(self):
        from pages.game import _build_stats_column_defs
        cols = [
            '#', 'Player', 'S', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
            'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BL',
            'PF', 'FD', 'PTS', 'eFG%', 'USG%', 'PM'
        ]
        cdefs = _build_stats_column_defs(cols)
        
        # Check leading pinned columns: #, Player, S (all center)
        self.assertEqual(cdefs[0]['field'], '#')
        self.assertEqual(cdefs[0]['pinned'], 'left')
        self.assertEqual(cdefs[0]['headerClass'], 'ag-header-align-center')
        self.assertEqual(cdefs[0]['cellClass'], 'ag-cell-align-center')

        self.assertEqual(cdefs[1]['field'], 'Player')
        self.assertEqual(cdefs[1]['pinned'], 'left')
        self.assertEqual(cdefs[1]['headerClass'], 'ag-header-align-center')
        self.assertEqual(cdefs[1]['cellClass'], 'ag-cell-align-center')
        self.assertEqual(cdefs[1]['width'], 95)

        self.assertEqual(cdefs[2]['field'], 'S')
        self.assertEqual(cdefs[2]['pinned'], 'left')
        self.assertEqual(cdefs[2]['headerClass'], 'ag-header-align-center')
        self.assertEqual(cdefs[2]['cellClass'], 'ag-cell-align-center')
        
        # Check Min & +/- are center-aligned
        self.assertEqual(cdefs[3]['field'], 'Min')
        self.assertEqual(cdefs[3]['headerClass'], 'ag-header-align-center')
        self.assertEqual(cdefs[3]['cellClass'], 'ag-cell-align-center')
        self.assertEqual(cdefs[4]['field'], '+/-')
        self.assertEqual(cdefs[4]['headerClass'], 'ag-header-align-center')
        self.assertEqual(cdefs[4]['cellClass'], 'ag-cell-align-center')

        # Check groups: 2PT, 3PT, FT, REB
        group_headers = [c.get('headerName') for c in cdefs if 'children' in c]
        self.assertEqual(group_headers, ['2PT', '3PT', 'FT', 'REB'])

        # Check 2PT children: M, A, %, all center-aligned
        group_2pt = next(c for c in cdefs if c.get('headerName') == '2PT')
        child_fields_2pt = [ch['field'] for ch in group_2pt['children']]
        self.assertEqual(child_fields_2pt, ['2M', '2A', '2FG%'])
        for group_name in ('2PT', '3PT', 'FT', 'REB'):
            group = next(c for c in cdefs if c.get('headerName') == group_name)
            for ch in group['children']:
                self.assertTrue(ch['sortable'])
                self.assertEqual(ch['headerClass'], 'ag-header-align-center')
                self.assertEqual(ch['cellClass'], 'ag-cell-align-center')

        # Check REB children: O, D, T
        group_reb = next(c for c in cdefs if c.get('headerName') == 'REB')
        child_fields_reb = [ch['field'] for ch in group_reb['children']]
        self.assertEqual(child_fields_reb, ['OR', 'DR', 'REB'])
        child_headers_reb = [ch['headerName'] for ch in group_reb['children']]
        self.assertEqual(child_headers_reb, ['O', 'D', 'T'])

        # Check tail standalone columns order: AST, TO, ST, BL, PF, FD, PTS, eFG%, USG%, PM
        tail_cols = [c['field'] for c in cdefs if 'field' in c and c['field'] not in ('#', 'Player', 'S', 'Min', '+/-')]
        self.assertEqual(tail_cols, ['AST', 'TO', 'ST', 'BL', 'PF', 'FD', 'PTS', 'eFG%', 'USG%', 'PM'])
        for c in cdefs:
            if 'field' in c and c['field'] in tail_cols:
                self.assertEqual(c['headerClass'], 'ag-header-align-center')
                self.assertEqual(c['cellClass'], 'ag-cell-align-center')

    def test_lineup_column_defs_structure_and_order(self):
        from pages.game import _build_stats_column_defs
        cols = [
            'Lineup', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
            'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BL',
            'PF', 'FD', 'PTS', 'eFG%', 'PM'
        ]
        cdefs = _build_stats_column_defs(cols, lineup_size=5)
        self.assertEqual(cdefs[0]['field'], 'Lineup')
        self.assertEqual(cdefs[0]['pinned'], 'left')
        self.assertEqual(cdefs[0]['headerClass'], 'ag-header-align-center')
        self.assertEqual(cdefs[0]['cellClass'], 'ag-cell-align-center')
        self.assertEqual(cdefs[0]['minWidth'], 260)
        self.assertEqual(cdefs[0]['width'], 270)
        self.assertNotIn('flex', cdefs[0])
        self.assertTrue(cdefs[0].get('wrapText'))
        self.assertTrue(cdefs[0].get('autoHeight'))
        two = _build_stats_column_defs(cols, lineup_size=2)
        self.assertEqual(two[0]['minWidth'], 140)
        self.assertEqual(two[0]['width'], 150)
        for cdef in cdefs:
            if 'field' in cdef:
                self.assertEqual(cdef['headerClass'], 'ag-header-align-center')
                self.assertEqual(cdef['cellClass'], 'ag-cell-align-center')
            for ch in cdef.get('children') or []:
                self.assertEqual(ch['headerClass'], 'ag-header-align-center')
                self.assertEqual(ch['cellClass'], 'ag-cell-align-center')
        tail_cols = [c['field'] for c in cdefs if 'field' in c and c['field'] not in ('Lineup', 'Min', '+/-')]
        self.assertEqual(tail_cols, ['AST', 'TO', 'ST', 'BL', 'PF', 'FD', 'PTS', 'eFG%', 'PM'])

    def test_dmc_table_from_df_group_headers_and_alignments(self):
        from pages.game import _dmc_table_from_df
        import pandas as pd
        df = pd.DataFrame([{
            'Team': 'Taipei Fubon Braves', 'Min': '265:00',
            '2M': 26, '2A': 44, '2FG%': '59.1%',
            '3M': 8, '3A': 34, '3FG%': '23.5%',
            'FTM': 21, 'FTA': 37, 'FT%': '56.8%',
            'OR': 16, 'DR': 42, 'REB': 58,
            'AST': 18, 'TO': 23, 'ST': 12, 'BL': 5, 'PF': 24, 'FD': 29, 'PTS': 97
        }])
        card = _dmc_table_from_df(df, is_team_summary=True)
        # Verify component contains dmc.Table with Thead containing 2 rows (group header + sub header)
        tbl = card.children if hasattr(card, 'children') and not isinstance(card.children, list) else card
        # Find the dmc.Table inside
        import dash_mantine_components as dmc
        def _find_dmc_table(node):
            if isinstance(node, dmc.Table):
                return node
            if hasattr(node, 'children'):
                ch = node.children
                if isinstance(ch, list):
                    for c in ch:
                        res = _find_dmc_table(c)
                        if res:
                            return res
                else:
                    return _find_dmc_table(ch)
            return None
        dmc_tbl = _find_dmc_table(card)
        self.assertIsNotNone(dmc_tbl)
        thead = dmc_tbl.children[0]
        # Thead has 2 Tr rows
        self.assertEqual(len(thead.children), 2)
        top_row = thead.children[0]
        sub_row = thead.children[1]
        top_titles = [th.children for th in top_row.children]
        self.assertIn('TEAM', top_titles)
        self.assertIn('2PT', top_titles)
        self.assertIn('3PT', top_titles)
        self.assertIn('FT', top_titles)
        self.assertIn('REB', top_titles)
        self.assertIn('AST', top_titles)
        self.assertIn('FD', top_titles)
        sub_titles = [th.children for th in sub_row.children]
        self.assertEqual(sub_titles, ['M', 'A', '%', 'M', 'A', '%', 'M', 'A', '%', 'O', 'D', 'T'])

        def walk(node):
            yield node
            ch = getattr(node, 'children', None)
            if isinstance(ch, (list, tuple)):
                for child in ch:
                    yield from walk(child)
            elif ch is not None:
                yield from walk(ch)

        for node in walk(dmc_tbl):
            if isinstance(node, (dmc.TableTh, dmc.TableTd)):
                self.assertEqual(node.style.get('textAlign'), 'center')

    def test_dmc_table_winner_color_and_team_stripe(self):
        from pages.game import _dmc_table_from_df
        import pandas as pd
        import dash_mantine_components as dmc
        df = pd.DataFrame([
            {'Team': 'Home', 'PTS': 88},
            {'Team': 'Away', 'PTS': 79},
        ])
        card = _dmc_table_from_df(df, is_team_summary=True)

        def walk(node):
            yield node
            ch = getattr(node, 'children', None)
            if isinstance(ch, (list, tuple)):
                for child in ch:
                    yield from walk(child)
            elif ch is not None:
                yield from walk(ch)

        tds = [n for n in walk(card) if isinstance(n, dmc.TableTd)]
        pts_home = next(td for td in tds if td.children == '88')
        pts_away = next(td for td in tds if td.children == '79')
        self.assertEqual(pts_home.style.get('color'), '#0077b6')
        self.assertEqual(pts_home.style.get('fontWeight'), 700)
        self.assertEqual(pts_away.style.get('color'), '#1e293b')
        team_home = next(td for td in tds if td.children == 'Home')
        team_away = next(td for td in tds if td.children == 'Away')
        self.assertEqual(team_home.style.get('borderLeft'), '3.5px solid #0077b6')
        self.assertEqual(team_away.style.get('borderLeft'), '3.5px solid #94a3b8')








