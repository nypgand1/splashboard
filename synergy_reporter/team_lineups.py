# -*- coding: utf-8 -*-
"""Season lineup and matchup rows from play-by-play already on the fixture."""
import pandas as pd

from domain.lineups import add_buckets, expand_subsets, lineup_records, matchup_records
from inbound.cache.frame_store import (
    get_fixture_facts,
    get_lineup_summary,
    get_rotation_summary,
    get_team_shirts,
    set_lineup_summary,
)
from synergy_inbounder.logs import data as log_data
from synergy_inbounder.names import shared_short_labels
from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats
from synergy_reporter.matchups import build_matchup_payload, lineup_name
from synergy_reporter.team_rotation import infer_opening_five, load_fixture_facts

_COUNT_KEYS = (
    'POSS', '2M', '2A', '3M', '3A', '1M', '1A',
    'OR', 'DR', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'FD',
    'PTS', 'PIP', 'SCP', 'FBP', 'POT',
)

EMPTY_LINEUPS = 'No lineups for this view.'
EMPTY_MATCHUPS = 'No 5-player matchups for this view.'


def _whole(value):
    try:
        if value is None or pd.isna(value):
            return 0
    except TypeError:
        if value is None:
            return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _seconds(value):
    try:
        if value is None or pd.isna(value):
            return 0.0
    except TypeError:
        if value is None:
            return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number <= 0:
        return 0.0
    return number


def _five(players):
    if not isinstance(players, (list, tuple)) or isinstance(players, str):
        return None
    try:
        ids = tuple(sorted(str(player) for player in players))
    except TypeError:
        return None
    if len(ids) != 5 or len(set(ids)) != 5:
        return None
    return ids


def _side(row, prefix):
    return {key: _whole(row.get(prefix + key)) for key in _COUNT_KEYS}


def _starters_for(org_id, game):
    home = game.get('home')
    away = game.get('away')
    pbp = game.get('pbp')
    if not home or not away or pbp is None:
        return None
    summary = get_rotation_summary(org_id, game.get('fixture_id'), id(pbp)) or {}
    seeded = dict(summary.get('starters') or {})
    for team in (home, away):
        if seeded.get(team):
            continue
        opening = infer_opening_five(pbp, team)
        if opening:
            seeded[team] = opening
    if seeded.get(home) and seeded.get(away):
        return seeded
    official = Parser.starter_dict_from_rows(
        get_fixture_facts(org_id, game.get('fixture_id')),
    )
    by_text = {str(key): value for key, value in official.items()}
    for team in (home, away):
        if seeded.get(team):
            continue
        found = official.get(team) or by_text.get(str(team))
        if found:
            seeded[team] = found
    if not seeded.get(home) or not seeded.get(away):
        return None
    return seeded


def _align_starters(frame, starters):
    """Use the play-by-play entityId object as the lineup column name."""
    found = {}
    if 'entityId' in frame.columns:
        for value in frame['entityId'].dropna().unique():
            found.setdefault(str(value), value)
    aligned = {}
    for key, people in (starters or {}).items():
        aligned[found.get(str(key), key)] = list(people or [])
    return aligned


