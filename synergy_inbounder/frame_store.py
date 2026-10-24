# -*- coding: utf-8 -*-
"""Parsed fixture frames shared by Game and Team Stats.

The store keeps play-by-play, that game's team totals, and that game's team
period rows. Lineup, Rotation, and Team Stats cards are derived and are not
stored. CONFIRMED pieces stay while pinned. FINISHED pieces may be rebuilt
after 30 seconds. Changing the Team Stats season drops frames pinned only by
the previous season.
"""
import threading
import time
from concurrent.futures import Future

from synergy_inbounder.game_status import normalize_status
from synergy_inbounder.live_budget import SHORT_CACHE_SECONDS

_lock = threading.Lock()
_frames = {}
_inflight = {}
_open_pins = {}
_home_pins = {}
_season_pins = {}


class FixtureFrame(object):
    def __init__(self, organization_id, fixture_id):
        self.organization_id = organization_id
        self.fixture_id = str(fixture_id)
        self.status = ''
        self.playbyplay_df = None
        self.team_df = None
        self.periods_df = None
        self.pbp_failed = False
        self.times = {}


def clear():
    with _lock:
        _frames.clear()
        _inflight.clear()
        _open_pins.clear()
        _home_pins.clear()
        _season_pins.clear()


def _key(organization_id, fixture_id):
    return (organization_id, str(fixture_id))


def peek(organization_id, fixture_id):
    with _lock:
        frame = _frames.get(_key(organization_id, fixture_id))
        return frame


def piece_fresh(frame, piece, now=None):
    """True when the piece should not be downloaded again."""
    if frame is None:
        return False
    moment = time.monotonic() if now is None else now
    if piece == 'playbyplay_df' and frame.pbp_failed:
        fetched = frame.times.get(piece)
        return fetched is not None and (moment - fetched) < SHORT_CACHE_SECONDS
    value = getattr(frame, piece, None)
    if value is None:
        return False
    if normalize_status(frame.status) == 'CONFIRMED':
        return True
    fetched = frame.times.get(piece)
    if fetched is None:
        return False
    return (moment - fetched) < SHORT_CACHE_SECONDS


def store(organization_id, fixture_id, status=None, playbyplay_df=None, team_df=None,
          periods_df=None, pbp_failed=False, touch=None):
    """Merge pieces. ``touch`` names the pieces whose clock should move."""
    touched = set(touch or ())
    now = time.monotonic()
    with _lock:
        key = _key(organization_id, fixture_id)
        frame = _frames.get(key)
        if frame is None:
            frame = FixtureFrame(organization_id, fixture_id)
            _frames[key] = frame
        if status:
            incoming = normalize_status(status)
            if incoming == 'CONFIRMED' or not frame.status:
                frame.status = incoming
        if playbyplay_df is not None:
            frame.playbyplay_df = playbyplay_df
            frame.pbp_failed = False
            if 'playbyplay_df' in touched:
                frame.times['playbyplay_df'] = now
        if pbp_failed:
            frame.pbp_failed = True
            frame.playbyplay_df = None
            if 'playbyplay_df' in touched:
                frame.times['playbyplay_df'] = now
        if team_df is not None:
            frame.team_df = team_df
            if 'team_df' in touched:
                frame.times['team_df'] = now
        if periods_df is not None:
            frame.periods_df = periods_df
            if 'periods_df' in touched:
                frame.times['periods_df'] = now
        return frame


def _pinned_ids(organization_id):
    pinned = set()
    open_id = _open_pins.get(organization_id)
    if open_id:
        pinned.add(str(open_id))
    pinned.update(_home_pins.get(organization_id) or ())
    for (org, _season_id), fixture_ids in _season_pins.items():
        if org == organization_id:
            pinned.update(fixture_ids)
    return pinned


def _drop_released(organization_id, released):
    """Drop frames this pin replacement just released. Never-pinned frames stay."""
    pinned = _pinned_ids(organization_id)
    for fixture_id in released:
        if str(fixture_id) not in pinned:
            _frames.pop(_key(organization_id, fixture_id), None)


def pin_open(organization_id, fixture_id):
    if not organization_id or not fixture_id:
        return
    with _lock:
        previous = _open_pins.get(organization_id)
        released = {str(previous)} if previous else set()
        _open_pins[organization_id] = str(fixture_id)
        _drop_released(organization_id, released)


def pin_home(organization_id, fixture_ids):
    if not organization_id:
        return
    with _lock:
        released = set(_home_pins.get(organization_id) or ())
        _home_pins[organization_id] = {str(item) for item in fixture_ids or () if item}
        _drop_released(organization_id, released)


def pin_season(organization_id, season_id, fixture_ids):
    """Replace this season's pin and drop other seasons for the same organization."""
    if not organization_id or not season_id:
        return
    with _lock:
        released = set()
        for key in list(_season_pins):
            if key[0] == organization_id:
                released.update(_season_pins.pop(key) or ())
        _season_pins[(organization_id, season_id)] = {
            str(item) for item in fixture_ids or () if item
        }
        _drop_released(organization_id, released)


def singleflight(key, builder):
    with _lock:
        future = _inflight.get(key)
        if future is None:
            future = Future()
            _inflight[key] = future
            owner = True
        else:
            owner = False
    if not owner:
        return future.result()
    try:
        value = builder()
    except Exception as exc:
        future.set_exception(exc)
        raise
    else:
        future.set_result(value)
        return value
    finally:
        with _lock:
            current = _inflight.get(key)
            if current is future:
                _inflight.pop(key, None)
