# -*- coding: utf-8 -*-
import requests
from synergy_inbounder.settings import LOGGER
from synergy_inbounder.settings import SYNERGY_TOKEN_URL, \
        SYNERGY_SEASON_GAME_LIST_URL, \
        SYNERGY_PLAY_BY_PLAY_URL, \
        SYNERGY_PLAYER_STATS_URL, SYNERGY_TEAM_STATS_URL, \
        SYNERGY_ORG_PERSONS_URL, SYNERGY_ORG_ENTITIES_URL, \
        SYNERGY_ORG_VENUES_URL, \
        SYNERGY_CREDENTIAL_ID, SYNERGY_CREDENTIAL_SECRET, SYNERGY_BEARER, \
        SYNERGY_ORGANIZATION_ID

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
    def get_synergy(url, params=dict(), headers=dict(), **kwargs):
        global SYNERGY_BEARER
        r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(SYNERGY_BEARER), **kwargs)

        if r.status_code == requests.codes.forbidden:
            SYNERGY_BEARER = Communicator.post_synergy_for_token().json().get('data', {}).get('token')
            r = Communicator.get(url, params=params, headers=headers, auth=BearerAuth(SYNERGY_BEARER), **kwargs)
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
    def get_game_player_stats_synergy(org_id, game_id):
        url = SYNERGY_PLAYER_STATS_URL.format(organizationId=org_id, fixtureId=game_id)
        params = {'limit': 1000, 'isPlayer': 'true'}
        r = Communicator.get_synergy(url, params=params)
        return r.json()

    @staticmethod
    def get_game_play_by_play_synergy(org_id, game_id, period_id):
        url = SYNERGY_PLAY_BY_PLAY_URL.format(organizationId=org_id, fixtureId=game_id)
        params = {'periodId': period_id}
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
