# -*- coding: utf-8 -*-
"""Process-local caches and singleflight. Cleared when the process exits."""
import threading
import time
from concurrent.futures import Future

FINISHED_STATUSES = frozenset({'FINISHED', 'CONFIRMED'})
LIVE_REPORT_TTL_SECONDS = 15
SEASON_LIST_TTL_SECONDS = 60
ID_TABLE_TTL_SECONDS = 8 * 60 * 60


def normalize_status(status):
    if status is None:
        return ''
    return str(status).strip()


def is_finished_status(status):
    return normalize_status(status) in FINISHED_STATUSES


_report_lock = threading.Lock()
_report_cache = {}
_report_inflight = {}

_meta_lock = threading.Lock()
_season_cache = {}
_id_table_cache = {}


def _report_is_stale(entry):
    if is_finished_status(entry.get('status')):
        return False
    return (time.monotonic() - entry['fetched_at']) >= LIVE_REPORT_TTL_SECONDS


def get_cached_report(game_id):
    if not game_id:
        raise ValueError('game_id is required')

    with _report_lock:
        entry = _report_cache.get(game_id)
        if entry and not _report_is_stale(entry):
            return entry['report']
        fut = _report_inflight.get(game_id)
        if fut is None:
            fut = Future()
            _report_inflight[game_id] = fut
            is_builder = True
        else:
            is_builder = False

    if not is_builder:
        return fut.result()

    try:
        from synergy_reporter.post_game_report import PostGameReport
        report = PostGameReport(game_id)
        status = lookup_game_status(game_id)
        with _report_lock:
            _report_cache[game_id] = {
                'report': report,
                'fetched_at': time.monotonic(),
                'status': status,
            }
        fut.set_result(report)
        return report
    except Exception as exc:
        fut.set_exception(exc)
        raise
    finally:
        with _report_lock:
            _report_inflight.pop(game_id, None)


def get_cached_game_status(game_id):
    with _report_lock:
        entry = _report_cache.get(game_id)
        if entry:
            return entry.get('status') or ''
    return ''


def lookup_game_status(game_id):
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
    from synergy_inbounder.parser import Parser

    season_df = Parser.parse_season_game_list_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)
    game_row = season_df[season_df['fixtureId'] == game_id]
    if game_row.empty:
        return ''
    return normalize_status(game_row.iloc[0]['status'])


def get_cached_season_df(org_id, season_id, builder):
    key = (org_id, season_id)
    now = time.monotonic()
    with _meta_lock:
        entry = _season_cache.get(key)
        if entry and (now - entry['fetched_at']) < SEASON_LIST_TTL_SECONDS:
            return entry['value']
    value = builder()
    with _meta_lock:
        _season_cache[key] = {'value': value, 'fetched_at': time.monotonic()}
    return value


def get_cached_id_table(org_id, builder):
    now = time.monotonic()
    with _meta_lock:
        entry = _id_table_cache.get(org_id)
        if entry and (now - entry['fetched_at']) < ID_TABLE_TTL_SECONDS:
            return entry['value']
    value = builder()
    with _meta_lock:
        _id_table_cache[org_id] = {'value': value, 'fetched_at': time.monotonic()}
    return value


def clear_runtime_caches():
    with _report_lock:
        _report_cache.clear()
        _report_inflight.clear()
    with _meta_lock:
        _season_cache.clear()
        _id_table_cache.clear()
