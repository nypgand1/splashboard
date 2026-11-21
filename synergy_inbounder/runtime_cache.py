# -*- coding: utf-8 -*-
"""Process-local caches and singleflight. Cleared when the process exits."""
from collections import OrderedDict
from concurrent.futures import Future
import datetime
import threading
import time

import pandas as pd

from domain.clocks import parse_timestamp as _parse_start_time
from inbound.cache.catalog_cache import (
    ID_TABLE_TTL_SECONDS,
    SEASON_LIST_TTL_SECONDS,
    _id_inflight,
    _id_table_cache,
    _meta_lock,
    _season_cache,
    _season_inflight,
    cached_fixture_match as _cached_fixture_match,
    clear_catalog_cache,
    id_refresh_state,
    load_meta as _load_meta,
    season_refresh_state,
    taipei_now_label,
)
from inbound.cache.frame_store import REPORT_CACHE_LIMIT, report_pinned_ids
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


def should_use_live_endpoints(status=None, game_id=None, organization_id=None):
    if status is None and game_id:
        status = lookup_game_status(game_id, organization_id)
    return is_live_play_status(status)


_report_lock = threading.Lock()
_report_cache = OrderedDict()
_report_inflight = {}
_applied = {}
_delay_paint = {}
_budget_wait_notice = set()


def _report_key(game_id, organization_id):
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    org = organization_id or SYNERGY_ORGANIZATION_ID
    return (org, str(game_id))


def report_refresh_state(game_id, organization_id=None):
    key = _report_key(game_id, organization_id)
    with _report_lock:
        entry = _report_cache.get(key)
        if not entry:
            return {
                'label': None,
                'delayed': False,
                'stats_label': None,
                'stats_delayed': False,
                'generation': 0,
            }
        return {
            'label': entry.get('label'),
            'delayed': bool(entry.get('delayed')),
            'stats_label': entry.get('stats_label'),
            'stats_delayed': bool(entry.get('stats_delayed')),
            'generation': int(entry.get('generation') or 0),
        }


def report_generation(game_id, organization_id=None):
    return int(report_refresh_state(game_id, organization_id).get('generation') or 0)


def applied_generation(game_id, organization_id, slot):
    key = _report_key(game_id, organization_id)
    with _report_lock:
        return int(_applied.get((key, slot)) or 0)


def note_applied(game_id, organization_id, slot, generation):
    if not generation:
        return
    key = _report_key(game_id, organization_id)
    with _report_lock:
        _applied[(key, slot)] = int(generation)


def take_delay_paint(game_id, organization_id, slot):
    """True once when this snapshot is delayed and this slot has not painted it."""
    key = _report_key(game_id, organization_id)
    with _report_lock:
        entry = _report_cache.get(key)
        delayed = bool(entry and entry.get('delayed'))
        label = entry.get('label') if entry else None
        token = (key, slot)
        if not delayed:
            _delay_paint.pop(token, None)
            return False
        mark = (label, True)
        if _delay_paint.get(token) == mark:
            return False
        _delay_paint[token] = mark
        return True


def _copy_starters(report, previous):
    if not getattr(report, 'stats_failed', False) or previous is None:
        return
    old = previous.get('report')
    starters = getattr(old, 'starter_dict', None)
    if not starters:
        return
    report.starter_dict = {
        team_id: list(people)
        for team_id, people in starters.items()
    }


def _note_budget_wait(org, game_id):
    token = (str(org), str(game_id))
    if token in _budget_wait_notice:
        return
    _budget_wait_notice.add(token)
    from synergy_inbounder.logs import budget
    budget.info('waiting for a live slot org=%s game=%s', org, game_id)


def _clear_budget_wait(org, game_id):
    _budget_wait_notice.discard((str(org), str(game_id)))


def _evict_finished_reports(org):
    """Bound finished full reports per organization to REPORT_CACHE_LIMIT (12)."""
    from synergy_inbounder.publisher import active_watched_game_ids, forget_game_snap
    with _report_lock:
        org_keys = [
            k for k, entry in _report_cache.items()
            if isinstance(k, tuple) and k[0] == org and not is_live_play_status(entry.get('status'))
        ]
    if len(org_keys) <= REPORT_CACHE_LIMIT:
        return
    protected = set(report_pinned_ids(org)) | active_watched_game_ids(org)
    evicted = []
    with _report_lock:
        org_keys = [
            k for k, entry in _report_cache.items()
            if isinstance(k, tuple) and k[0] == org and not is_live_play_status(entry.get('status'))
        ]
        for candidate in org_keys:
            if len([
                k for k, entry in _report_cache.items()
                if isinstance(k, tuple) and k[0] == org and not is_live_play_status(entry.get('status'))
            ]) <= REPORT_CACHE_LIMIT:
                break
            if str(candidate[1]) not in protected:
                _report_cache.pop(candidate, None)
                evicted.append(candidate[1])
    for gid in evicted:
        forget_game_snap(org, gid)