def _walk_game(game, starters):
    frame = game.get('pbp')
    if frame is None or getattr(frame, 'empty', True):
        return None
    home = game.get('home')
    away = game.get('away')
    walked = frame.copy()
    process_lineup_pbp(walked, _align_starters(walked, starters))
    payload = build_matchup_payload(walked, home, away)
    stats = process_lineup_stats(walked)
    fives = {}
    for team, table in (stats or {}).items():
        if table is None or getattr(table, 'empty', True) or team not in table.columns:
            continue
        team_key = str(team)
        grouped = {}
        for row in table.to_dict('records'):
            ids = _five(row.get(team))
            seconds = _seconds(row.get('duration'))
            if ids is None or seconds <= 0:
                continue
            grouped[ids] = {
                'ids': ids,
                'duration': seconds,
                'own': _side(row, ''),
                'opp': _side(row, 'Opp_'),
            }
        if grouped:
            fives[team_key] = grouped
    pairs = []
    for pair in payload.get('pairs') or []:
        text = str(pair.get('id') or '')
        if '|' not in text:
            continue
        home_text, away_text = text.split('|', 1)
        home_ids = tuple(part for part in home_text.split(',') if part)
        away_ids = tuple(part for part in away_text.split(',') if part)
        seconds = _seconds(pair.get('duration'))
        if len(home_ids) != 5 or len(away_ids) != 5 or seconds <= 0:
            continue
        pairs.append({
            'home_team': str(home),
            'away_team': str(away),
            'home': home_ids,
            'away': away_ids,
            'duration': seconds,
            'home_stats': dict(pair.get('home') or {}),
            'away_stats': dict(pair.get('away') or {}),
        })
    return {'fives': fives, 'pairs': pairs}


def summary_for(org_id, game):
    """Compact fives and 5v5 pairs for one fixture. Reuses a warm summary."""
    pbp = game.get('pbp')
    if pbp is None or getattr(pbp, 'empty', True):
        return None
    fixture_id = game.get('fixture_id')
    cached = get_lineup_summary(org_id, fixture_id, id(pbp))
    if cached is not None:
        return cached
    starters = _starters_for(org_id, game)
    if not starters:
        return None
    try:
        built = _walk_game(game, starters)
    except Exception as exc:
        log_data.debug('season lineup walk failed fixture=%s: %s', fixture_id, exc)
        return None
    if built is None:
        return None
    set_lineup_summary(org_id, fixture_id, id(pbp), built)
    return built


def _prepare(source):
    load_fixture_facts(source)
    org_id = source.get('org_id')
    prepared = []
    for game in source.get('games') or []:
        summary = summary_for(org_id, game)
        if summary is None:
            continue
        prepared.append(summary)
    return prepared


def _pool(source, team_id, extra_ids):
    people = list(extra_ids or ())
    org_id = source.get('org_id')
    for game in source.get('games') or []:
        for row in get_fixture_facts(org_id, game.get('fixture_id')) or []:
            if str(row.get('entityId')) != str(team_id):
                continue
            person = row.get('personId')
            if person:
                people.append(person)
    return people


def _remember(pools, source, team_id, ids):
    key = str(team_id)
    current = pools.get(key)
    if current is None:
        pools[key] = _pool(source, key, ids)
        return
    current.extend(ids)


def _label(source, team_id, ids, pools):
    key = str(team_id)
    pool = pools.get(key) or []
    shirts = get_team_shirts(key)
    names = source.get('id_table') or {}
    return lineup_name(ids, shirts, names, pool)


def season_lineup_records(source, size):
    """Selected team's lineups. Sizes 4, 3, and 2 expand the summed fives."""
    team = str(source.get('team'))
    groups = []
    pools = {}
    for summary in _prepare(source):
        grouped = (summary.get('fives') or {}).get(team) or {}
        groups.append(grouped)
        for ids in grouped:
            _remember(pools, source, team, ids)
    if team not in pools:
        pools[team] = _pool(source, team, ())
    buckets = expand_subsets(add_buckets(groups), size)

    def label_for(ids):
        return _label(source, team, ids, pools)

    return lineup_records(buckets, label_for)


def season_matchup_records(source):
    """5v5 pairs with the selected team on top."""
    team = str(source.get('team'))
    pairs = []
    pools = {}
    for summary in _prepare(source):
        for pair in summary.get('pairs') or []:
            pairs.append(pair)
            _remember(pools, source, pair.get('home_team'), pair.get('home'))
            _remember(pools, source, pair.get('away_team'), pair.get('away'))

    def label_for(team_id, ids):
        _remember(pools, source, team_id, ids)
        return _label(source, team_id, ids, pools)

    return matchup_records(pairs, team, label_for)
