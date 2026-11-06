# -*- coding: utf-8 -*-
"""Which side a Select menu opens, and how tall it is.

The numbers match ``assets/select_menu.js`` (``splashboardSelectMenuPlan``).
"""
from decimal import Decimal, ROUND_CEILING


def _menu_px(value):
    """Smallest whole pixel that can hold this length."""
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_CEILING))


def select_menu_plan(top, bottom, viewport_height, row_count, row_height=32, pad_top=0, pad_bottom=0):
    """Open toward the side that can hold every row plus the dropdown padding.

    The space below wins when both sides can. When neither can, scroll and end
    on a complete row. A short window still keeps four rows.
    """
    above = max(0.0, float(top) - 12)
    below = max(0.0, float(viewport_height) - float(bottom) - 12)
    rows = max(0, int(row_count))
    row = float(row_height)
    pad = _menu_px(pad_top) + _menu_px(pad_bottom)
    inner_all = _menu_px(rows * row) if rows else 0
    needed = inner_all + (pad if rows else 0)

    def scroll_inner(space):
        room = float(space) - pad
        fit = int(room // row) if row > 0 else 0
        count = fit if fit >= 4 else 4
        return _menu_px(count * row)

    if needed > 0 and below >= needed:
        side, inner = 'bottom', inner_all
    elif needed > 0 and above >= needed:
        side, inner = 'top', inner_all
    elif below >= above:
        side, inner = 'bottom', scroll_inner(below)
    else:
        side, inner = 'top', scroll_inner(above)
    return {'side': side, 'height': inner + pad, 'inner': inner}
