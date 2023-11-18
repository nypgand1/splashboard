# -*- coding: utf-8 -*-
import logging

LOGGER_FORMAT = '%(levelname)s: %(asctime)-15s: %(message)s'
logging.basicConfig(format=LOGGER_FORMAT, level=logging.INFO)
LOGGER = logging.getLogger('FibaInbounder')

SYNERGY_TOKEN_URL = 'https://token.prod.cloud.atriumsports.com/v1/oauth2/rest/token'
SYNERGY_SEASON_GAME_LIST_URL = 'https://api.dc.prod.cloud.atriumsports.com/v1/basketball/o/{organizationId}/seasons/{seasonId}/fixtures'
SYNERGY_PLAY_BY_PLAY_URL = 'https://api.dc.prod.cloud.atriumsports.com/v1/basketball/o/{organizationId}/fixtures/{fixtureId}/playbyplay/live'
SYNERGY_PLAYER_STATS_URL = 'https://api.dc.prod.cloud.atriumsports.com/v1/basketball/o/{organizationId}/statistics/for/person/in/fixtures/{fixtureId}/live'
SYNERGY_ORG_PERSONS_URL = 'https://api.dc.prod.cloud.atriumsports.com/v1/basketball/o/{organizationId}/persons'
SYNERGY_ORG_ENTITIES_URL = 'https://api.dc.prod.cloud.atriumsports.com/v1/basketball/o/{organizationId}/entities'
SYNERGY_ORG_VENUES_URL = 'https://api.dc.prod.cloud.atriumsports.com/v1/basketball/o/{organizationId}/venues'

SYNERGY_CREDENTIAL_ID = '213ZjhWhtFf4AWNu6kwULbQ49kgyUz'
SYNERGY_CREDENTIAL_SECRET = 'hgjCozSsvhHfdzzVdsCCp16EmzLhie'
SYNERGY_BEARER = 'token'

SYNERGY_ORGANIZATION_ID = 'b1vqz'

SYNERGY_SEASON_ID_PRE_22_23 = 'e24ebe03-3e5b-11ed-a1a4-977d7240edca'
SYNERGY_SEASON_ID_REG_22_23 = 'e279bdcf-3e5b-11ed-83e3-977d7240edca'
SYNERGY_SEASON_ID_REG_23_24 = 'e54380a8-4318-11ee-aac9-833b08b75024'
SYNERGY_SEASON_ID = SYNERGY_SEASON_ID_REG_23_24
