# -*- coding: utf-8 -*-
"""Cache Module 2: Unified Finished Fixture Frame Store & Season Bundle State.

Consolidates:
- Per-fixture frames (`playbyplay_df`, `team_df`, `periods_df`, `roster`, `starters`)
- Season bundle state (`schedule`, `totals`, `periods`, `id_table`, `stamp`, `fetched_at`)
- Team rotation per-fixture facts, starters, shirts, and walked rotation summaries
- Pin-based lifecycle eviction (`pin_open` multi-user LRU, `pin_home`, `pin_season`)
- Shared ``SingleflightGroup`` for concurrent fixture downloads
"""
from collections import OrderedDict
import threading
import time

from inbound.cache.singleflight import SingleflightGroup
from synergy_inbounder.game_status import is_finished_status, normalize_status
from synergy_inbounder.live_budget import SHORT_CACHE_SECONDS

OPEN_PIN_LRU_LIMIT = 8
PIN_OPEN_LIMIT = OPEN_PIN_LRU_LIMIT

_lock = threading.Lock()
_singleflight = SingleflightGroup()
_frames = {}
_open_pins = {}
_home_pins = {}
_season_pins = {}

# Consolidated from team_season._bundles
_bundles = {}

# Consolidated from team_rotation (_STARTERS, _SHIRTS, _FACTS, _FACT_ATTEMPTS, _SUMMARIES, _SHIRT_SOURCE)
_starters = {}
_shirts = {}
_facts = {}
_fact_attempts = set()
_summaries = {}
_shirt_source = {}
_STARTERS = _starters
_SHIRTS = _shirts
_FACTS = _facts
_FACT_ATTEMPTS = _fact_attempts
_SUMMARIES = _summaries
_SHIRT_SOURCE = _shirt_source


class FixtureFrame(object):
    def __init__(self, organization_id, fixture_id):
        self.organization_id = organization_id
        self.fixture_id = str(fixture_id)
        self.status = ''
        self.playbyplay_df = None
        self.team_df = None
        self.periods_df = None
        self.roster = None
        self.starters = None
        self.pbp_failed = False
        self.times = {}


def _key(organization_id, fixture_id):
    return (organization_id, str(fixture_id))


def _fact_key(organization_id, fixture_id):
    return (str(organization_id), str(fixture_id))


def clear():
    """Clear all fixture frames, pins, season bundles, and rotation facts."""
    with _lock:
        _frames.clear()
        _open_pins.clear()
        _home_pins.clear()
        _season_pins.clear()
        _bundles.clear()
        _starters.clear()
        _shirts.clear()
        _facts.clear()
        _fact_attempts.clear()
        _summaries.clear()
        _shirt_source.clear()
    _singleflight.clear()


def clear_team_stats_cache():
    with _lock:
        _bundles.clear()


def clear_rotation_cache():
    with _lock:
        _starters.clear()
        _shirts.clear()
        _facts.clear()
        _fact_attempts.clear()
        _summaries.clear()
        _shirt_source.clear()


def peek(organization_id, fixture_id):
    with _lock:
        return _frames.get(_key(organization_id, fixture_id))


def invalidate_piece(organization_id, fixture_id, piece):
    """Drop one parsed piece so the next read does not treat it as fresh."""
    with _lock:
        frame = _frames.get(_key(organization_id, fixture_id))
        if frame is None:
            return
        setattr(frame, piece, None)
        frame.times.pop(piece, None)
        if piece == 'playbyplay_df':
            frame.pbp_failed = False


def mark_stale(organization_id, fixture_id):
    """Drop parsed pieces so a watched official refetch is not served from memory.

    ``piece_fresh`` treats a ``CONFIRMED`` piece as fresh whenever the value is
    present, so clearing the timestamp alone does not bypass it.
    """
    with _lock:
        frame = _frames.get(_key(organization_id, fixture_id))
        if frame is None:
            return
        frame.playbyplay_df = None
        frame.team_df = None
        frame.periods_df = None
        frame.roster = None
        frame.times.clear()
        frame.pbp_failed = False


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
          periods_df=None, roster=None, starters=None, pbp_failed=False, touch=None):
    """Merge pieces into a FixtureFrame. ``touch`` names pieces whose timestamp moves."""
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
        if roster is not None:
            frame.roster = roster
        if starters is not None:
            frame.starters = starters
        return frame


def _pinned_ids(organization_id):
    pinned = set()
    open_lru = _open_pins.get(organization_id)
    if isinstance(open_lru, OrderedDict):
        pinned.update(open_lru.keys())
    elif open_lru:
        pinned.add(str(open_lru))
    pinned.update(_home_pins.get(organization_id) or ())
    for (org, _season_id), fixture_ids in _season_pins.items():
        if org == organization_id:
            pinned.update(fixture_ids)
    return pinned


def _drop_released(organization_id, released):
    """Drop frames and rotation summaries released by a pin update."""
    pinned = _pinned_ids(organization_id)
    org_str = str(organization_id)
    for fixture_id in released:
        fid = str(fixture_id)
        if fid not in pinned:
            _frames.pop(_key(organization_id, fid), None)
            fkey = _fact_key(organization_id, fid)
            _starters.pop(fkey, None)
            _facts.pop(fkey, None)
            _fact_attempts.discard(fkey)
            for skey in [k for k in _summaries if k[0] == org_str and k[1] == fid]:
                _summaries.pop(skey, None)


