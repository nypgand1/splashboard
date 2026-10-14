# -*- coding: utf-8 -*-
"""Process-local caches and singleflight. Cleared when the process exits."""
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

# One live cadence for PBP-derived views (Play-By-Play + Rotation).
LIVE_CADENCE_SECONDS = 30
LIVE_PBP_HTTP_TTL_SECONDS = 25
LIVE_REPORT_TTL_SECONDS = 25
SEASON_LIST_TTL_SECONDS = 25
ID_TABLE_TTL_SECONDS = 8 * 60 * 60


def should_use_live_endpoints(status=None, game_id=None, organization_id=None):
    if status is None and game_id:
        status = lookup_game_status(game_id, organization_id)
    return is_live_play_status(status)


_report_lock = threading.Lock()
_report_cache = {}
_report_inflight = {}

_meta_lock = threading.Lock()
_season_cache = {}
_id_table_cache = {}


def _report_is_stale(entry):
    if not is_live_play_status(entry.get('status')):
        return False
    return (time.monotonic() - entry['fetched_at']) >= LIVE_REPORT_TTL_SECONDS


def _report_key(game_id, organization_id):
    from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
    org = organization_id or SYNERGY_ORGANIZATION_ID
    return (org, str(game_id))


def get_cached_report(game_id, organization_id=None):
    factory = getattr(get_cached_report, 'factory', None)
    if callable(factory):
        return factory(game_id)
    if not game_id:
        raise ValueError('game_id is required')
    key = _report_key(game_id, organization_id)

    with _report_lock:
        entry = _report_cache.get(key)
        if entry and not _report_is_stale(entry):
            return entry['report']
        fut = _report_inflight.get(key)
        if fut is None:
            fut = Future()
            _report_inflight[key] = fut
            is_builder = True
        else:
            is_builder = False

    if not is_builder:
        return fut.result()

    try:
        from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
        from synergy_reporter.post_game_report import PostGameReport
        org = organization_id or SYNERGY_ORGANIZATION_ID
        report = PostGameReport(game_id, org)
        status = lookup_game_status(game_id, org)
        with _report_lock:
            _report_cache[key] = {
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
        _id_table_cache.clear()

