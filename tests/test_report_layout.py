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
    def test_report_helper_is_dbc_not_ag_grid(self):
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
        self.assertIn('bi-table', markup)
        self.assertIn('Add table', markup)
        self.assertIn('report-table-menu', markup)
        self.assertIn('Reset layout', markup)
        self.assertIn('bi-arrow-counterclockwise', markup)
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
        self.assertIn('bi-x-lg', markup)

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
    def test_report_uses_dbc_table_pbp_keeps_ag_grid(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        engine = report_layout.report_table_engine()
        self.assertEqual(engine['report'], 'dbc.Table')
        self.assertEqual(engine['play_by_play'], 'ag_grid')
        self.assertEqual(engine['box_score'], 'dbc.Table')
        self.assertEqual(engine['lineup'], 'dbc.Table')
        self.assertEqual(engine['home'], 'dbc.Table')

    def test_block_overflow_is_hidden(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        self.assertEqual(report_layout.block_overflow_spec(), 'hidden')
        self.assertNotEqual(report_layout.block_overflow_spec(), 'auto')
        self.assertNotEqual(report_layout.block_overflow_spec(), 'scroll')

    def test_toolbar_has_no_title_and_bootstrap_icons(self):
        if report_layout is None:
            raise unittest.SkipTest('synergy_reporter.report_layout is not implemented')
        chrome = report_layout.chrome_spec()
        self.assertIsNone(chrome['toolbar_title'])
        self.assertEqual(chrome['icon_set'], 'bootstrap-icons')
        self.assertEqual(chrome['icon_scope'], 'report_chrome')
        self.assertEqual(chrome['add_note_icon'], 'bi-journal-text')
        self.assertEqual(chrome['add_image_icon'], 'bi-image')
        self.assertEqual(chrome['add_table_icon'], 'bi-table')
        self.assertEqual(chrome['add_note_label'], 'Add note')
        self.assertEqual(chrome['add_image_label'], 'Add image')
        self.assertEqual(chrome['add_table_label'], 'Add table')
        self.assertEqual(chrome['add_table_control'], 'icon_menu')
        self.assertEqual(chrome['reset_icon'], 'bi-arrow-counterclockwise')
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
        self.assertEqual(chrome['page_delete_icon'], 'bi-x-lg')
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
            'Player': ['A', 'B', 'C'],
            'PTS': [20, 8, 12],
            '+/-': [1, 9, -2],
        })
        sorted_df = sort_player_stats_for_report(df)
        self.assertEqual(list(sorted_df['Player']), ['B', 'A', 'C'])
        self.assertEqual(list(sorted_df['+/-']), [9, 1, -2])

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
