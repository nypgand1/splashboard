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

# Newest first. Regular seasons only: no preseason, 熱身賽, ONE_OFF, or Test1.
SYNERGY_SEASONS = (
    ('2026-27', '94b08c7c-bb00-11f1-ba8e-bd03fe15a10b'),
    ('2025-26', '00ab711f-938c-11f0-91bb-4b1b779ef3d9'),
    ('2024-25', 'ab495b22-7563-11ef-9992-67cb519a6043'),
    ('2023-24', 'e54380a8-4318-11ee-aac9-833b08b75024'),
    ('2022-23', 'e279bdcf-3e5b-11ed-83e3-977d7240edca'),
    ('2021-22', 'b84d0073-3d8e-11ed-bbf9-2d934c23ac1b'),
    ('2020-21', 'b6d36761-3d8e-11ed-a1f2-d5490a4ddc81'),
)
SYNERGY_SEASON_ID = dict(SYNERGY_SEASONS)['2025-26']


def plg_season_ids():
    """Default season first, then the rest of SYNERGY_SEASONS."""
    ordered = [SYNERGY_SEASON_ID]
    for _label, season_id in SYNERGY_SEASONS:
        if season_id not in ordered:
            ordered.append(season_id)
    return ordered


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