def _store_report(key, report, status, now):
    previous = _report_cache.get(key)
    _copy_starters(report, previous)
    stats_failed = bool(getattr(report, 'stats_failed', False))
    label = taipei_now_label()
    if stats_failed and previous is not None:
        stats_label = previous.get('stats_label')
    else:
        stats_label = None if stats_failed else label
    generation = int(previous.get('generation') or 0) + 1 if previous else 1
    _clear_budget_wait(key[0] if isinstance(key, tuple) else None, key[-1] if isinstance(key, tuple) else key)
    if key in _report_cache:
        del _report_cache[key]
    _report_cache[key] = {
        'report': report,
        'fetched_at': now,
        'status': status,
        'label': label,
        'stats_label': stats_label,
        'stats_delayed': stats_failed,
        'delayed': False,
        'generation': generation,
    }


def _mark_report_delayed(key):
    entry = _report_cache.get(key)
    if entry:
        entry['delayed'] = True
        return entry['report']
    return None


def forget_finished_report(game_id, organization_id=None):
    """Drop a non-live report memo so the next build reads the new bodies."""
    if not game_id:
        return
    key = _report_key(game_id, organization_id)
    with _report_lock:
        entry = _report_cache.get(key)
        if entry and not is_live_play_status(entry.get('status')):
            _report_cache.pop(key, None)


def peek_finished_report(game_id, organization_id=None):
    """Return a stored non-live finished report, or None. Does not build one."""
    if not game_id:
        return None
    key = _report_key(game_id, organization_id)
    with _report_lock:
        entry = _report_cache.get(key)
    if not entry or is_live_play_status(entry.get('status')):
        return None
    if not is_finished_status(entry.get('status')):
        return None
    return entry.get('report')


def cached_fixture_status(organization_id, game_id):
    """Status from the process season cache. A miss does not fetch."""
    _season_id, row = _cached_fixture_match(organization_id, game_id)
    if row is None:
        return ''
    return normalize_status(row.get('status'))


def cached_regulation_minutes(organization_id, game_id):
    """Season-id minutes when that season list is already cached, else 48."""
    from synergy_inbounder.settings import regulation_minutes
    season_id, row = _cached_fixture_match(organization_id, game_id)
    if row is None:
        return 48
    minutes = regulation_minutes(season_id)
    return minutes if minutes else 48


def get_cached_report(game_id, organization_id=None, pin=None):
    factory = getattr(get_cached_report, 'factory', None)
    if callable(factory):
        return factory(game_id)
    if not game_id:
        raise ValueError('game_id is required')
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    org = organization_id or SYNERGY_ORGANIZATION_ID
    if pin == 'open':
        from synergy_inbounder.frame_store import pin_open
        pin_open(org, game_id)
    key = _report_key(game_id, organization_id)
    now = time.monotonic()

    with _report_lock:
        entry = _report_cache.get(key)
        if entry and not is_live_play_status(entry.get('status')):
            _report_cache.move_to_end(key)
    if entry and not is_live_play_status(entry.get('status')):
        BUDGET.forget(org, str(game_id))
        return entry['report']

    status = lookup_game_status(game_id, org)
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
                from synergy_inbounder.communicator import LiveBudgetWait
                _note_budget_wait(org, game_id)
                raise LiveBudgetWait('No live snapshot for {game}'.format(game=game_id))
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
        if not is_live_play_status(status):
            _evict_finished_reports(org)
        future.set_result(stored)
        return stored
    except SynergyAuthError as exc:
        from synergy_inbounder.logs import auth
        auth.exception('live report auth failed game=%s', game_id)
        _drop_partial_live_http(game_id, live)
        with _report_lock:
            _report_cache.pop(key, None)
        future.set_exception(exc)
        raise
    except Exception as exc:
        from synergy_inbounder.logs import build
        build.exception('live report build failed game=%s', game_id)
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
    from synergy_inbounder.parser import Parser
    from synergy_inbounder.settings import (
        SYNERGY_ORGANIZATION_ID,
        season_ids_for_organization,
    )

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
    except Exception as exc:
        from synergy_inbounder.logs import unexpected
        unexpected.exception('drop partial live http cache failed: %s', exc)
        return


