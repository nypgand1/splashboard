# -*- coding: utf-8 -*-
import threading
import time

import requests
import requests_cache

from synergy_inbounder.settings import LOGGER
from synergy_inbounder.live_budget import BUDGET, SHORT_CACHE_SECONDS, LONG_CACHE_SECONDS, live_route
from synergy_inbounder.runtime_cache import LIVE_PBP_HTTP_TTL_SECONDS
from synergy_inbounder.settings import SYNERGY_TOKEN_URL, \
        SYNERGY_SEASON_GAME_LIST_URL, \
        SYNERGY_PLAY_BY_PLAY_URL, SYNERGY_PLAY_BY_PLAY_LIVE_URL, \
        SYNERGY_PLAYER_STATS_URL, SYNERGY_PLAYER_STATS_LIVE_URL, \
        SYNERGY_PLAYER_STATS_PERIODS_URL, SYNERGY_PLAYER_STATS_PERIODS_LIVE_URL, \
        SYNERGY_TEAM_STATS_URL, SYNERGY_TEAM_STATS_LIVE_URL, \
        SYNERGY_TEAM_STATS_PERIODS_URL, SYNERGY_TEAM_STATS_PERIODS_LIVE_URL, \
        SYNERGY_FIXTURE_ROSTER_URL, \
        SYNERGY_ORG_PERSONS_URL, SYNERGY_ORG_ENTITIES_URL, \
        SYNERGY_ORG_VENUES_URL, \
        SYNERGY_ORGANIZATION_ID, SYNERGY_EASL_ORGANIZATION_ID, \
        get_synergy_credentials

TOKEN_EXPIRY_SKEW_SECONDS = 60

def _catalog_ttl(org_id):
    return {
        SYNERGY_ORG_PERSONS_URL.format(organizationId=org_id): LONG_CACHE_SECONDS,
        SYNERGY_ORG_ENTITIES_URL.format(organizationId=org_id): LONG_CACHE_SECONDS,
        SYNERGY_ORG_VENUES_URL.format(organizationId=org_id): LONG_CACHE_SECONDS,
    }


urls_expire_after = {'*/playbyplay/live': LIVE_PBP_HTTP_TTL_SECONDS}
for _org_id in (SYNERGY_ORGANIZATION_ID, SYNERGY_EASL_ORGANIZATION_ID):
    urls_expire_after.update(_catalog_ttl(_org_id))

requests_cache.install_cache(
        'synergy_communicator_cache',
        expire_after=SHORT_CACHE_SECONDS,
        urls_expire_after=urls_expire_after,
        allowable_codes=(200,),
        check_same_thread=False,
        timeout=30.0,
)

_token_lock = threading.Lock()
_token_slots = {}
_active_org = None


def _empty_slot():
    return {'bearer': None, 'generation': 0, 'expires_at': 0.0}


def _token_slot(org_id):
    slot = _token_slots.get(org_id)
    if slot is None:
        slot = _empty_slot()
        _token_slots[org_id] = slot
    return slot

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        r.headers['authorization'] = 'Bearer ' + self.token
        return r

class SynergyApiError(RuntimeError):
    pass


class SynergyAuthError(SynergyApiError):
    pass


def drop_cached_live_urls(game_id):
    """Drop partial /live HTTP hits for one fixture so the next bundle is one generation."""
    if not game_id:
        return
    try:
        cache = requests_cache.get_cache()
        if cache is None:
            return
        marker = '/{game_id}'.format(game_id=game_id)
        urls = []
        for url in cache.urls():
            path = (url or '').split('?', 1)[0]
            if not path.endswith('/live'):
                continue
            start = path.find(marker)
            if start < 0:
                continue
            end = start + len(marker)
            if end == len(path) or path[end] == '/':
                urls.append(url)
        if urls:
            cache.delete(urls=urls)
    except Exception:
        return


def payload_from_response(response, url=''):
    status = getattr(response, 'status_code', None)
    if status in (requests.codes.unauthorized, requests.codes.forbidden):
        raise SynergyAuthError('Synergy {status} for {url}'.format(status=status, url=url or getattr(response, 'url', '')))
    if status != requests.codes.ok:
        raise SynergyApiError('Synergy {status} for {url}'.format(status=status, url=url or getattr(response, 'url', '')))
    try:
        payload = response.json()
    except ValueError as exc:
        raise SynergyApiError('Synergy returned non-JSON for {url}'.format(url=url)) from exc
    if not isinstance(payload, dict) or 'data' not in payload:
        raise SynergyApiError('Synergy payload missing data for {url}'.format(url=url))
    return payload


