# -*- coding: utf-8 -*-
"""Report canvas layout model. No Dash, no disk I/O."""

import re

A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297
GRID_COLUMNS = 12
LAYOUT_VERSION = 2
STORAGE_KEY_PREFIX = 'splashboard.report.layout.'
IMAGE_MAX_BYTES = 1_000_000
ALLOWED_IMAGE_MIMES = frozenset({'image/jpeg', 'image/png', 'image/webp'})
PDF_FILENAME_FALLBACK = 'splashboard-report.pdf'
REPORT_TAB_STATUSES = frozenset({'FINISHED', 'CONFIRMED'})
REPORT_DESKTOP_MIN_PX = 1280


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
ALLOWED_BLOCK_TYPES = ('builtin_table', 'text', 'image', 'rotation')
ROTATION_TITLE = 'Rotation'
ROTATION_DEFAULT_H = 11
ROTATION_EMPTY = 'No rotation chart for this game.'
ROTATION_ERROR = 'Could not load rotation.'


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
        'orientation': 'portrait',
        'page_format': 'a4',
        'page_order': 'layout_pages',
        'title_dot': 'filled_circle',
        'starter_s': 'stroked_circle',
        'filename': 'match_date_yyyymmdd',
        'filename_fallback': PDF_FILENAME_FALLBACK,
        'engine': 'jspdf_dom',
        'text': 'selectable',
        'visual': 'approximate',
        'font': 'Noto Sans TC',
        'font_url': '/assets/NotoSansTC-Regular.ttf',
        'font_styles': ('normal',),
        'scale': 'axis_separate',
        'cell_text_baseline': 'middle',
        'bold': 'offset_duplicate',
        'bold_offset_mm': 0.15,
        'bold_min_weight': 600,
        'table_style': 'as_on_screen',
        'rich_text_notes': True,
        'nested_lists_support': True,
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


def report_header_groups_spec():
    return {
        'shot_groups': ('2PT', '3PT', 'FT', 'REB'),
        'four_factors_label': '4 FACTORS',
        'four_factors_keys': ('eFG%', 'TOV%', 'ORB%', 'FT-R'),
        'four_factors_tables': ('t_adv_df',),
        'no_four_factors_tables': ('p_df_home', 'p_df_away', 'lineup_home', 'lineup_away'),
    }


def report_table_engine():
    return {
        'report': 'html_table_js',
        'play_by_play': 'ag_grid',
        'box_score_summary': 'dmc.Table',
        'player_stats': 'ag_grid',
        'lineup': 'ag_grid',
        'home': 'ag_grid',
    }


def block_overflow_spec():
    return 'hidden'


