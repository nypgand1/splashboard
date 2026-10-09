# -*- coding: utf-8 -*-
"""5v5 matchup pairs from play-by-play on-court lists."""
import pandas as pd

from synergy_inbounder.names import person_name
from synergy_inbounder.possessions import annotate_possessions
from synergy_inbounder.pre_processing_func import _option_on
from synergy_reporter.post_game_report import lineup_ppp_display, shot_pct_display

STAT_KEYS = (
    'POSS', '2M', '2A', '3M', '3A', '1M', '1A',
    'OR', 'DR', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'FD',
    'PTS', 'PIP', 'SCP', 'FBP', 'POT',
)

_COUNT_FIELDS = (
    ('2M', '2M'), ('2A', '2A'), ('3M', '3M'), ('3A', '3A'),
    ('1M', 'FTM'), ('1A', 'FTA'),
    ('OR', 'OR'), ('DR', 'DR'), ('REB', 'REB'),
    ('AST', 'AST'), ('TOV', 'TO'), ('STL', 'ST'), ('BLK', 'BL'),
    ('PF', 'PF'), ('FD', 'FD'), ('PTS', 'PTS'),
    ('PIP', 'PIP'), ('SCP', 'SCP'), ('FBP', 'FBP'), ('POT', 'POT'),
)

_POINT_FLAGS = (
    ('PIP', 'pointsInThePaint'),
    ('SCP', 'secondChance'),
    ('FBP', 'fastBreak'),
    ('POT', 'fromTurnover'),
)


def _missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _column_for(df, team_id):
    if _missing(team_id):
        return None
    if team_id in df.columns:
        return team_id
    text = str(team_id)
    if text in df.columns:
        return text
    for column in df.columns:
        if str(column) == text:
            return column
    return None


def _five(value):
    if _missing(value) or isinstance(value, str):
        return None
    try:
        ids = tuple(sorted(str(player_id) for player_id in value))
    except TypeError:
        return None
    if len(ids) != 5:
        return None
    return ids


def _made(success):
    return success == 1 or success is True


def _flag_points(event, made, options, flag_name):
    if not made or not _option_on(options, flag_name):
        return 0
    if event == '2pt':
        return 2
    if event == '3pt':
        return 3
    if event == 'freeThrow':
        return 1
    return 0


def _empty_side():
    return {key: 0 for key in STAT_KEYS}


def _shirt(player_id, shirts):
    if player_id in shirts:
        return shirts[player_id]
    return shirts.get(str(player_id))


def _player_name(player_id, id_table):
    return person_name(id_table, player_id)


def _sort_key(player_id, shirts, id_table):
    bib = _shirt(player_id, shirts)
    if bib is not None:
        try:
            return (0, int(bib))
        except (TypeError, ValueError):
            pass
    return (1, _player_name(player_id, id_table))


def lineup_name(player_ids, shirts, id_table):
    ordered = sorted(player_ids, key=lambda player_id: _sort_key(player_id, shirts, id_table))
    return '-'.join(_player_name(player_id, id_table) for player_id in ordered)


def _add_event(side, row):
    if side is None:
        return
    event = row.get('eventType')
    subtype = row.get('subType')
    made = _made(row.get('success'))
    if event == '2pt':
        side['2A'] += 1
        if made:
            side['2M'] += 1
            side['PTS'] += 2
    elif event == '3pt':
        side['3A'] += 1
        if made:
            side['3M'] += 1
            side['PTS'] += 3
    elif event == 'freeThrow':
        side['1A'] += 1
        if made:
            side['1M'] += 1
            side['PTS'] += 1
    elif event == 'rebound':
        side['REB'] += 1
        if subtype == 'offensive':
            side['OR'] += 1
        elif subtype == 'defensive':
            side['DR'] += 1
    elif event == 'assist':
        side['AST'] += 1
    elif event == 'turnover':
        side['TOV'] += 1
    elif event == 'steal':
        side['STL'] += 1
    elif event == 'block':
        side['BLK'] += 1
    elif event == 'foul' and subtype == 'drawn':
        side['FD'] += 1
    elif event == 'foul':
        side['PF'] += 1
    options = row.get('options')
    for column, flag_name in _POINT_FLAGS:
        side[column] += _flag_points(event, made, options, flag_name)


def _durations(work):
    clocks = pd.to_datetime(work['clock'], format='PT%MM%SS')
    periods = work['periodId']
    same = (periods == periods.shift(-1)).fillna(False)
    delta = (clocks - clocks.shift(-1)).dt.total_seconds()
    seconds = [0.0] * len(work)
    for index, keep in enumerate(same.tolist()):
        if not keep:
            continue
        value = delta.iloc[index]
        if pd.notna(value):
            seconds[index] = float(value)
    return seconds