def pin_open(organization_id, fixture_id, max_open=OPEN_PIN_LRU_LIMIT):
    """Pin an open game in a bounded per-org LRU so concurrent users don't evict each other."""
    if not organization_id or not fixture_id:
        return
    fid = str(fixture_id)
    limit = max(1, int(max_open))
    with _lock:
        lru = _open_pins.get(organization_id)
        if not isinstance(lru, OrderedDict):
            lru = OrderedDict()
            _open_pins[organization_id] = lru
        if fid in lru:
            lru.move_to_end(fid)
            return
        lru[fid] = True
        released = set()
        while len(lru) > limit:
            oldest, _ = lru.popitem(last=False)
            released.add(str(oldest))
        if released:
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
    return _singleflight.do(key, builder)


# --- Season Bundle State (formerly team_season._bundles) ---

def get_season_bundle(org_id, season_id):
    with _lock:
        return _bundles.get((org_id, season_id))


def has_season_bundle(org_id, season_id):
    with _lock:
        return (org_id, season_id) in _bundles


def store_season_bundle(org_id, season_id, entry):
    schedule = entry.get('schedule') or []
    finished_ids = [
        str(row.get('fixtureId'))
        for row in schedule
        if is_finished_status(row.get('status')) and row.get('fixtureId')
    ]
    with _lock:
        _bundles[(org_id, season_id)] = entry
    pin_season(org_id, season_id, finished_ids)


# --- Team Rotation Facts / Starters / Shirts / Summaries (thread-safe) ---

def get_fixture_starters(org_id, fixture_id):
    with _lock:
        return _starters.get(_fact_key(org_id, fixture_id))


def set_fixture_starters(org_id, fixture_id, starters):
    with _lock:
        _starters[_fact_key(org_id, fixture_id)] = starters


def get_fixture_facts(org_id, fixture_id):
    with _lock:
        return list(_facts.get(_fact_key(org_id, fixture_id)) or ())


def is_fact_attempted(org_id, fixture_id):
    with _lock:
        return _fact_key(org_id, fixture_id) in _fact_attempts


def get_team_shirts(team_id):
    with _lock:
        return dict(_shirts.get(str(team_id)) or {})


def snapshot_all_shirts():
    with _lock:
        return {team: dict(people) for team, people in _shirts.items()}


def remember_team_shirts(team_id, roster):
    with _lock:
        for row in roster or []:
            if str(row.get('entityId')) != str(team_id) or not row.get('personId'):
                continue
            number = row.get('shirtNumber')
            if number in (None, ''):
                continue
            _shirts.setdefault(str(team_id), {})[str(row['personId'])] = number


def _store_shirt_locked(team_id, person_id, number, source):
    if number in (None, '') or not team_id or not person_id:
        return
    key = (str(team_id), str(person_id))
    if _shirt_source.get(key) == 'roster' and source != 'roster':
        return
    _shirts.setdefault(key[0], {})[key[1]] = number
    _shirt_source[key] = 'roster' if source == 'roster' else 'stats'


def absorb_fixture_facts(org_id, fixture_id, roster_rows, stats_rows, merged_rows):
    fkey = _fact_key(org_id, fixture_id)
    with _lock:
        _facts[fkey] = list(merged_rows or ())
        roster_people = set()
        for row in roster_rows or ():
            person_id = row.get('personId')
            team_id = row.get('entityId')
            number = row.get('shirtNumber')
            if number in (None, '') or not person_id or not team_id:
                continue
            roster_people.add((str(team_id), str(person_id)))
            _store_shirt_locked(team_id, person_id, number, 'roster')
        for row in merged_rows or ():
            team_id = row.get('entityId')
            person_id = row.get('personId')
            if (str(team_id), str(person_id)) in roster_people:
                continue
            _store_shirt_locked(team_id, person_id, row.get('shirtNumber'), 'stats')
        _fact_attempts.add(fkey)


def get_rotation_summary(org_id, fixture_id, pbp_id):
    with _lock:
        return _summaries.get((str(org_id), str(fixture_id), pbp_id))


def set_rotation_summary(org_id, fixture_id, pbp_id, summary):
    with _lock:
        _summaries[(str(org_id), str(fixture_id), pbp_id)] = summary


def store_shirt(team_id, person_id, number, source):
    with _lock:
        _store_shirt_locked(team_id, person_id, number, source)


def open_pinned_keys():
    with _lock:
        out = []
        for org_id, lru in _open_pins.items():
            if isinstance(lru, OrderedDict):
                for fid in lru.keys():
                    out.append((org_id, str(fid)))
            elif lru:
                out.append((org_id, str(lru)))
        return out


def put_frame(organization_id, fixture_id, frame, pin=None):
    with _lock:
        _frames[_key(organization_id, fixture_id)] = frame
    if pin == 'open':
        pin_open(organization_id, fixture_id)


def get_frame(organization_id, fixture_id):
    return peek(organization_id, fixture_id)


def clear_frames():
    clear()


def put_bundle(key, value):
    with _lock:
        _bundles[key] = value


def get_bundle(key):
    with _lock:
        return _bundles.get(key)


def clear_bundles():
    clear_team_stats_cache()


def put_rotation_facts(key, value):
    with _lock:
        _facts[key] = value


def rotation_facts(key):
    with _lock:
        return _facts.get(key)
