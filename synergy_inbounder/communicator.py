# -*- coding: utf-8 -*-
import threading
import time

import requests
import requests_cache

from synergy_inbounder.settings import LOGGER
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
        SYNERGY_ORGANIZATION_ID, \
        get_synergy_credentials

TOKEN_EXPIRY_SKEW_SECONDS = 60

urls_expire_after = {
        SYNERGY_ORG_PERSONS_URL.format(organizationId=SYNERGY_ORGANIZATION_ID): 8*60*60,
        SYNERGY_ORG_ENTITIES_URL.format(organizationId=SYNERGY_ORGANIZATION_ID): 8*60*60,
        SYNERGY_ORG_VENUES_URL.format(organizationId=SYNERGY_ORGANIZATION_ID): 8*60*60,
        '*/playbyplay/live': LIVE_PBP_HTTP_TTL_SECONDS,
}

requests_cache.install_cache(
        'synergy_communicator_cache',
        expire_after=30,
        urls_expire_after=urls_expire_after,
        allowable_codes=(200,),
        check_same_thread=False,
        timeout=30.0,
)

_token_lock = threading.Lock()
_bearer = None
_token_generation = 0
_token_expires_at = 0.0

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        r.headers['authorization'] = 'Bearer ' + self.token
        return r

class SynergyApiError(RuntimeError):
    pass


def payload_from_response(response, url=''):
    status = getattr(response, 'status_code', None)
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
    def get(url, params=None, headers=dict(), **kwargs):
        r = requests.get(url, params, **kwargs)
        LOGGER.info('{r} GET {url}'.format(r=r, url=url))
        return r

    @staticmethod
    def post_synergy_for_token():
        url = SYNERGY_TOKEN_URL
        credential_id, credential_secret = get_synergy_credentials()
        r = requests.post(url, json={
                'credentialId': credential_id,
                'credentialSecret': credential_secret,
                'sport': 'basketball',
                'organization': {'id': [SYNERGY_ORGANIZATION_ID]},
                'scopes': ['read:organization', 'read:organization_live']
            }
        )
        LOGGER.info('{r} POST {url}'.format(r=r, url=url))
        return r

    @staticmethod
    def _token_is_fresh():
        return bool(_bearer) and time.monotonic() < _token_expires_at

    @staticmethod
    def _current_token():
        with _token_lock:
            if Communicator._token_is_fresh():
                return _bearer, _token_generation
            return None, _token_generation

    @staticmethod
    def _set_token(token, expires_in):
        global _bearer, _token_generation, _token_expires_at
        _bearer = token
        _token_generation += 1
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError):
            lifetime = 0.0
        if lifetime > 0:
            _token_expires_at = time.monotonic() + max(1.0, lifetime - TOKEN_EXPIRY_SKEW_SECONDS)
        else:
            _token_expires_at = time.monotonic() + 3600.0
        LOGGER.info('Refreshed Synergy bearer token (generation {g})'.format(g=_token_generation))

    @staticmethod
    def _refresh_token(seen_generation=None):
        global _bearer, _token_generation
        with _token_lock:
            if seen_generation is None and Communicator._token_is_fresh():
                return _bearer, _token_generation
            if seen_generation is not None and _token_generation != seen_generation:
                return _bearer, _token_generation
            r = Communicator.post_synergy_for_token()
            payload = r.json() or {}
            token = payload.get('data', {}).get('token')
            if not token:
                raise RuntimeError('Synergy token refresh returned no token')
            Communicator._set_token(token, payload.get('data', {}).get('expiresIn'))
            return _bearer, _token_generation

    @staticmethod
    def reset_token_state():
        global _bearer, _token_generation, _token_expires_at
        with _token_lock:
            _bearer = None
            _token_generation = 0
            _token_expires_at = 0.0

    @staticmethod
    def get_synergy(url, params=dict(), headers=dict(), **kwargs):
        token, generation = Communicator._current_token()
        if not token:
            token, generation = Communicator._refresh_token()
        r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(token), **kwargs)

        if r.status_code in (requests.codes.unauthorized, requests.codes.forbidden):
            token, generation = Communicator._refresh_token(seen_generation=generation)
            r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(token), **kwargs)
        if r.status_code >= 500:
            r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(token), **kwargs)
        return r

    @staticmethod
    def _stats_url(official_url, live_url, live):
        return live_url if live else official_url

    @staticmethod
    def get_season_game_list(org_id, season_id):
        url = SYNERGY_SEASON_GAME_LIST_URL.format(organizationId=org_id, seasonId=season_id)
        params = {'limit': 1000, 'sortBy': 'startTimeUTC'}
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_team_stats_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(SYNERGY_TEAM_STATS_URL, SYNERGY_TEAM_STATS_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        r = Communicator.get_synergy(url)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_team_stats_periods_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(SYNERGY_TEAM_STATS_PERIODS_URL, SYNERGY_TEAM_STATS_PERIODS_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        r = Communicator.get_synergy(url)
        return payload_from_response(r, url=url)
 
    @staticmethod
    def get_game_player_stats_synergy(org_id, game_id, live=True):
        url = Communicator._stats_url(SYNERGY_PLAYER_STATS_URL, SYNERGY_PLAYER_STATS_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000, 'isPlayer': 'true'}
        r = Communicator.get_synergy(url, params=params)
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
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_game_play_by_play_synergy(org_id, game_id, period_id=None, live=True):
        url = Communicator._stats_url(SYNERGY_PLAY_BY_PLAY_URL, SYNERGY_PLAY_BY_PLAY_LIVE_URL, live)
        url = url.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 2000}
        if period_id:
            params['periodId'] = period_id
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_fixture_roster_synergy(org_id, game_id):
        url = SYNERGY_FIXTURE_ROSTER_URL.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_org_persons_synergy(org_id):
        url = SYNERGY_ORG_PERSONS_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_org_entities_synergy(org_id):
        url = SYNERGY_ORG_ENTITIES_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)

    @staticmethod
    def get_org_venues_synergy(org_id):
        url = SYNERGY_ORG_VENUES_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return payload_from_response(r, url=url)