def build_matchup_payload(df, home_id, away_id, id_table=None, shirts=None):
    """Pairs whose two on-court lists are both length 5, summed for the game."""
    id_table = id_table or {}
    shirts = shirts or {}
    payload = {
        'home_id': None if _missing(home_id) else str(home_id),
        'away_id': None if _missing(away_id) else str(away_id),
        'pairs': [],
    }
    if df is None or len(df) == 0 or _missing(home_id) or _missing(away_id):
        return payload
    home_col = _column_for(df, home_id)
    away_col = _column_for(df, away_id)
    if home_col is None or away_col is None:
        return payload

    work = df.reset_index(drop=True)
    annotated = annotate_possessions(work)
    poss_end = [bool(value) for value in annotated['poss_end'].tolist()]
    poss_team = list(annotated['poss_team_id'])
    seconds = _durations(work)
    home_key = str(home_id)
    away_key = str(away_id)
    grouped = {}

    for index, row in enumerate(work.to_dict('records')):
        home_ids = _five(row.get(home_col))
        away_ids = _five(row.get(away_col))
        if home_ids is None or away_ids is None:
            continue
        key = (home_ids, away_ids)
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {'home': _empty_side(), 'away': _empty_side(), 'duration': 0.0}
            grouped[key] = bucket
        bucket['duration'] += seconds[index]
        entity = row.get('entityId')
        side = None
        if not _missing(entity):
            if str(entity) == home_key:
                side = bucket['home']
            elif str(entity) == away_key:
                side = bucket['away']
        _add_event(side, row)
        if poss_end[index] and not _missing(poss_team[index]):
            team = str(poss_team[index])
            if team == home_key:
                bucket['home']['POSS'] += 1
            elif team == away_key:
                bucket['away']['POSS'] += 1

    pairs = []
    for (home_ids, away_ids), bucket in grouped.items():
        if bucket['duration'] <= 0:
            continue
        pairs.append({
            'id': ','.join(home_ids) + '|' + ','.join(away_ids),
            'home_name': lineup_name(home_ids, shirts, id_table),
            'away_name': lineup_name(away_ids, shirts, id_table),
            'duration': bucket['duration'],
            'home': bucket['home'],
            'away': bucket['away'],
        })
    payload['pairs'] = pairs
    return payload


def _blank_count(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ''
    if number == 0:
        return ''
    return number


def _minutes(seconds):
    seconds = float(seconds or 0)
    return f"{int(seconds // 60)}:{seconds % 60:02.0f}"


def _side_visible(stats):
    stats = stats or {}
    visible = {}
    for source, dest in _COUNT_FIELDS:
        visible[dest] = _blank_count(stats.get(source, 0))
    visible['2FG%'] = shot_pct_display(stats.get('2M', 0), stats.get('2A', 0))
    visible['3FG%'] = shot_pct_display(stats.get('3M', 0), stats.get('3A', 0))
    visible['FT%'] = shot_pct_display(stats.get('1M', 0), stats.get('1A', 0))
    visible['PPP'] = lineup_ppp_display(stats.get('PTS', 0), stats.get('POSS', 0))
    return visible


def _pts(stats):
    try:
        return int((stats or {}).get('PTS') or 0)
    except (TypeError, ValueError):
        return 0


def _ppp_rank(value):
    """Blank PPP ranks below 0.00."""
    if value in ('', None):
        return float('-inf')
    try:
        if pd.isna(value):
            return float('-inf')
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return float('-inf')


def _duration_rank(value):
    try:
        if _missing(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def matchup_grid_records(payload, viewpoint_id=None):
    """Two rows per pair. The viewpoint five is the top row."""
    if not isinstance(payload, dict):
        return []
    home_id = '' if _missing(payload.get('home_id')) else str(payload.get('home_id'))
    away_id = '' if _missing(payload.get('away_id')) else str(payload.get('away_id'))
    view = away_id if _missing(viewpoint_id) else str(viewpoint_id)
    if view not in (home_id, away_id):
        view = away_id
    home_on_top = view == home_id and home_id != ''
    ordered = []
    for pair in payload.get('pairs') or []:
        if not isinstance(pair, dict):
            continue
        home_stats = pair.get('home') or {}
        away_stats = pair.get('away') or {}
        if home_on_top:
            top_name = pair.get('home_name') or ''
            other_name = pair.get('away_name') or ''
            top_stats = home_stats
            other_stats = away_stats
        else:
            top_name = pair.get('away_name') or ''
            other_name = pair.get('home_name') or ''
            top_stats = away_stats
            other_stats = home_stats
        plus_minus = _pts(top_stats) - _pts(other_stats)
        top_visible = _side_visible(top_stats)
        top_visible['Lineup'] = top_name
        top_visible['Min'] = _minutes(pair.get('duration'))
        top_visible['+/-'] = plus_minus
        other_visible = _side_visible(other_stats)
        other_visible['Lineup'] = other_name
        other_visible['Min'] = ''
        other_visible['+/-'] = ''
        pair_id = pair.get('id') or ''
        both_names = f"{pair.get('away_name') or ''} {pair.get('home_name') or ''}".strip()
        own = dict(top_visible)
        top = dict(top_visible)
        other = dict(other_visible)
        top['_opp'] = False
        other['_opp'] = True
        top['_pair'] = other['_pair'] = pair_id
        top['_own'] = other['_own'] = own
        top['_filter'] = other['_filter'] = both_names
        ordered.append((
            plus_minus,
            _ppp_rank(top_visible.get('PPP')),
            _duration_rank(pair.get('duration')),
            top_name,
            top,
            other,
        ))
    ordered.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    records = []
    for _plus, _ppp, _seconds, _name, top, other in ordered:
        records.append(top)
        records.append(other)
    return records
