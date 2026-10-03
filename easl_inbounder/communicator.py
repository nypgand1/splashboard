# -*- coding: utf-8 -*-
import requests

from easl_inbounder.settings import EASL_MATCHES_URL


class Communicator:
    @staticmethod
    def get_season_matches(season_id):
        response = requests.get(
            EASL_MATCHES_URL,
            params={'seasonId': season_id},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError('EASL matches response must be a list')
        return payload