class Communicator:
    @staticmethod
    def get(url, params=None, headers=dict(), cached=True, **kwargs):
        if cached:
            r = requests.get(url, params, **kwargs)
        else:
            with requests_cache.disabled():
                r = requests.get(url, params, **kwargs)
        LOGGER.info('{r} GET {url}'.format(r=r, url=url))
        return r

    @staticmethod
    def post_synergy_for_token():
        global _active_org
        url = SYNERGY_TOKEN_URL
        org_id = _active_org or SYNERGY_ORGANIZATION_ID
        credential_id, credential_secret = get_synergy_credentials(org_id)
        r = requests.post(url, json={
                'credentialId': credential_id,
                'credentialSecret': credential_secret,
                'sport': 'basketball',
                'organization': {'id': [org_id]},
                'scopes': ['read:organization', 'read:organization_live']
            }
        )
        LOGGER.info('{r} POST {url}'.format(r=r, url=url))
        return r

    @staticmethod
    def _token_is_fresh(slot):
        return bool(slot['bearer']) and time.monotonic() < slot['expires_at']

    @staticmethod
    def _current_token(org_id):
        with _token_lock:
            slot = _token_slot(org_id)
            if Communicator._token_is_fresh(slot):
                return slot['bearer'], slot['generation']
            return None, slot['generation']

    @staticmethod
    def _set_token(org_id, token, expires_in):
        slot = _token_slot(org_id)
        slot['bearer'] = token
        slot['generation'] += 1
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError):
            lifetime = 0.0
        if lifetime > 0:
            slot['expires_at'] = time.monotonic() + max(1.0, lifetime - TOKEN_EXPIRY_SKEW_SECONDS)
        else:
            slot['expires_at'] = time.monotonic() + 3600.0
        LOGGER.info('Refreshed Synergy bearer token (generation {g})'.format(g=slot['generation']))

    @staticmethod
    def _refresh_token(org_id, seen_generation=None):
        global _active_org
        with _token_lock:
            slot = _token_slot(org_id)
            if seen_generation is None and Communicator._token_is_fresh(slot):
                return slot['bearer'], slot['generation']
            if seen_generation is not None and slot['generation'] != seen_generation:
                return slot['bearer'], slot['generation']
            _active_org = org_id
            r = Communicator.post_synergy_for_token()
            payload = r.json() or {}
            token = payload.get('data', {}).get('token')
            if not token:
                raise RuntimeError('Synergy token refresh returned no token')
            Communicator._set_token(org_id, token, payload.get('data', {}).get('expiresIn'))
            slot = _token_slot(org_id)
            return slot['bearer'], slot['generation']

    @staticmethod
    def reset_token_state():
        global _active_org
        with _token_lock:
            _token_slots.clear()
            _active_org = None

    @staticmethod
    def _note_live_response(org_id, url, response):
        route = live_route(url)
        if not route or getattr(response, 'from_cache', False):
            if route and getattr(response, 'from_cache', False):
                BUDGET.refund(org_id, route)
            return response
        if response.status_code == 429:
            header = getattr(response, 'headers', {}) or {}
            BUDGET.note_429(org_id, header.get('Retry-After'))
        return response

    @staticmethod
    def get_synergy(url, params=dict(), headers=dict(), organization_id=None, cached=True, **kwargs):
        org_id = organization_id or SYNERGY_ORGANIZATION_ID
        token, generation = Communicator._current_token(org_id)
        if not token:
            token, generation = Communicator._refresh_token(org_id)
        route = live_route(url)
        if route and not BUDGET.in_hold(org_id):
            if not BUDGET.try_spend(org_id, route):
                raise SynergyApiError('Live budget exhausted for {url}'.format(url=url))
        r = Communicator.get(
            url, params=params, headers=headers, auth=BearerAuth(token), cached=cached, **kwargs,
        )
        r = Communicator._note_live_response(org_id, url, r)

        if r.status_code in (requests.codes.unauthorized, requests.codes.forbidden):
            token, generation = Communicator._refresh_token(org_id, seen_generation=generation)
            if route is None or BUDGET.allow_retry(org_id, route):
                r = Communicator.get(
                    url, params=params, headers=headers, auth=BearerAuth(token), cached=cached, **kwargs,
                )
                r = Communicator._note_live_response(org_id, url, r)
        if r.status_code >= 500 and (route is None or BUDGET.allow_retry(org_id, route)):
            r = Communicator.get(
                url, params=params, headers=headers, auth=BearerAuth(token), cached=cached, **kwargs,
            )
            r = Communicator._note_live_response(org_id, url, r)
        return r

    @staticmethod
    def _stats_url(official_url, live_url, live):
        return live_url if live else official_url

    @staticmethod
    def get_season_game_list(org_id, season_id):
        url = SYNERGY_SEASON_GAME_LIST_URL.format(organizationId=org_id, seasonId=season_id)
        params = {'limit': 1000, 'sortBy': 'startTimeUTC'}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id, cached=False)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_team_stats_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(SYNERGY_TEAM_STATS_URL, SYNERGY_TEAM_STATS_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        r = Communicator.get_synergy(url, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_team_stats_periods_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(SYNERGY_TEAM_STATS_PERIODS_URL, SYNERGY_TEAM_STATS_PERIODS_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        r = Communicator.get_synergy(url, organization_id=org_id)
        return payload_from_response(r, url=url)
 
    @staticmethod
    def get_game_player_stats_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(SYNERGY_PLAYER_STATS_URL, SYNERGY_PLAYER_STATS_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000, 'isPlayer': 'true'}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_player_stats_periods_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(
            SYNERGY_PLAYER_STATS_PERIODS_URL,
            SYNERGY_PLAYER_STATS_PERIODS_LIVE_URL,
            live,
        )
        url = url.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_play_by_play_synergy(org_id, game_id, period_id=None, live=True):
        url = Communicator._stats_url(SYNERGY_PLAY_BY_PLAY_URL, SYNERGY_PLAY_BY_PLAY_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 2000}
        if period_id:
            params['periodId'] = period_id
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_fixture_roster_synergy(org_id, game_id):
        url = SYNERGY_FIXTURE_ROSTER_URL.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_org_persons_synergy(org_id):
        url = SYNERGY_ORG_PERSONS_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_org_entities_synergy(org_id):
        url = SYNERGY_ORG_ENTITIES_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_org_venues_synergy(org_id):
        url = SYNERGY_ORG_VENUES_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params, organization_id=org_id)
        return payload_from_response(r, url=url)
