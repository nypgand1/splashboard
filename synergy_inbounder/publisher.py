# -*- coding: utf-8 -*-
"""One background publisher for watched Game and Team Stats pages.

HTTP callbacks note a watch and read a drawer. They do not build a report and
they do not wait on an in-flight fetch. Live work runs before a season step.
The same key is not started twice while its job is still running.
"""
import threading
import time

from synergy_inbounder.live_budget import LIVE_CADENCE_SECONDS, WATCH_SECONDS

OFFICIAL_REFRESH_SECONDS = 120
READER_WAIT_MS = 2000
CONFIRMED_BATCH = 4

_LOCK = threading.Lock()
_epoch = 0
_games = {}
_seasons = {}
_game_snaps = {}
_season_snaps = {}
_game_builder = None
_season_step = None
_thread = None
_autostart = True


def register_game_builder(builder):
    """``builder(org, game_id, league, previous, fingerprint)`` fills one game."""
    global _game_builder
    _game_builder = builder


def register_season_step(step):
    """``step(org, season_id, view, state, now)`` advances one Q6 C step."""
    global _season_step
    _season_step = step


def autostart_enabled():
    return _autostart


def set_autostart(enabled):
    global _autostart
    _autostart = bool(enabled)


def reset():
    """Drop watches and drawers. Registered builders stay."""
    global _epoch
    with _LOCK:
        _epoch += 1
        _games.clear()
        _seasons.clear()
        _game_snaps.clear()
        _season_snaps.clear()


def _touch_game(org, game_id, league, now):
    key = (org, str(game_id))
    slot = _games.get(key)
    if slot is None:
        slot = {'seen': now, 'league': league, 'pending': False}
        _games[key] = slot
    else:
        slot['seen'] = now
        slot['league'] = league
    return key


def note_game(org, game_id, league, now=None):
    """Record that a Game page is open. Does not fetch and does not block."""
    if not org or not game_id:
        return
    moment = time.monotonic() if now is None else now
    with _LOCK:
        _touch_game(org, game_id, league, moment)
    if _autostart:
        start()


def note_season(org, season_id, view, now=None):
    """Record that Team Stats is open. The first note waits one official interval."""
    if not org or not season_id:
        return
    moment = time.monotonic() if now is None else now
    key = (org, str(season_id))
    with _LOCK:
        slot = _seasons.get(key)
        if slot is None:
            slot = {
                'seen': moment,
                'view': dict(view or {}),
                'pending': False,
                'cycle': {
                    'phase': 'idle',
                    'next_due': moment + OFFICIAL_REFRESH_SECONDS,
                    'cursor': 0,
                    'painted': None,
                },
            }
            _seasons[key] = slot
        else:
            slot['seen'] = moment
            slot['view'] = dict(view or {})
    if _autostart:
        start()


def peek_game(org, game_id):
    """Return the latest store strings, or None when this game has no snapshot."""
    key = (org, str(game_id))
    with _LOCK:
        snap = _game_snaps.get(key)
        if not snap:
            return None
        return {
            'stores': dict(snap.get('stores') or {}),
            'fingerprint': snap.get('fingerprint'),
        }


def game_pending(org, game_id):
    """True while a build is running or the open game has never produced a snapshot."""
    key = (org, str(game_id))
    with _LOCK:
        slot = _games.get(key)
        if slot is None:
            return False
        if slot.get('pending'):
            return True
        return key not in _game_snaps


def peek_season(org, season_id):
    key = (org, str(season_id))
    with _LOCK:
        snap = _season_snaps.get(key)
        if not snap:
            return None
        return {
            'payload': snap.get('payload'),
            'generation': int(snap.get('generation') or 0),
            'view': dict(snap.get('view') or {}),
        }


def _expire(now):
    stale_games = [
        key for key, slot in _games.items()
        if now - slot.get('seen', now) >= WATCH_SECONDS
    ]
    for key in stale_games:
        _games.pop(key, None)
    stale_seasons = [
        key for key, slot in _seasons.items()
        if now - slot.get('seen', now) >= WATCH_SECONDS
    ]
    for key in stale_seasons:
        _seasons.pop(key, None)


def _soon_game(now):
    due = []
    for key, slot in _games.items():
        if slot.get('pending'):
            continue
        last = slot.get('last_run')
        kind = slot.get('kind')
        if last is None or (kind == 'live' and now - last >= LIVE_CADENCE_SECONDS):
            due.append((last is not None, 0 if last is None else last, key))
    if not due:
        return None
    due.sort()
    return due[0][2]


def _official_game(now):
    due = []
    for key, slot in _games.items():
        if slot.get('pending') or slot.get('kind') != 'official':
            continue
        last = slot.get('last_run')
        if last is None or now - last >= OFFICIAL_REFRESH_SECONDS:
            due.append((last or 0, key))
    if not due:
        return None
    due.sort()
    return due[0][1]


