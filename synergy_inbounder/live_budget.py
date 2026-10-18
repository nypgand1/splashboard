# -*- coding: utf-8 -*-
"""Process-local live-route budget. One process, one machine."""
import threading
import time

LIVE_CADENCE_SECONDS = 35
SHORT_CACHE_SECONDS = 30
LONG_CACHE_SECONDS = 2 * 60 * 60
LIVE_ROUTE_LIMIT = 2
LIVE_ROUTE_WINDOW_SECONDS = 60
LIVE_SLOT_SECONDS = 35
WATCH_SECONDS = 70
RETRY_AFTER_DEFAULT_SECONDS = 60

LIVE_ROUTES = (
    'team',
    'team_periods',
    'player',
    'player_periods',
    'pbp',
)


def live_route(url):
    path = (url or '').split('?', 1)[0]
    if not path.endswith('/live'):
        return None
    if path.endswith('/playbyplay/live'):
        return 'pbp'
    if '/for/person/' in path and path.endswith('/periods/live'):
        return 'player_periods'
    if '/for/entity/' in path and path.endswith('/periods/live'):
        return 'team_periods'
    if '/for/person/' in path:
        return 'player'
    if '/for/entity/' in path:
        return 'team'
    return 'live'


def parse_retry_after(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return RETRY_AFTER_DEFAULT_SECONDS
    if seconds < 0:
        return RETRY_AFTER_DEFAULT_SECONDS
    return seconds


class LiveBudget:
    def __init__(self):
        self._lock = threading.Lock()
        self._polls = {}
        self._origins = {}
        self._last_bundle = {}
        self._last_fetch = {}
        self._cooldown_until = {}
        self._holds = {}

    def clear(self):
        with self._lock:
            self._polls.clear()
            self._origins.clear()
            self._last_bundle.clear()
            self._last_fetch.clear()
            self._cooldown_until.clear()
            self._holds.clear()

    def forget(self, org, game_id):
        with self._lock:
            polls = self._polls.get(org)
            if polls:
                polls.pop(game_id, None)
            fetched = self._last_fetch.get(org)
            if fetched:
                fetched.pop(game_id, None)

    def acquire(self, org, game_id, has_snapshot, age_seconds, now):
        """Return fetch, serve, or delay. A fetch reserves one call on every live route."""
        with self._lock:
            self._note_poll(org, game_id, now)
            action = self._decide(org, game_id, has_snapshot, age_seconds, now)
            if action == 'fetch':
                self._reserve(org, now)
                self._last_fetch.setdefault(org, {})[game_id] = now
            return action

    def in_hold(self, org):
        with self._lock:
            return self._holds.get(org, 0) > 0

    def release(self, org):
        with self._lock:
            remaining = self._holds.get(org, 0) - 1
            if remaining <= 0:
                self._holds.pop(org, None)
            else:
                self._holds[org] = remaining

    def try_spend(self, org, route, now=None):
        with self._lock:
            moment = time.monotonic() if now is None else now
            if self._cooling(org, moment):
                return False
            if self._count(org, route, moment) >= LIVE_ROUTE_LIMIT:
                return False
            self._origins.setdefault((org, route), []).append(moment)
            return True

    def allow_retry(self, org, route, now=None):
        return self.try_spend(org, route, now=now)

    def refund(self, org, route):
        with self._lock:
            stamps = self._origins.get((org, route))
            if stamps:
                stamps.pop()

    def note_429(self, org, retry_after, now=None):
        with self._lock:
            moment = time.monotonic() if now is None else now
            pause = parse_retry_after(retry_after)
            until = moment + pause
            current = self._cooldown_until.get(org, 0.0)
            if until > current:
                self._cooldown_until[org] = until

    def _note_poll(self, org, game_id, now):
        polls = self._polls.setdefault(org, {})
        polls[game_id] = now
        stale = [gid for gid, seen in polls.items() if now - seen >= WATCH_SECONDS]
        for gid in stale:
            polls.pop(gid, None)
            fetched = self._last_fetch.get(org)
            if fetched:
                fetched.pop(gid, None)

    def _watched(self, org, now):
        polls = self._polls.get(org, {})
        return [gid for gid, seen in polls.items() if now - seen < WATCH_SECONDS]

    def _count(self, org, route, now):
        key = (org, route)
        fresh = [stamp for stamp in self._origins.get(key, []) if now - stamp < LIVE_ROUTE_WINDOW_SECONDS]
        if fresh:
            self._origins[key] = fresh
        elif key in self._origins:
            self._origins.pop(key, None)
        return len(fresh)

    def _budget_open(self, org, now):
        return all(self._count(org, route, now) < LIVE_ROUTE_LIMIT for route in LIVE_ROUTES)

    def _cooling(self, org, now):
        return now < self._cooldown_until.get(org, 0.0)

    def _next_game(self, org, watched):
        fetched = self._last_fetch.get(org, {})

        def rank(gid):
            stamp = fetched.get(gid)
            return (stamp is not None, stamp if stamp is not None else 0.0, str(gid))

        return min(watched, key=rank)

    def _reserve(self, org, now):
        for route in LIVE_ROUTES:
            self._origins.setdefault((org, route), []).append(now)
        self._last_bundle[org] = now
        self._holds[org] = self._holds.get(org, 0) + 1

    def _decide(self, org, game_id, has_snapshot, age_seconds, now):
        watched = self._watched(org, now)
        multi = len(watched) >= 2
        our_turn = (not multi) or game_id == self._next_game(org, watched)
        slot_closed = multi and (now - self._last_bundle.get(org, now - LIVE_SLOT_SECONDS)) < LIVE_SLOT_SECONDS
        if not has_snapshot and not self._cooling(org, now) and self._budget_open(org, now):
            return 'fetch'
        if not our_turn:
            return 'serve' if has_snapshot else 'fail'
        if slot_closed and has_snapshot:
            return 'serve'
        if not multi and has_snapshot and age_seconds < SHORT_CACHE_SECONDS:
            return 'serve'
        if self._cooling(org, now):
            return 'delay' if has_snapshot else 'fail'
        if not self._budget_open(org, now):
            return 'serve' if has_snapshot else 'fail'
        return 'fetch'


BUDGET = LiveBudget()
