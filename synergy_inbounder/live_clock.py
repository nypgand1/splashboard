# -*- coding: utf-8 -*-
"""In-progress period clock for the schedule and the game banner."""
import json
import threading

import pandas as pd

from synergy_reporter.rotation import (
    _parse_scores,
    _same_id,
    clock_to_seconds,
    period_label,
)

_LOCK = threading.Lock()
_CLOCKS = {}


def format_period_clock(period_id, clock):
    seconds = clock_to_seconds(clock)
    if seconds is None or seconds < 0:
        return None
    try:
        if pd.isna(period_id):
            return None
    except TypeError:
        pass
    try:
        period = int(period_id)
    except (TypeError, ValueError):
        return None
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return '{label} {minutes}:{secs:02d}'.format(
        label=period_label(period),
        minutes=minutes,
        secs=secs,
    )


def label_from_summary(payload):
    status, clock = _summary_clock(payload)
    if status is None or clock is None:
        return None
    if 'periodId' not in status or status.get('periodId') in (None, ''):
        return None
    main = clock.get('main')
    if main in (None, ''):
        return None
    return format_period_clock(status.get('periodId'), main)


def _score_text(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return str(int(number))
    return str(number)


def clock_from_pbp_frame(frame):
    label, _home, _away = scoreboard_from_pbp_frame(frame, None, None)
    return label


def scoreboard_from_pbp_frame(frame, home_id, away_id):
    """Clock and the scoreboard at that event, from API ``data`` order.

    The clock is the last row with ``periodId`` and a parseable clock.
    The score is that row's home and away points, or the nearest earlier
    row that has both. Rows after the clock that have no clock are ignored.
    No clock returns ``(None, None, None)``.
    """
    if frame is None or getattr(frame, 'empty', True):
        return None, None, None
    if 'periodId' not in frame.columns or 'clock' not in frame.columns:
        return None, None, None
    records = frame.to_dict('records')
    clock_at = None
    label = None
    for index, row in enumerate(records):
        text = format_period_clock(row.get('periodId'), row.get('clock'))
        if text:
            clock_at = index
            label = text
    if clock_at is None:
        return None, None, None
    home_score = None
    away_score = None
    for row in records[:clock_at + 1]:
        found_home = None
        found_away = None
        for key, value in _parse_scores(row.get('scores')).items():
            text = _score_text(value)
            if text is None:
                continue
            if _same_id(key, home_id):
                found_home = text
            elif _same_id(key, away_id):
                found_away = text
        if found_home is not None and found_away is not None:
            home_score = found_home
            away_score = found_away
    return label, home_score, away_score


def clock_from_pbp_store(raw):
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or parsed.get('_ui') == 'error':
        return None
    columns = parsed.get('columns')
    data = parsed.get('data')
    if not isinstance(columns, list) or not isinstance(data, list):
        return None
    try:
        frame = pd.DataFrame(data, columns=columns)
    except (TypeError, ValueError):
        return None
    return clock_from_pbp_frame(frame)


def recall(org_id, fixture_id):
    if not org_id or not fixture_id:
        return None
    with _LOCK:
        return _CLOCKS.get((str(org_id), str(fixture_id)))


def remember(org_id, fixture_id, label):
    if not org_id or not fixture_id or not label:
        return
    with _LOCK:
        _CLOCKS[(str(org_id), str(fixture_id))] = label


def forget_finished(org_id, records):
    if not org_id:
        return
    live_ids = set()
    for row in records or []:
        if str(row.get('status') or '').strip() != 'IN_PROGRESS':
            continue
        fixture_id = row.get('fixtureId')
        if fixture_id:
            live_ids.add(str(fixture_id))
    org = str(org_id)
    with _LOCK:
        for key in [key for key in _CLOCKS if key[0] == org and key[1] not in live_ids]:
            _CLOCKS.pop(key, None)


def refresh_summaries(org_id, candidates):
    from synergy_inbounder.communicator import (
        Communicator,
        SynergyApiError,
        SynergyAuthError,
    )

    if not org_id:
        return
    for row in candidates or []:
        fixture_id = str(row.get('fixtureId') or '')
        if not fixture_id:
            continue
        try:
            payload = Communicator.get_fixture_live_summary(org_id, fixture_id)
        except SynergyAuthError:
            return
        except SynergyApiError as exc:
            text = str(exc).lower()
            if 'budget' in text or '429' in text:
                return
            continue
        except Exception as exc:
            from synergy_inbounder.logs import data as log_data
            log_data.debug('live summary unavailable fixture=%s: %s', fixture_id, exc)
            continue
        label = label_from_summary(payload)
        if label:
            remember(org_id, fixture_id, label)


def _summary_clock(payload):
    if not isinstance(payload, dict):
        return None, None
    data = payload.get('data')
    item = None
    if isinstance(data, list) and data:
        item = data[0]
    elif isinstance(data, dict):
        item = data
    return _clock_pair(item)


def _clock_pair(item):
    if not isinstance(item, dict):
        return None, None
    status = item.get('status')
    clock = item.get('clock')
    if isinstance(status, dict) and isinstance(clock, dict):
        if 'periodId' in status or 'main' in clock:
            return status, clock
    inner = item.get('data')
    if isinstance(inner, dict) and inner is not item:
        return _clock_pair(inner)
    return None, None
