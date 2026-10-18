# -*- coding: utf-8 -*-
"""Process-local caches and singleflight. Cleared when the process exits."""
import datetime
import threading
import time
from concurrent.futures import Future

import pandas as pd

from synergy_inbounder.game_status import (
    FINISHED_STATUSES,
    is_finished_status,
    is_live_play_status,
    normalize_status,
)
from synergy_inbounder.live_budget import (
    BUDGET,
    LIVE_CADENCE_SECONDS,
    LONG_CACHE_SECONDS,
    SHORT_CACHE_SECONDS,
)

# One live cadence for PBP-derived views (Play-By-Play + Rotation).
LIVE_PBP_HTTP_TTL_SECONDS = SHORT_CACHE_SECONDS
LIVE_REPORT_TTL_SECONDS = SHORT_CACHE_SECONDS
SEASON_LIST_TTL_SECONDS = SHORT_CACHE_SECONDS
ID_TABLE_TTL_SECONDS = LONG_CACHE_SECONDS


def should_use_live_endpoints(status=None, game_id=None, organization_id=None):
    if status is None and game_id:
        status = lookup_game_status(game_id, organization_id)
    return is_live_play_status(status)


_report_lock = threading.Lock()
_report_cache = {}
_report_inflight = {}

_meta_lock = threading.Lock()
_season_cache = {}
_season_inflight = {}
_id_table_cache = {}
_id_inflight = {}


def taipei_now_label():
    when = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
    return 'Last Update: {when}'.format(when=when)


def _report_key(game_id, organization_id):
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    org = organization_id or SYNERGY_ORGANIZATION_ID
    return (org, str(game_id))


def report_refresh_state(game_id, organization_id=None):
    key = _report_key(game_id, organization_id)
    with _report_lock:
        entry = _report_cache.get(key)
        if not entry:
            return {'label': None, 'delayed': False}
        return {
            'label': entry.get('label'),
            'delayed': bool(entry.get('delayed')),
        }


def _store_report(key, report, status, now):
    _report_cache[key] = {
        'report': report,
        'fetched_at': now,
        'status': status,
        'label': taipei_now_label(),
        'delayed': False,
    }


def _mark_report_delayed(key):
    entry = _report_cache.get(key)
    if entry:
        entry['delayed'] = True
        return entry['report']
    return None


def get_cached_report(game_id, organization_id=None):
    factory = getattr(get_cached_report, 'factory', None)
    if callable(factory):
        return factory(game_id)
    if not game_id:
        raise ValueError('game_id is required')
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    org = organization_id or SYNERGY_ORGANIZATION_ID
    key = _report_key(game_id, organization_id)
    now = time.monotonic()

    with _report_lock:
        entry = _report_cache.get(key)
    if entry and not is_live_play_status(entry.get('status')):
        BUDGET.forget(org, str(game_id))
        return entry['report']

    status = entry.get('status') if entry else lookup_game_status(game_id, org)
    if not is_live_play_status(status):
        BUDGET.forget(org, str(game_id))
        return _build_report(key, game_id, org, now, live=False)

    with _report_lock:
        inflight = _report_inflight.get(key)
        if inflight is not None:
            is_builder = False
            fut = inflight
        else:
            entry = _report_cache.get(key)
            has_snapshot = entry is not None
            age = (now - entry['fetched_at']) if entry else SHORT_CACHE_SECONDS
            action = BUDGET.acquire(org, str(game_id), has_snapshot, age, now)
            if action != 'fetch':
                if action == 'delay':
                    _mark_report_delayed(key)
                if entry:
                    return entry['report']
                from synergy_inbounder.communicator import SynergyApiError
                raise SynergyApiError('No live snapshot for {game}'.format(game=game_id))
            fut = Future()
            _report_inflight[key] = fut
            is_builder = True

    if not is_builder:
        return fut.result()
    try:
        return _build_report(key, game_id, org, now, live=True, future=fut)
    finally:
        BUDGET.release(org)
        with _report_lock:
            _report_inflight.pop(key, None)


def _build_report(key, game_id, org, now, live, future=None):
    from synergy_inbounder.communicator import SynergyAuthError
    from synergy_reporter.post_game_report import PostGameReport
    created_here = future is None
    if created_here:
        with _report_lock:
            existing = _report_inflight.get(key)
            if existing is not None:
                future = existing
                created_here = False
            else:
                future = Future()
                _report_inflight[key] = future
        if not created_here:
            return future.result()
    try:
        report = PostGameReport(game_id, org)
        status = lookup_game_status(game_id, org)
        with _report_lock:
            _store_report(key, report, status, time.monotonic())
            stored = _report_cache[key]['report']
        future.set_result(stored)
        return stored
    except SynergyAuthError as exc:
        _drop_partial_live_http(game_id, live)
        with _report_lock:
            _report_cache.pop(key, None)
        future.set_exception(exc)
        raise
    except Exception as exc:
        _drop_partial_live_http(game_id, live)
        with _report_lock:
            stale = _mark_report_delayed(key)
        if live and stale is not None:
            future.set_result(stale)
            return stale
        future.set_exception(exc)
        raise
    finally:
        if created_here:
            with _report_lock:
                _report_inflight.pop(key, None)


def get_cached_game_status(game_id, organization_id=None):
    key = _report_key(game_id, organization_id)
    with _report_lock:
        entry = _report_cache.get(key)
        if entry:
            return entry.get('status') or ''
    return ''


