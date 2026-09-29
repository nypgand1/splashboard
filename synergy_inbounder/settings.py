# -*- coding: utf-8 -*-
import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
except ImportError:
    pass

LOGGER_FORMAT = '%(levelname)s: %(asctime)-15s: %(message)s'
logging.basicConfig(format=LOGGER_FORMAT, level=logging.INFO)
LOGGER = logging.getLogger('SynergyInbounder')

SYNERGY_TOKEN_BASE = 'https://token.connect.sportradar.com/v1'
SYNERGY_API_BASE = 'https://api.dc.connect.sportradar.com/v1'
SYNERGY_TOKEN_URL = SYNERGY_TOKEN_BASE + '/oauth2/rest/token'
SYNERGY_SEASON_GAME_LIST_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/seasons/{seasonId}/fixtures'
SYNERGY_PLAY_BY_PLAY_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/fixtures/{fixtureId}/playbyplay'
SYNERGY_PLAY_BY_PLAY_LIVE_URL = SYNERGY_PLAY_BY_PLAY_URL + '/live'
SYNERGY_TEAM_STATS_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/statistics/for/entity/in/fixtures/{fixtureId}'
SYNERGY_TEAM_STATS_LIVE_URL = SYNERGY_TEAM_STATS_URL + '/live'
SYNERGY_TEAM_STATS_PERIODS_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/statistics/for/entity/in/fixtures/{fixtureId}/periods'
SYNERGY_TEAM_STATS_PERIODS_LIVE_URL = SYNERGY_TEAM_STATS_PERIODS_URL + '/live'
SYNERGY_PLAYER_STATS_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/statistics/for/person/in/fixtures/{fixtureId}'
SYNERGY_PLAYER_STATS_LIVE_URL = SYNERGY_PLAYER_STATS_URL + '/live'
SYNERGY_PLAYER_STATS_PERIODS_URL = SYNERGY_PLAYER_STATS_URL + '/periods'
SYNERGY_PLAYER_STATS_PERIODS_LIVE_URL = SYNERGY_PLAYER_STATS_PERIODS_URL + '/live'
SYNERGY_FIXTURE_ROSTER_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/fixtures/{fixtureId}/roster'
SYNERGY_ORG_PERSONS_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/persons'
SYNERGY_ORG_ENTITIES_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/entities'
SYNERGY_ORG_VENUES_URL = SYNERGY_API_BASE + '/basketball/o/{organizationId}/venues'

SYNERGY_BEARER = 'token'

SYNERGY_ORGANIZATION_ID = 'b1vqz'

SYNERGY_SEASON_ID_PRE_22_23 = 'e24ebe03-3e5b-11ed-a1a4-977d7240edca'
SYNERGY_SEASON_ID_REG_22_23 = 'e279bdcf-3e5b-11ed-83e3-977d7240edca'
SYNERGY_SEASON_ID_REG_23_24 = 'e54380a8-4318-11ee-aac9-833b08b75024'
SYNERGY_SEASON_ID_REG_24_25 = 'ab495b22-7563-11ef-9992-67cb519a6043'
SYNERGY_SEASON_ID_REG_25_26 = '00ab711f-938c-11f0-91bb-4b1b779ef3d9'
SYNERGY_SEASON_ID = SYNERGY_SEASON_ID_REG_25_26


class MissingSynergyCredentials(RuntimeError):
    """Raised when token credentials are not in the process environment."""


def get_synergy_credentials():
    credential_id = (os.environ.get('SYNERGY_CREDENTIAL_ID') or '').strip()
    credential_secret = (os.environ.get('SYNERGY_CREDENTIAL_SECRET') or '').strip()
    if not credential_id or not credential_secret:
        raise MissingSynergyCredentials(
            'Missing SYNERGY_CREDENTIAL_ID or SYNERGY_CREDENTIAL_SECRET'
        )
    return credential_id, credential_secret
