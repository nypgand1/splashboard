# -*- coding: utf-8 -*-
"""Unified period labels, period chip builders, and period filtering."""
import pandas as pd

REGULATION_PERIOD_CHIPS = frozenset({'all', '1', '2', '3', '4', 'h1', 'h2'})


def period_label(period_id):
    """Display label for a period id (1Q..4Q, OT, OT2...)."""
    try:
        pid = int(period_id)
    except (TypeError, ValueError):
        return str(period_id)
    if 1 <= pid <= 4:
        return f'{pid}Q'
    if pid >= 11:
        ot = pid - 10
        return 'OT' if ot == 1 else f'{ot}OT'
    if pid > 4:
        ot = pid - 4
        return 'OT' if ot == 1 else f'{ot}OT'
    return f'P{pid}'


def period_id_value(value):
    """Normalize a periodId cell to int, or None when missing/invalid."""
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def known_period_ids(frame):
    """Distinct integer periodIds present in a DataFrame."""
    if frame is None or len(frame) == 0 or 'periodId' not in getattr(frame, 'columns', []):
        return set()
    found = set()
    for value in frame['periodId'].tolist():
        period = period_id_value(value)
        if period is not None:
            found.add(period)
    return found


def build_period_chips(period_ids, gate_ids=None):
    """Build ``All | 1Q | 2Q | 1H | 3Q | 4Q | 2H | OT...`` chips in standard order.

    When ``gate_ids`` is passed (e.g. player period ids on Game Box Score),
    only periods present in both ``period_ids`` and ``gate_ids`` are emitted.
    """
    found = set()
    for value in period_ids or ():
        pid = period_id_value(value)
        if pid is not None:
            found.add(pid)
    if gate_ids is not None:
        gate = {
            pid for pid in (period_id_value(v) for v in gate_ids)
            if pid is not None
        }
        found = found & gate
    chips = [{'label': 'All', 'value': 'all'}]
    for period in (1, 2):
        if period in found:
            chips.append({'label': period_label(period), 'value': str(period)})
    if 1 in found and 2 in found:
        chips.append({'label': '1H', 'value': 'h1'})
    for period in (3, 4):
        if period in found:
            chips.append({'label': period_label(period), 'value': str(period)})
    if 3 in found and 4 in found:
        chips.append({'label': '2H', 'value': 'h2'})
    for period in sorted(item for item in found if item not in (1, 2, 3, 4)):
        chips.append({'label': period_label(period), 'value': str(period)})
    return chips


def chip_spec(chip):
    """Return ``(period_id_tuple, recompute_rates_bool)`` for a period chip value."""
    if chip == 'h1':
        return (1, 2), True
    if chip == 'h2':
        return (3, 4), True
    return (int(chip),), False


def resolve_period_ids(period):
    """Return the tuple of integer period IDs for ``period``, or None for ``all``."""
    if period in (None, '', 'all'):
        return None
    ids, _recompute = chip_spec(period)
    return ids


def period_matches(period_id, selected):
    """True when ``period_id`` belongs to the selected period chip."""
    if not selected or selected == 'all':
        return True
    pid = period_id_value(period_id)
    if pid is None:
        return False
    if selected == 'h1':
        return pid in (1, 2)
    if selected == 'h2':
        return pid in (3, 4)
    try:
        return pid == int(selected)
    except (TypeError, ValueError):
        return False


def filter_periods(frame, period_ids):
    """Filter a DataFrame with ``periodId`` column to rows in ``period_ids``."""
    if frame is None or len(frame) == 0 or 'periodId' not in frame.columns:
        return pd.DataFrame()
    wanted = {period_id_value(period) for period in period_ids}
    ids = frame['periodId'].map(period_id_value)
    return frame.loc[ids.isin(wanted)].copy()


def is_overtime_period(period):
    """True when ``period`` selects a specific overtime period."""
    if period in REGULATION_PERIOD_CHIPS:
        return False
    try:
        return int(period) not in (1, 2, 3, 4)
    except (TypeError, ValueError):
        return False
