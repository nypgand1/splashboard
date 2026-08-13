# -*- coding: utf-8 -*-
import threading

import requests
import requests_cache

from synergy_inbounder.settings import LOGGER
from synergy_inbounder.settings import SYNERGY_TOKEN_URL, \
        SYNERGY_SEASON_GAME_LIST_URL, \
        SYNERGY_PLAY_BY_PLAY_URL, \
        SYNERGY_PLAYER_STATS_URL, SYNERGY_TEAM_STATS_URL, SYNERGY_TEAM_STATS_PERIODS_URL, \
        SYNERGY_ORG_PERSONS_URL, SYNERGY_ORG_ENTITIES_URL, \
        SYNERGY_ORG_VENUES_URL, \
        SYNERGY_CREDENTIAL_ID, SYNERGY_CREDENTIAL_SECRET, \
        SYNERGY_ORGANIZATION_ID

urls_expire_after = {
        SYNERGY_ORG_PERSONS_URL.format(organizationId=SYNERGY_ORGANIZATION_ID): 8*60*60,
        SYNERGY_ORG_ENTITIES_URL.format(organizationId=SYNERGY_ORGANIZATION_ID): 8*60*60,
        SYNERGY_ORG_VENUES_URL.format(organizationId=SYNERGY_ORGANIZATION_ID): 8*60*60,
        '*/playbyplay/live': 3*60
}

requests_cache.install_cache(
        'synergy_communicator_cache',
        expire_after=30,
        urls_expire_after=urls_expire_after,
        check_same_thread=False,
        timeout=30.0,
)

_token_lock = threading.Lock()
_bearer = None
_token_generation = 0

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        r.headers['authorization'] = 'Bearer ' + self.token
        return r

class Communicator:
    @staticmethod
    def get(url, params=None, headers=dict(), **kwargs):
        r = requests.get(url, params, **kwargs)
        LOGGER.info('{r} GET {url}'.format(r=r, url=url))
        return r

    @staticmethod
    def post_synergy_for_token():
        url = SYNERGY_TOKEN_URL
        r = requests.post(url, json={
                'credentialId': SYNERGY_CREDENTIAL_ID,
                'credentialSecret': SYNERGY_CREDENTIAL_SECRET,
                'sport': 'basketball',
                'organization': {'id': [SYNERGY_ORGANIZATION_ID]},
                'scopes': ['read:organization', 'read:organization_live']
            }
        )
        LOGGER.info('{r} POST {url}'.format(r=r, url=url))
        return r

    @staticmethod
    def _current_token():
        with _token_lock:
            return _bearer, _token_generation

    @staticmethod
    def _refresh_token(seen_generation=None):
        global _bearer, _token_generation
        with _token_lock:
            if seen_generation is None and _bearer:
                return _bearer, _token_generation
            if seen_generation is not None and _token_generation != seen_generation:
                return _bearer, _token_generation
            r = Communicator.post_synergy_for_token()
            token = (r.json() or {}).get('data', {}).get('token')
            if not token:
                raise RuntimeError('Synergy token refresh returned no token')
            _bearer = token
            _token_generation += 1
            LOGGER.info('Refreshed Synergy bearer token (generation {g})'.format(g=_token_generation))
            return _bearer, _token_generation

    @staticmethod
    def reset_token_state():
        global _bearer, _token_generation
        with _token_lock:
            _bearer = None
            _token_generation = 0

    @staticmethod
    def get_synergy(url, params=dict(), headers=dict(), **kwargs):
        token, generation = Communicator._current_token()
        if not token:
            token, generation = Communicator._refresh_token()
        r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(token), **kwargs)

        if r.status_code == requests.codes.forbidden:
            token, generation = Communicator._refresh_token(seen_generation=generation)
            r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(token), **kwargs)
        return r

    @staticmethod
    def get_season_game_list(org_id, season_id):
        url = SYNERGY_SEASON_GAME_LIST_URL.format(organizationId=org_id, seasonId=season_id)
        params = {'limit': 1000, 'sortBy': 'startTimeUTC'}
        r = Communicator.get_synergy(url, params=params)
        return r.json()

    @staticmethod
    def get_game_team_stats_synergy(org_id, game_id):
        url = SYNERGY_TEAM_STATS_URL.format(organizationId=org_id, fixtureId=game_id)
        r = Communicator.get_synergy(url)
        return r.json()

    @staticmethod
    def get_game_team_stats_periods_synergy(org_id, game_id):
        url = SYNERGY_TEAM_STATS_PERIODS_URL.format(organizationId=org_id, fixtureId=game_id)
        r = Communicator.get_synergy(url)
        return r.json()
 
    @staticmethod
    def get_game_player_stats_synergy(org_id, game_id):
        url = SYNERGY_PLAYER_STATS_URL.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000, 'isPlayer': 'true'}
        r = Communicator.get_synergy(url, params=params)
        return r.json()

    @staticmethod
    def get_game_play_by_play_synergy(org_id, game_id, period_id=None):
        url = SYNERGY_PLAY_BY_PLAY_URL.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 2000}
        if period_id:
            params['periodId'] = period_id
        r = Communicator.get_synergy(url, params=params)
        return r.json()       

    @staticmethod
    def get_org_persons_synergy(org_id):
        url = SYNERGY_ORG_PERSONS_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return r.json()

    @staticmethod
    def get_org_entities_synergy(org_id):
        url = SYNERGY_ORG_ENTITIES_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return r.json()

    @staticmethod
    def get_org_venues_synergy(org_id):
        url = SYNERGY_ORG_VENUES_URL.format(organizationId=org_id)
        params = {'limit': 1000}
        r = Communicator.get_synergy(url, params=params)
        return r.json()
