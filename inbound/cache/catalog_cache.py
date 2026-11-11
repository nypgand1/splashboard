# -*- coding: utf-8 -*-
"""Cache Module 1: Organization Catalog & Season Schedule Cache (TTL 2h / 30s).

Uses ``SingleflightGroup`` to coalesce concurrent requests for ``season_df``
and ``id_table``, with stale-on-error fallback (`delayed=True`).
"""
from concurrent.futures import Future
import datetime
import threading
import time

from synergy_inbounder.live_budget import LONG_CACHE_SECONDS, SHORT_CACHE_SECONDS

SEASON_LIST_TTL_SECONDS = SHORT_CACHE_SECONDS
ID_TABLE_TTL_SECONDS = LONG_CACHE_SECONDS

_meta_lock = threading.Lock()
_season_cache = {}
_season_inflight = {}
_id_table_cache = {}
_id_inflight = {}


def taipei_now_label():
    when = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
    return 'Last Update: {when}'.format(when=when)


def load_meta(cache, inflight, key, ttl, builder, now):
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
        from synergy_inbounder.logs import auth
        auth.exception('meta refresh auth failed')
        fut.set_exception(exc)
        raise
    except Exception as exc:
        from synergy_inbounder.logs import unexpected
        unexpected.exception('meta refresh failed')
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


def get_cached_season_df(org_id, season_id, builder, now_fn=time.monotonic):
    return load_meta(
        _season_cache,
        _season_inflight,
        (org_id, season_id),
        SEASON_LIST_TTL_SECONDS,
        builder,
        now_fn(),
    )


def get_cached_id_table(org_id, builder, now_fn=time.monotonic):
    return load_meta(
        _id_table_cache,
        _id_inflight,
        org_id,
        ID_TABLE_TTL_SECONDS,
        builder,
        now_fn(),
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


def cached_fixture_match(organization_id, game_id):
    wanted = str(game_id or '')
    if not wanted:
        return None, None
    with _meta_lock:
        items = list(_season_cache.items())
    for (org, season_id), entry in items:
        if org != organization_id:
            continue
        frame = entry.get('value') if isinstance(entry, dict) else None
        if frame is None or getattr(frame, 'empty', True) or 'fixtureId' not in getattr(frame, 'columns', []):
            continue
        matched = frame[frame['fixtureId'].astype(str) == wanted]
        if not matched.empty:
            return season_id, matched.iloc[0]
    return None, None


def clear_catalog_cache():
    with _meta_lock:
        _season_cache.clear()
        _season_inflight.clear()
        _id_table_cache.clear()
        _id_inflight.clear()
