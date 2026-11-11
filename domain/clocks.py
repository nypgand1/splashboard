# -*- coding: utf-8 -*-
"""Clock parsing, duration formatting, and timestamp helpers."""
import re

import pandas as pd

from synergy_inbounder.logs import data as log_data

CLOCK_RE = re.compile(r'^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$')


def clock_to_seconds(value):
    """Parse Synergy ISO-8601 duration (e.g. ``PT10M00S``) or numeric seconds."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = CLOCK_RE.match(text)
    if match:
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2) or 0.0)
        return minutes * 60.0 + seconds
    try:
        return float(text)
    except ValueError:
        return None


def minutes_to_mmss(value):
    """Convert Synergy PT duration (or seconds) to M:SS (e.g. 45:59, 8:21, 0:06)."""
    seconds = clock_to_seconds(value)
    if seconds is None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ''
        return str(value).strip()
    total = int(round(float(seconds)))
    if total < 0:
        total = 0
    return '{:d}:{:02d}'.format(total // 60, total % 60)


def sum_clocks(values):
    """Sum an iterable of PT durations into a single ``PT{M}M{S}S`` string."""
    total = 0.0
    seen = False
    for value in values:
        seconds = clock_to_seconds(value)
        if seconds is None:
            continue
        seen = True
        total += float(seconds)
    if not seen:
        return 'PT0S'
    whole = int(round(total))
    return f'PT{whole // 60}M{whole % 60}S'


def clock_sort_seconds(value):
    """M:SS as seconds for sorting. Blank and DNP sort as missing (NaN)."""
    if value is None:
        return float('nan')
    try:
        if pd.isna(value):
            return float('nan')
    except TypeError:
        pass
    text = str(value).strip()
    if not text or text == 'DNP' or ':' not in text:
        return float('nan')
    minutes, _, seconds = text.partition(':')
    try:
        return int(minutes) * 60 + float(seconds)
    except ValueError:
        return float('nan')


def parse_timestamp(value):
    """Parse an ISO start time safely into a pandas Timestamp, or None."""
    if value is None or value == '':
        return None
    try:
        if pd.isna(value):
            return None
    except Exception as exc:
        log_data.debug('timestamp na check failed: %s', exc)
        return None
    try:
        parsed = pd.to_datetime(value)
    except Exception as exc:
        log_data.debug('timestamp parse failed: %s', exc)
        return None
    try:
        if pd.isna(parsed):
            return None
    except Exception as exc:
        log_data.debug('parsed timestamp na check failed: %s', exc)
        return None
    return parsed