def get_cached_season_df(org_id, season_id, builder):
    return _load_meta(
        _season_cache,
        _season_inflight,
        (org_id, season_id),
        SEASON_LIST_TTL_SECONDS,
        builder,
        time.monotonic(),
    )


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
    """Queue P2 phase-2 warmup (4,3,2 lineup combinations) via the unified publisher."""
    if not game_id:
        return
    org = organization_id
    if org is None and isinstance(match_info, dict):
        org = match_info.get('organization_id')
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    from synergy_inbounder.publisher import note_warmup_game
    note_warmup_game(org or SYNERGY_ORGANIZATION_ID, game_id)


def _fixture_id(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception as exc:
        from synergy_inbounder.logs import data
        data.debug('fixture id na check failed: %s', exc)
    text = str(value).strip()
    if not text or text.lower() == 'nan':
        return ''
    return text


def latest_finished_fixture_ids(season_df, max_games=2, team=None, game_type=None):
    """Up to max_games finished fixtures, latest startTimeLocal last.

    Accepts a DataFrame or a list of schedule record dicts, optionally filtered
    by ``team`` (entityId) and ``game_type`` (fixtureType).
    """
    if max_games <= 0 or season_df is None:
        return []
    if isinstance(season_df, list):
        records = [r for r in season_df if isinstance(r, dict)]
        if not records:
            return []
    else:
        if getattr(season_df, 'empty', True):
            return []
        columns = set(getattr(season_df, 'columns', []))
        if 'status' not in columns or 'fixtureId' not in columns:
            return []
        records = season_df.to_dict('records')
    wanted_team = str(team or '').strip()
    if wanted_team.lower() in ('', 'all', 'none'):
        wanted_team = ''
    wanted_type = str(game_type or '').strip()
    if wanted_type.lower() in ('', 'none', 'nan'):
        wanted_type = ''
    timed = []
    untimed = []
    for position, row in enumerate(records):
        if not is_finished_status(row.get('status')):
            continue
        if wanted_type:
            row_type = str(row.get('fixtureType') or row.get('Game Type') or '').strip()
            if row_type != wanted_type:
                continue
        if wanted_team:
            home_id = str(row.get('teamIdHome') or '').strip()
            away_id = str(row.get('teamIdAway') or '').strip()
            if wanted_team not in (home_id, away_id):
                continue
        fixture_id = _fixture_id(row.get('fixtureId'))
        if not fixture_id:
            continue
        start = _parse_start_time(row.get('startTimeLocal') or row.get('Time'))
        (timed if start is not None else untimed).append((position, start, fixture_id))
    pool = sorted(timed, key=lambda item: (item[1], item[0])) if timed else untimed
    if not pool:
        return []
    return [item[2] for item in pool[-max_games:]]


def prefetch_latest_games(
    season_df, max_games=2, organization_id=None, team=None, game_type=None,
    season_id=None, league=None,
):
    """Queue P2 Home hotspot finished reports and P3 season warmup on the unified publisher."""
    from synergy_inbounder.frame_store import pin_home
    from synergy_inbounder.publisher import note_prefetch_games, note_prefetch_season
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    org = organization_id or SYNERGY_ORGANIZATION_ID
    target_ids = latest_finished_fixture_ids(
        season_df, max_games, team=team, game_type=game_type,
    )
    if target_ids:
        pin_home(org, target_ids)
        note_prefetch_games(org, target_ids, league=league)
    if season_id:
        note_prefetch_season(org, season_id, league=league, game_type=game_type)


def clear_runtime_caches():
    """Clear all 3 memory cache modules: Report/LiveCache, CatalogCache, and FrameStore."""
    with _report_lock:
        _report_cache.clear()
        _report_inflight.clear()
        _applied.clear()
        _delay_paint.clear()
        _budget_wait_notice.clear()
    clear_catalog_cache()
    BUDGET.clear()
    from synergy_inbounder.frame_store import clear as clear_frames
    clear_frames()
    from synergy_inbounder.live_clock import clear_live_clocks
    clear_live_clocks()
    from synergy_inbounder.publisher import reset as reset_publisher
    reset_publisher()
    from synergy_inbounder.player_minutes_log import reset_player_minutes_log
    reset_player_minutes_log()
