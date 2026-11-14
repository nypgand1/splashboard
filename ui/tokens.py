# -*- coding: utf-8 -*-
"""Design tokens for Splashboard (日式簡約 Braves 青空藍).

Single source of truth for Python-side colors, typography, and layout constants,
aligned with CSS custom properties in ``assets/app.css`` and ``assets/report.css``.
"""

BRAVES_BLUE_PRIMARY = '#0077b6'
BRAND_PRIMARY = BRAVES_BLUE_PRIMARY
BRAVES_CYAN_ACCENT = '#00b4d8'
OPP_ALERT_RED = '#e63946'
HOT_ZONE_RED = '#dc2626'
KILL_STOP_RED = '#ef4444'
MARGIN_LINE_BLUE = '#0284c7'
AWAY_SLATE = '#94a3b8'
DNP_TEXT = AWAY_SLATE
OPP_ROW_BG = '#f1f5f9'
BORDER_SLATE = '#e2e8f0'
GRID_LINE_SLATE = '#e2e8f0'
ZERO_LINE_SLATE = '#475569'
PRIMARY_INK = '#0f172a'
INK_PRIMARY = '#1e293b'
INK_SECONDARY = '#334155'
INK_SUBTLE = '#475569'
INK_MUTED = '#64748b'
JERSEY_MUTED = '#64748b'

HOME_FILL_SOFT = 'rgba(0, 119, 182, 0.20)'
AWAY_FILL_SOFT = 'rgba(148, 163, 184, 0.25)'
HOME_RUN_FILL = 'rgba(0, 119, 182, 0.14)'
AWAY_RUN_FILL = 'rgba(148, 163, 184, 0.22)'
SELECTED_FILL = HOME_FILL_SOFT
OPPONENT_FILL = AWAY_FILL_SOFT

HOME_DOT = BRAVES_CYAN_ACCENT
AWAY_DOT = AWAY_SLATE
HOME_STRIPE = BRAVES_BLUE_PRIMARY
AWAY_STRIPE = AWAY_SLATE

WINNER_STYLE = {'color': BRAVES_BLUE_PRIMARY, 'fontWeight': 700}
OPP_BEST_STYLE = {'color': OPP_ALERT_RED, 'fontWeight': 700}

SCORE_COLOR = BRAVES_BLUE_PRIMARY
SCORE_FZ = '22px'
SCORE_SLOT_STYLE = {
    'fontVariantNumeric': 'tabular-nums',
    'flexShrink': 0,
}

COURT_COLUMN_STYLE = {'width': '100%', 'maxWidth': '380px', 'marginInline': 'auto'}
COURT_CARD_STYLE = {'width': '100%', 'maxWidth': '808px', 'marginInline': 'auto'}
COURT_IMAGE_STYLE = {'width': '100%', 'height': 'auto', 'display': 'block'}

ROTATION_FIGURE_MARGIN = {'l': 112, 'r': 112, 't': 40, 'b': 48}

MANTINE_THEME = {
    'primaryColor': 'bravesBlue',
    'fontFamily': '-apple-system, "PingFang TC", "Noto Sans TC", "Segoe UI", Roboto, sans-serif',
    'defaultRadius': 'md',
    'colors': {
        'bravesBlue': [
            '#e8f4f8',
            '#cce9f2',
            '#99d4e5',
            '#66bed8',
            '#33a9cb',
            BRAVES_CYAN_ACCENT,
            BRAVES_BLUE_PRIMARY,
            '#005f92',
            '#00476d',
            '#002f49',
        ]
    },
}
