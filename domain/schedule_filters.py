# -*- coding: utf-8 -*-
"""Shared schedule, league, season, and game-type option helpers."""
from synergy_inbounder.settings import (
    EASL_SEASON_ID,
    EASL_SEASONS,
    SYNERGY_SEASON_ID,
    SYNERGY_SEASONS,
    selectable_seasons,
)

LEAGUE_PLG = 'PLG'
LEAGUE_EASL = 'EASL'
LEAGUE_OPTIONS = [
    {'label': LEAGUE_PLG, 'value': LEAGUE_PLG},
    {'label': LEAGUE_EASL, 'value': LEAGUE_EASL},
]


def default_season_id(league):
    """Default season ID for ``league`` (PLG or EASL)."""
    if str(league or '').strip().upper() == LEAGUE_EASL:
        return EASL_SEASON_ID
    return SYNERGY_SEASON_ID


def seasons_for(league):
    """Raw season table for ``league``."""
    if str(league or '').strip().upper() == LEAGUE_EASL:
        return EASL_SEASONS
    return SYNERGY_SEASONS


def selectable_season_options(league):
    """Dash Select ``data`` list for seasons that have regulation minutes."""
    return [
        {'label': label, 'value': season_id}
        for label, season_id in selectable_seasons(league)
    ]


def plain_fixture_type(value):
    """Real fixtureType string, or '' for blanks, non-strings, and pandas missing values."""
    if not isinstance(value, str):
        return ''
    text = value.strip()
    if text.lower() in ('nan', 'none', 'null', '<na>'):
        return ''
    return text


def fixture_type_options(records, key_fn=None):
    """Distinct non-empty fixtureType values in schedule order.

    ``key_fn(record)`` extracts the raw fixtureType when records use a fallback
    column name (such as Home's ``Game Type`` fallback); defaults to ``record.get('fixtureType')``.
    """
    options = []
    seen = set()
    for record in records or []:
        if not isinstance(record, dict):
            continue
        raw = key_fn(record) if key_fn is not None else record.get('fixtureType')
        value = plain_fixture_type(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        options.append({'label': value.title(), 'value': value})
    return options


def choose_game_type(options, requested):
    """Keep ``requested`` if present, else pick ``Regular``, else first option."""
    values = [item['value'] for item in options]
    if requested in values:
        return requested
    for item in options:
        if str(item['value']).title() == 'Regular':
            return item['value']
    return values[0] if values else None
