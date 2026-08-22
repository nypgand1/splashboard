# -*- coding: utf-8 -*-
"""Report canvas layout model. No Dash, no disk I/O."""

import re

A4_WIDTH_MM = 297
A4_HEIGHT_MM = 210
GRID_COLUMNS = 12
LAYOUT_VERSION = 1
STORAGE_KEY_PREFIX = 'splashboard.report.layout.'
IMAGE_MAX_BYTES = 1_000_000
ALLOWED_IMAGE_MIMES = frozenset({'image/jpeg', 'image/png', 'image/webp'})
PDF_FILENAME_FALLBACK = 'splashboard-report.pdf'
REPORT_TAB_STATUSES = frozenset({'FINISHED', 'CONFIRMED'})


def report_tab_is_visible(status):
    if status is None:
        return False
    return str(status).strip() in REPORT_TAB_STATUSES

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
TABLE_TITLES = {
    'score_group': 'Score',
    't_adv_df': 'Pace, PPP & Four Factors',
    't_df': 'Team Stats',
    'k_df': 'Key Stats',
    'p_df_home': 'Home Player Stats',
    'p_df_away': 'Away Player Stats',
    'lineup_home': 'Home Lineup Stats',
    'lineup_away': 'Away Lineup Stats',
}


def layout_storage_key(game_id):
    if game_id is None:
        raise ValueError('game_id is required')
    key = str(game_id).strip()
    if not key:
        raise ValueError('game_id is required')
    return STORAGE_KEY_PREFIX + key


def validate_image_upload(mime, size_bytes):
    if not mime or mime not in ALLOWED_IMAGE_MIMES:
        raise ValueError('unsupported image type')
    try:
        size = int(size_bytes)
    except (TypeError, ValueError):
        raise ValueError('invalid image size')
    if size <= 0:
        raise ValueError('empty image')
    if size > IMAGE_MAX_BYTES:
        raise ValueError('image exceeds 1MB')


def pdf_filename(match_info=None):
    date = ((match_info or {}).get('date') or '')
    digits = re.sub(r'\D', '', str(date))
    if len(digits) >= 8:
        return digits[:8] + '.pdf'
    return PDF_FILENAME_FALLBACK


def pdf_export_spec():
    return {
        'orientation': 'landscape',
        'page_format': 'a4',
        'page_order': 'layout_pages',
        'filename': 'match_date_yyyymmdd',
        'filename_fallback': PDF_FILENAME_FALLBACK,
        'engine': 'jspdf_dom',
        'text': 'selectable',
        'visual': 'approximate',
        'font': 'Noto Sans TC',
        'font_url': '/assets/NotoSansTC-Regular.ttf',
        'table_style': 'as_on_screen',
        'image_format': 'png',
        'fallback': 'print',
        'export_busy': 'disable_button',
        'no_print_selectors': [
            'report-toolbar',
            'report-page-list',
            'grid-stack-item-handle',
            'report-page-delete',
            'report-dialog',
        ],
    }


def report_table_engine():
    return {
        'report': 'dbc.Table',
        'play_by_play': 'ag_grid',
        'box_score': 'dbc.Table',
        'lineup': 'dbc.Table',
        'home': 'dbc.Table',
    }


def block_overflow_spec():
    return 'hidden'


def chrome_spec():
    return {
        'toolbar_title': None,
        'icon_set': 'bootstrap-icons',
        'icon_scope': 'report_chrome',
        'add_note_icon': 'bi-journal-text',
        'add_image_icon': 'bi-image',
        'add_table_icon': 'bi-table',
        'add_note_label': 'Add note',
        'add_image_label': 'Add image',
        'add_table_label': 'Add table',
        'add_table_control': 'icon_menu',
        'reset_icon': 'bi-arrow-counterclockwise',
        'reset_label': 'Reset layout',
        'reset_confirm': 'Reset to the default layout? This cannot be undone.',
        'delete_confirm': 'Delete this page?',
        'dialog_cancel': 'Cancel',
        'dialog_reset': 'Reset',
        'dialog_delete': 'Delete',
        'page_delete': 'paper_corner',
        'page_delete_icon': 'bi-x-lg',
        'page_list_has_delete': False,
        'min_pages': 1,
        'toolbar_align': 'paper',
        'drag_handle': 'title_left',
        'note_drag_handle': 'overlay',
        'page_number': False,
        'notes_default_h': 2,
        'notes_resize': 'content',
        'notes_editor': 'contenteditable',
        'notes_placeholder': 'Notes',
        'header_size': 'compact',
        'header_line_gap': 'loose',
        'sticky_selectors': ['report-toolbar', 'report-page-list'],
        'table_menu_order': ALLOWED_TABLE_KEYS,
    }