def lookup_game_status(game_id, organization_id=None):
    from synergy_inbounder.settings import (
        SYNERGY_ORGANIZATION_ID,
        season_ids_for_organization,
    )
    from synergy_inbounder.parser import Parser

    org = organization_id or SYNERGY_ORGANIZATION_ID
    row = Parser.find_game_row(org, game_id, season_ids_for_organization(org))
    if row is None:
        return ''
    return normalize_status(row.get('status'))


def _drop_partial_live_http(game_id, live):
    if not live:
        return
    try:
        from synergy_inbounder.communicator import drop_cached_live_urls
        drop_cached_live_urls(game_id)
    except Exception:
        return


def _load_meta(cache, inflight, key, ttl, builder, now):
    from synergy_inbounder.communicator import SynergyAuthError
    with _meta_lock:
        entry = cache.get(key)
        if entry and (now - entry['fetched_at']) < ttl:
            return entry['value']
        fut = inflight.get(key)
        if fut is None:
            fut = Future()
            inflight[key] = fut
            is_builder = True
        else:
            is_builder = False
    if not is_builder:
        return fut.result()
    try:
        value = builder()
        with _meta_lock:
            cache[key] = {
                'value': value,
                'fetched_at': time.monotonic(),
                'delayed': False,
                'label': taipei_now_label(),
            }
        fut.set_result(value)
        return value
    except SynergyAuthError as exc:
        fut.set_exception(exc)
        raise
    except Exception as exc:
        with _meta_lock:
            entry = cache.get(key)
            if entry:
                entry['delayed'] = True
                fut.set_result(entry['value'])
                return entry['value']
        fut.set_exception(exc)
        raise
    finally:
        with _meta_lock:
            inflight.pop(key, None)


def get_cached_season_df(org_id, season_id, builder):
    return _load_meta(
        _season_cache,
        _season_inflight,
        (org_id, season_id),
        SEASON_LIST_TTL_SECONDS,
        builder,
        time.monotonic(),
    )


def season_refresh_state(org_id, season_id):
    with _meta_lock:
        entry = _season_cache.get((org_id, season_id))
        if not entry:
            return {'label': None, 'delayed': False}
        return {
            'label': entry.get('label'),
            'delayed': bool(entry.get('delayed')),
        }


def id_refresh_state(org_id):
    with _meta_lock:
        entry = _id_table_cache.get(org_id)
        if not entry:
            return {'delayed': False}
        return {'delayed': bool(entry.get('delayed'))}


def get_cached_id_table(org_id, builder):
    return _load_meta(
        _id_table_cache,
        _id_inflight,
        org_id,
        ID_TABLE_TTL_SECONDS,
        builder,
        time.monotonic(),
    )


def warmup_game_report(game_id, match_info=None, organization_id=None):
    """Background warmup for finished games: computes 4,3,2 lineup combinations and rotation."""
    if not game_id:
        return
    org = organization_id
    if org is None and isinstance(match_info, dict):
        org = match_info.get('organization_id')

    def _run():
        try:
            report = get_cached_report(game_id, org)
            status = lookup_game_status(game_id, org)
            if is_finished_status(status):
                report.get_all_lineup_stats_json_dict(sizes=(5, 4, 3, 2))
                info = match_info or {}
                report.get_rotation_payload(
                    home_team_id=info.get('home_team_id'),
                    away_team_id=info.get('away_team_id'),
                )
        except Exception as e:
            print(f"Background warmup error for {game_id}: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _parse_start_time(value):
    if value is None or value == '':
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return None
    try:
        if pd.isna(parsed):
            return None
    except Exception:
        pass
    return parsed


def _fixture_id(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() == 'nan':
        return ''
    return text


def latest_finished_fixture_ids(season_df, max_games=2):
    """Up to max_games finished fixtures, latest startTimeLocal last.

    A missing start time stays out unless every finished row is missing one.
    Equal times keep schedule order: the later row is later.
    """
    if max_games <= 0 or season_df is None or getattr(season_df, 'empty', True):
        return []
    columns = set(getattr(season_df, 'columns', []))
    if 'status' not in columns or 'fixtureId' not in columns:
        return []
    finished = season_df[season_df['status'].map(is_finished_status)]
    if finished.empty:
        return []
    timed = []
    untimed = []
    for position, row in enumerate(finished.to_dict('records')):
        fixture_id = _fixture_id(row.get('fixtureId'))
        if not fixture_id:
            continue
        start = _parse_start_time(row.get('startTimeLocal'))
        (timed if start is not None else untimed).append((position, start, fixture_id))
    pool = sorted(timed, key=lambda item: (item[1], item[0])) if timed else untimed
    if not pool:
        return []
    return [item[2] for item in pool[-max_games:]]


def prefetch_latest_games(season_df, max_games=2, organization_id=None):
    """Background sequential worker to prefetch up to max_games finished reports."""
    target_ids = latest_finished_fixture_ids(season_df, max_games)
    if not target_ids:
        return

    def _worker():
        for gid in target_ids:
            try:
                get_cached_report(gid, organization_id)
            except Exception as e:
                print(f"Prefetch error for game {gid}: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def clear_runtime_caches():
    with _report_lock:
        _report_cache.clear()
        _report_inflight.clear()
    with _meta_lock:
        _season_cache.clear()
        _season_inflight.clear()
        _id_table_cache.clear()
        _id_inflight.clear()
    BUDGET.clear()

