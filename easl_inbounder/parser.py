# -*- coding: utf-8 -*-
import pandas as pd

from easl_inbounder.communicator import Communicator

TEAM_TBD = 'TBD'
SCHEDULE_COLUMNS = (
    'startTimeLocal',
    'fixtureId',
    'fixtureType',
    'status',
    'teamScoreHome',
    'teamScoreAway',
    'Home Team',
    'Away Team',
    'Venue',
)


def _text(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in ('none', 'nan'):
        return ''
    return text


def _team_name(competitor):
    if not isinstance(competitor, dict):
        return TEAM_TBD
    return _text(competitor.get('nameFullLocal')) or TEAM_TBD


def _score(competitor):
    if not isinstance(competitor, dict):
        return None
    score = competitor.get('score')
    if score is None:
        return None
    if _text(score) == '':
        return None
    return score


def _sides(competitors):
    home = None
    away = None
    if not isinstance(competitors, list):
        return home, away
    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        is_home = competitor.get('isHome')
        if is_home is True and home is None:
            home = competitor
        elif is_home is False and away is None:
            away = competitor
    return home, away


def _venue(match):
    venue = match.get('venue') if isinstance(match, dict) else None
    if not isinstance(venue, dict):
        return ''
    return _text(venue.get('nameLocal'))


def matches_to_frame(matches):
    if not isinstance(matches, list):
        raise ValueError('EASL matches response must be a list')
    rows = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        home, away = _sides(match.get('competitors'))
        fixture_type = _text(match.get('fixtureType')) or None
        rows.append({
            'startTimeLocal': _text(match.get('startTimeLocal')),
            'fixtureId': _text(match.get('fixtureId')),
            'fixtureType': fixture_type,
            'status': _text(match.get('status')),
            'teamScoreHome': _score(home),
            'teamScoreAway': _score(away),
            'Home Team': _team_name(home),
            'Away Team': _team_name(away),
            'Venue': _venue(match),
        })
    return pd.DataFrame(rows, columns=list(SCHEDULE_COLUMNS))


class Parser:
    @staticmethod
    def parse_season_game_list_df(season_id):
        return matches_to_frame(Communicator.get_season_matches(season_id))