def chrome_spec():
    return {
        'toolbar_title': None,
        'icon_set': 'dash-iconify',
        'icon_scope': 'app',
        'add_note_icon': 'tabler:notebook',
        'add_image_icon': 'tabler:photo',
        'add_table_icon': 'tabler:table',
        'add_rotation_icon': 'tabler:chart-bar',
        'add_note_label': 'Add note',
        'add_image_label': 'Add image',
        'add_table_label': 'Add table',
        'add_rotation_label': 'Add rotation',
        'rotation_resize': False,
        'rotation_title': None,
        'rotation_scale': 0.75,
        'rotation_drag_handle': 'overlay',
        'rotation_camera': 'all_no_dnp_no_playhead',
        'rotation_place': 'native_or_new_page',
        'rotation_empty': ROTATION_EMPTY,
        'rotation_error': ROTATION_ERROR,
        'add_table_control': 'icon_menu',
        'editor_chrome': 'dmc',
        'dialog': 'dmc.Modal',
        'sticky_top_px': 8,
        'page_list_align': 'paper_top',
        'page_list_sticky': 'toolbar_plus_gap',
        'overflow_chrome': 'paper_ring',
        'overflow_color': '#e63946',
        'overflow_ring_px': 2,
        'overflow_detect': 'item_box_vs_paper',
        'pdf_overflow': 'confirm_modal',
        'pdf_overflow_confirm': 'This export will crop content that sits outside A4.',
        'pdf_overflow_ok': 'Export',
        'resize_handles': 'se',
        'image_place': 'natural_or_max_remaining',
        'image_aspect': 'lock',
        'table_min_size': 'max_content',
        'block_place': 'clamp_to_paper',
        'oversized_drag': 'x_only_y0',
        'notes_enter_overflow': 'reject',
        'notes_edit_overflow': 'reject',
        'pdf_text_test': 'marker_pdf_text',
        'resize_max': 'remaining_paper',
        'reset_icon': 'tabler:restore',
        'reset_label': 'Reset layout',
        'reset_confirm': 'Reset to the default layout? This cannot be undone.',
        'delete_confirm': 'Delete this page?',
        'dialog_cancel': 'Cancel',
        'dialog_reset': 'Reset',
        'dialog_delete': 'Delete',
        'page_delete': 'paper_corner',
        'page_delete_icon': 'tabler:x',
        'page_list_has_delete': False,
        'min_pages': 1,
        'default_pages': 4,
        'toolbar_align': 'paper',
        'drag_handle': 'title_left',
        'note_drag_handle': 'overlay',
        'page_number': False,
        'notes_default_h': 2,
        'notes_min_h': 1,
        'notes_resize': 'content',
        'notes_preserve_w': True,
        'notes_editor': 'execCommand',
        'notes_placeholder': 'Notes',
        'notes_content_format': 'html',
        'notes_toolbar_location': 'report_toolbar',
        'notes_toolbar_visibility': 'on_focus',
        'notes_toolbar_controls': (
            'Bold', 'Italic', 'Underline', 'Strikethrough',
            'BulletList', 'OrderedList', 'ColorPicker', 'Highlight',
        ),
        'notes_color_palette': (
            '#e74c3c', '#e67e22', '#f1c40f', '#2ecc71',
            '#3498db', '#9b59b6', '#ffffff', '#000000',
        ),
        'notes_palette_rows': 1,
        'notes_custom_color_picker': True,
        'notes_nested_lists': True,
        'notes_old_plain_text': 'forward_compatible',
        'notes_dynamic_mount': 'execCommand',
        'header_size': 'compact',
        'header_line_gap': 'loose',
        'sticky_selectors': ['report-toolbar', 'report-page-list'],
        'table_menu_order': ALLOWED_TABLE_KEYS,
        'rail_bg': '#f1f5f9',
        'rail_button_bg': '#ffffff',
        'rail_blur': False,
        'rail_accent': '#00b4d8',
        'rail_shadow': '0 8px 24px rgba(15, 23, 42, 0.12)',
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
        'python_inputs': ('tabs', 'report-pane-ready'),
        'python_states': (
            'bs_store',
            'lineup_store',
            'match_info_store',
            'game_id',
        ),
        'pane_rebuild': 'first_open_or_empty',
        'lineup_precompute': 'game_id_trigger_size5',
        'layout_store_rebuilds_pane': False,
        'layout_mutations': 'split',
        'page_shells': 'python_cmd_patch',
        'page_list_output': 'buttons_only',
        'add_table': 'js_from_store',
        'add_target': 'current_page',
        'current_page': 'scroll_spy',
        'place': 'auto',
        'page_full': 'no_fit',
        'overflow_page': 'add_page',
        'grid_fills_paper': True,
        'table_block_height': 'fit_content_with_handle',
        'fit_batch': 'read_then_write',
        'compact': 'first_paint_and_reset',
        'hydrate': 'active_page',
        'python_paint': 'shell',
        'hidden_table_templates': False,
        'lineup_rows': 'paint_all',
        'report_tab': 'finished_and_desktop',
        'desktop_min_px': REPORT_DESKTOP_MIN_PX,
        'player_stats_sort': '+/-_desc',
        'new_page_blocks': (),
        'image_validate': 'clientside',
        'rotation_figure': 'workspace_json',
        'rotation_store_on_load': True,
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


def _rotation(block_id, x, y, w, h):
    return _block(block_id, 'rotation', x, y, w, h)


def default_layout(match_info=None):
    del match_info
    half = GRID_COLUMNS // 2
    return {
        'version': LAYOUT_VERSION,
        'pages': [
            {
                'id': 'page-1',
                'blocks': [
                    _table('p1-score', 'score_group', 0, 0, half, 3),
                    _table('p1-four', 't_adv_df', 0, 3, half, 3),
                    _text('p1-notes', half, 0, half, 6),
                    _rotation('p1-rotation', 0, 6, GRID_COLUMNS, ROTATION_DEFAULT_H),
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
                    _table('p3-home', 'p_df_home', 0, 0, GRID_COLUMNS, 8),
                    _table('p3-away', 'p_df_away', 0, 8, GRID_COLUMNS, 8),
                ],
            },
            {
                'id': 'page-4',
                'blocks': [
                    _table('p4-home', 'lineup_home', 0, 0, GRID_COLUMNS, 8),
                    _table('p4-away', 'lineup_away', 0, 8, GRID_COLUMNS, 8),
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
    if layout.get('version') != LAYOUT_VERSION:
        return default_layout()
    pages = layout.get('pages') or []
    if not pages:
        return default_layout()
    return {
        'version': LAYOUT_VERSION,
        'pages': pages,
    }
