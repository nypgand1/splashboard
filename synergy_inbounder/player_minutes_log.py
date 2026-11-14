# -*- coding: utf-8 -*-
"""Record raw player-minute gaps for a later read of the live feed.

The box score is unchanged. Lines go to ``synergy.live.minutes`` at INFO.
"""
import threading

from synergy_inbounder.logs import minutes as log_minutes

_COUNT_FIELDS = (
    'points', 'pointsTwoMade', 'pointsTwoAttempted',
    'pointsThreeMade', 'pointsThreeAttempted',
    'freeThrowsMade', 'freeThrowsAttempted',
    'rebounds', 'reboundsOffensive', 'reboundsDefensive',
    'assists', 'turnovers', 'steals', 'blocks',
    'foulsTotal', 'foulsDrawn', 'plusMinus',
)

_lock = threading.Lock()
_seen_live = set()
_last_summary = {}
_last_gap = {}
_keys_logged = set()


def reset_player_minutes_log():
    """Drop the in-process watch. Used when the runtime caches are cleared."""
    with _lock:
        _seen_live.clear()
        _last_summary.clear()
        _last_gap.clear()
        _keys_logged.clear()


def _items(payload):
    if not isinstance(payload, dict):
        return []
    data = payload.get('data')
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _nonzero(value):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    try:
        return float(value) != 0.0
    except (TypeError, ValueError):
        return False


def _has_count(stats):
    return any(_nonzero(stats.get(field)) for field in _COUNT_FIELDS)


def _minutes_state(stats):
    """Return ``(present, raw)``. ``present`` is missing, null, blank, or ok."""
    if 'minutes' not in stats:
        return 'missing', None
    value = stats.get('minutes')
    if value is None:
        return 'null', None
    if isinstance(value, float) and value != value:
        return 'null', None
    if isinstance(value, str) and not value.strip():
        return 'blank', value
    return 'ok', value


def _describe(item, period):
    stats = item.get('statistics')
    if not isinstance(stats, dict):
        stats = {}
    present, raw = _minutes_state(stats)
    return {
        'person': item.get('personId'),
        'entity': item.get('entityId'),
        'starter': bool(item.get('starter')),
        'participated': bool(item.get('participated')),
        'present': present,
        'minutes': raw,
        'points': stats.get('points'),
        'rebounds': stats.get('rebounds'),
        'assists': stats.get('assists'),
        'counts': _has_count(stats),
        'keys': tuple(sorted(str(key) for key in stats.keys())),
        'period': period,
    }


def _row_line(fixture_id, route, row):
    return (
        'player-minutes row fixture=%s route=%s person=%s entity=%s '
        'starter=%s participated=%s minutes=%r present=%s points=%s '
        'rebounds=%s assists=%s period=%s' % (
            fixture_id, route, row['person'], row['entity'],
            row['starter'], row['participated'], row['minutes'], row['present'],
            row['points'], row['rebounds'], row['assists'], row['period'],
        )
    )


def _filled_line(fixture_id, route, row):
    return (
        'player-minutes filled fixture=%s route=%s person=%s minutes=%r '
        'points=%s period=%s' % (
            fixture_id, route, row['person'], row['minutes'],
            row['points'], row['period'],
        )
    )


def _signature(row):
    return (
        row['present'], repr(row['minutes']), row['starter'], row['participated'],
        row['points'], row['rebounds'], row['assists'],
    )


def _note_rows(org_id, fixture_id, route, rows, kind, lines):
    missing = 0
    missing_with_counts = 0
    saw_missing_key = False
    key_union = set()
    for row in rows:
        token = (
            str(org_id), str(fixture_id), kind,
            row['person'], row['entity'], row['period'],
        )
        if row['present'] == 'ok':
            if token in _last_gap:
                del _last_gap[token]
                lines.append(_filled_line(fixture_id, route, row))
            continue
        missing += 1
        if row['counts']:
            missing_with_counts += 1
        if row['present'] == 'missing':
            saw_missing_key = True
            key_union.update(row['keys'])
        signature = (route, _signature(row))
        if _last_gap.get(token) == signature:
            continue
        _last_gap[token] = signature
        lines.append(_row_line(fixture_id, route, row))
    return missing, missing_with_counts, tuple(sorted(key_union)), saw_missing_key


def note_player_minutes(org_id, fixture_id, live, status, player_json, period_json):
    """Log minute gaps for one bundle. Official rows log only after a live bundle.

    Returns the lines written. An unchanged snapshot returns an empty list.
    """
    route = 'live' if live else 'official'
    watch = (str(org_id), str(fixture_id))
    label = str(status or '').strip() or route
    lines = []
    with _lock:
        if live:
            _seen_live.add(watch)
        elif watch not in _seen_live:
            return []
        if isinstance(player_json, dict) and player_json.get('_stats_failed'):
            lines.append(
                'player-minutes fixture=%s org=%s route=%s failed=1' % (
                    fixture_id, org_id, route,
                )
            )
        else:
            totals = [
                _describe(item, 'all') for item in _items(player_json)
            ]
            periods = [
                _describe(item, item.get('periodId')) for item in _items(period_json)
            ]
            missing, with_counts, key_names, saw_missing_key = _note_rows(
                org_id, fixture_id, route, totals, 'totals', lines,
            )
            period_missing, period_with_counts, _period_keys, _period_missing_key = _note_rows(
                org_id, fixture_id, route, periods, 'periods', lines,
            )
            if saw_missing_key and (watch, route) not in _keys_logged:
                _keys_logged.add((watch, route))
                lines.append(
                    'player-minutes keys fixture=%s org=%s route=%s keys=%s' % (
                        fixture_id, org_id, route, ','.join(key_names),
                    )
                )
            summary = (
                len(totals), missing, with_counts,
                len(periods), period_missing, period_with_counts, label,
            )
            if _last_summary.get((watch, route)) != summary:
                _last_summary[(watch, route)] = summary
                lines.insert(0, (
                    'player-minutes fixture=%s org=%s route=%s status=%s '
                    'rows=%s missing=%s missing_with_counts=%s '
                    'period_rows=%s period_missing=%s '
                    'period_missing_with_counts=%s' % (
                        fixture_id, org_id, route, label,
                        summary[0], summary[1], summary[2],
                        summary[3], summary[4], summary[5],
                    )
                ))
        for line in lines:
            log_minutes.info(line)
        return list(lines)