def header_spec():
    return {
        'lines': 2,
        'line_1_fields': ('away', 'away_score', '@', 'home_score', 'home'),
        'line_2_fields': ('date', 'time', 'venue'),
        'venue_placement': 'after_time',
        'score_separator': '@',
        'height': 'taller',
        'type_size': 'smaller',
        'draggable': False,
    }


def paint_spec():
    return {
        'python_inputs': ('tabs', 'lineup_store'),
        'layout_store_rebuilds_pane': False,
        'layout_mutations': 'clientside',
        'add_table': 'clone_template',
        'add_target': 'current_page',
        'current_page': 'scroll_spy',
        'place': 'auto',
        'page_full': 'no_fit',
        'overflow_page': 'add_page',
        'grid_fills_paper': True,
        'table_block_height': 'fit_content_with_handle',
        'compact': 'first_paint_and_reset',
        'report_tab': 'finished_only',
        'player_stats_sort': '+/-_desc',
        'new_page_blocks': (),
        'image_validate': 'clientside',
    }


def _block(block_id, block_type, x, y, w, h, **extra):
    item = {
        'id': block_id,
        'type': block_type,
        'x': x,
        'y': y,
        'w': w,
        'h': h,
    }
    item.update(extra)
    return item


def _table(block_id, table_key, x, y, w, h):
    return _block(block_id, 'builtin_table', x, y, w, h, table_key=table_key)


def _text(block_id, x, y, w, h):
    return _block(block_id, 'text', x, y, w, h, content='')


def default_layout(match_info=None):
    del match_info
    return {
        'version': LAYOUT_VERSION,
        'pages': [
            {
                'id': 'page-1',
                'blocks': [
                    _table('p1-score', 'score_group', 0, 0, 7, 3),
                    _text('p1-notes', 7, 0, 5, 2),
                    _table('p1-four', 't_adv_df', 0, 3, GRID_COLUMNS, 3),
                ],
            },
            {
                'id': 'page-2',
                'blocks': [
                    _table('p2-team', 't_df', 0, 0, GRID_COLUMNS, 3),
                    _table('p2-key', 'k_df', 0, 3, GRID_COLUMNS, 3),
                    _text('p2-notes', 0, 6, GRID_COLUMNS, 2),
                ],
            },
            {
                'id': 'page-3',
                'blocks': [
                    _table('p3-home', 'p_df_home', 0, 0, GRID_COLUMNS, 5),
                    _table('p3-away', 'p_df_away', 0, 5, GRID_COLUMNS, 5),
                    _text('p3-notes', 0, 10, GRID_COLUMNS, 2),
                ],
            },
            {
                'id': 'page-4',
                'blocks': [
                    _table('p4-home', 'lineup_home', 0, 0, GRID_COLUMNS, 5),
                    _text('p4-notes', 0, 5, GRID_COLUMNS, 2),
                ],
            },
            {
                'id': 'page-5',
                'blocks': [
                    _table('p5-away', 'lineup_away', 0, 0, GRID_COLUMNS, 5),
                    _text('p5-notes', 0, 5, GRID_COLUMNS, 2),
                ],
            },
        ],
    }


def empty_page(page_id):
    return {
        'id': page_id,
        'blocks': [],
    }


def normalize_layout(layout):
    if not isinstance(layout, dict) or not layout.get('pages'):
        return default_layout()
    pages = layout.get('pages') or []
    if not pages:
        return default_layout()
    return {
        'version': LAYOUT_VERSION,
        'pages': pages,
    }