def _season_job(now):
    for key, slot in _seasons.items():
        if slot.get('pending'):
            continue
        cycle = slot.get('cycle') or {}
        if cycle.get('phase') == 'games':
            return key
    for key, slot in _seasons.items():
        if slot.get('pending'):
            continue
        cycle = slot.get('cycle') or {}
        if cycle.get('phase') != 'games' and now >= cycle.get('next_due', now + 1):
            return key
    return None


def _pick(now):
    game_key = _soon_game(now)
    if game_key is not None and _game_builder is not None:
        return ('game', game_key)
    season_key = _season_job(now)
    if season_key is not None and _season_step is not None:
        cycle = (_seasons.get(season_key) or {}).get('cycle') or {}
        if cycle.get('phase') == 'games' or _official_game(now) is None:
            return ('season', season_key)
    official_key = _official_game(now)
    if official_key is not None and _game_builder is not None:
        return ('game', official_key)
    if season_key is not None and _season_step is not None:
        return ('season', season_key)
    return None


def _mark_pending(kind, key, pending):
    table = _games if kind == 'game' else _seasons
    slot = table.get(key)
    if slot is not None:
        slot['pending'] = pending


def _execute(kind, key, now, epoch):
    if kind == 'game':
        _execute_game(key, now, epoch)
    else:
        _execute_season(key, now, epoch)


def _execute_game(key, now, epoch):
    with _LOCK:
        if epoch != _epoch or key not in _games:
            return
        slot = _games[key]
        snap = _game_snaps.get(key) or {}
        previous = dict(snap.get('stores') or {}) or None
        fingerprint = slot.get('fingerprint')
        league = slot.get('league')
        org, game_id = key
        builder = _game_builder
    if builder is None:
        return
    result = builder(org, game_id, league, previous, fingerprint) or {}
    with _LOCK:
        if epoch != _epoch or key not in _games:
            return
        slot = _games[key]
        slot['last_run'] = now
        slot['kind'] = result.get('kind') or 'official'
        if 'fingerprint' in result:
            slot['fingerprint'] = result.get('fingerprint')
        stores = result.get('stores')
        if stores and any(value is not None for value in stores.values()):
            _game_snaps[key] = {
                'stores': dict(stores),
                'fingerprint': result.get('fingerprint'),
            }


def _execute_season(key, now, epoch):
    with _LOCK:
        if epoch != _epoch or key not in _seasons:
            return
        slot = _seasons[key]
        view = dict(slot.get('view') or {})
        cycle = dict(slot.get('cycle') or {})
        org, season_id = key
        step = _season_step
    if step is None:
        return
    try:
        new_cycle, payload = step(org, season_id, view, cycle, now)
    except Exception:
        from synergy_inbounder.logs import unexpected
        unexpected.exception('watched season step failed org=%s season=%s', org, season_id)
        new_cycle = dict(cycle)
        new_cycle['phase'] = 'idle'
        new_cycle['next_due'] = now + OFFICIAL_REFRESH_SECONDS
        payload = None
    with _LOCK:
        if epoch != _epoch or key not in _seasons:
            return
        slot = _seasons[key]
        slot['cycle'] = dict(new_cycle or {})
        if payload is not None:
            generation = int((_season_snaps.get(key) or {}).get('generation') or 0) + 1
            _season_snaps[key] = {
                'payload': payload,
                'generation': generation,
                'view': dict(view),
            }


def _backoff(kind, key, now, epoch):
    with _LOCK:
        if epoch != _epoch:
            return
        table = _games if kind == 'game' else _seasons
        slot = table.get(key)
        if slot is None:
            return
        slot['last_run'] = now
        if kind == 'game' and not slot.get('kind'):
            slot['kind'] = 'official'
        if kind == 'season':
            cycle = dict(slot.get('cycle') or {})
            cycle['phase'] = 'idle'
            cycle['next_due'] = now + OFFICIAL_REFRESH_SECONDS
            slot['cycle'] = cycle


def run_once(now=None):
    """Run at most one heavy job. ``None`` means nothing was due."""
    moment = time.monotonic() if now is None else now
    with _LOCK:
        epoch = _epoch
        _expire(moment)
        picked = _pick(moment)
        if picked is None:
            return None
        kind, key = picked
        _mark_pending(kind, key, True)
    try:
        _execute(kind, key, moment, epoch)
    except Exception:
        from synergy_inbounder.logs import unexpected
        unexpected.exception('publisher job failed kind=%s', kind)
        _backoff(kind, key, moment, epoch)
    finally:
        with _LOCK:
            if epoch == _epoch:
                _mark_pending(kind, key, False)
    return kind


def _loop():
    while True:
        worked = None
        try:
            worked = run_once()
        except Exception:
            from synergy_inbounder.logs import unexpected
            unexpected.exception('publisher loop failed')
        time.sleep(0.4 if worked else 1.0)


def start():
    """Start the daemon once. Tests that call ``run_once`` leave this off."""
    global _thread
    with _LOCK:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_loop, name='splashboard-publisher', daemon=True)
        _thread.start()
