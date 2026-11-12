# -*- coding: utf-8 -*-
"""Season lineup and 5v5 matchup totals. No HTTP and no Dash."""
from itertools import combinations

from domain.clocks import minutes_to_mmss
from domain.rates import lineup_ppp_display, shot_pct_display

COUNT_KEYS = (
    'POSS', '2M', '2A', '3M', '3A', '1M', '1A',
    'OR', 'DR', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'FD',
    'PTS', 'PIP', 'SCP', 'FBP', 'POT',
)

_DISPLAY = (
    ('2M', '2M'), ('2A', '2A'), ('3M', '3M'), ('3A', '3A'),
    ('1M', 'FTM'), ('1A', 'FTA'),
    ('OR', 'OR'), ('DR', 'DR'), ('REB', 'REB'),
    ('AST', 'AST'), ('TOV', 'TO'), ('STL', 'ST'), ('BLK', 'BS'),
    ('PF', 'PF'), ('FD', 'FD'), ('PTS', 'PTS'),
    ('PIP', 'PIP'), ('SCP', 'SCP'), ('FBP', 'FBP'), ('POT', 'POT'),
)


def empty_side():
    return {key: 0 for key in COUNT_KEYS}


def _whole(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    if number < 0:
        return 0
    return number


def _seconds(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number < 0:
        return 0.0
    return number


def _blank(value):
    number = _whole(value)
    if number == 0:
        return ''
    return number


def _ppp_rank(value):
    if value in ('', None):
        return float('-inf')
    try:
        return float(value)
    except (TypeError, ValueError):
        return float('-inf')


def add_sides(left, right):
    return {
        key: _whole(left.get(key)) + _whole(right.get(key))
        for key in COUNT_KEYS
    }


def _fresh(ids):
    return {
        'ids': tuple(ids),
        'duration': 0.0,
        'own': empty_side(),
        'opp': empty_side(),
    }


def add_buckets(groups):
    """Sum five-man buckets. A non-positive total is dropped."""
    summed = {}
    for group in groups or ():
        if not group:
            continue
        for key, bucket in group.items():
            seconds = _seconds(bucket.get('duration'))
            if seconds <= 0:
                continue
            ids = tuple(bucket.get('ids') or key)
            dest = summed.get(ids)
            if dest is None:
                dest = _fresh(ids)
                summed[ids] = dest
            dest['duration'] += seconds
            dest['own'] = add_sides(dest['own'], bucket.get('own') or {})
            dest['opp'] = add_sides(dest['opp'], bucket.get('opp') or {})
    return {key: bucket for key, bucket in summed.items() if bucket['duration'] > 0}


def expand_subsets(fives, size):
    """Size 5 keeps the fives. A smaller size inherits each five's totals."""
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 5
    kept = add_buckets([fives or {}])
    if size >= 5:
        return kept
    if size < 2:
        size = 2
    expanded = {}
    for bucket in kept.values():
        ids = tuple(bucket['ids'])
        if len(ids) < size:
            continue
        for combo in combinations(ids, size):
            key = tuple(sorted(combo))
            dest = expanded.get(key)
            if dest is None:
                dest = _fresh(key)
                expanded[key] = dest
            dest['duration'] += bucket['duration']
            dest['own'] = add_sides(dest['own'], bucket['own'])
            dest['opp'] = add_sides(dest['opp'], bucket['opp'])
    return {key: bucket for key, bucket in expanded.items() if bucket['duration'] > 0}


def _visible(stats):
    shown = {}
    for source, dest in _DISPLAY:
        shown[dest] = _blank(stats.get(source))
    shown['2FG%'] = shot_pct_display(stats.get('2M'), stats.get('2A'))
    shown['3FG%'] = shot_pct_display(stats.get('3M'), stats.get('3A'))
    shown['FT%'] = shot_pct_display(stats.get('1M'), stats.get('1A'))
    shown['PPP'] = lineup_ppp_display(stats.get('PTS'), stats.get('POSS'))
    return shown


def _lineup_key(ids):
    return '|'.join(str(pid) for pid in ids)


def lineup_records(buckets, label_for):
    """Own row, then an Opp row. Order is +/- , PPP, minutes, name."""
    ranked = []
    for bucket in (buckets or {}).values():
        ids = tuple(bucket.get('ids') or ())
        own_stats = bucket.get('own') or empty_side()
        opp_stats = bucket.get('opp') or empty_side()
        name = label_for(ids) if label_for else _lineup_key(ids)
        plus = _whole(own_stats.get('PTS')) - _whole(opp_stats.get('PTS'))
        own = _visible(own_stats)
        own['Lineup'] = name
        own['Min'] = minutes_to_mmss(bucket.get('duration'))
        own['+/-'] = plus
        opp = _visible(opp_stats)
        opp['Lineup'] = name
        opp['Min'] = ''
        opp['+/-'] = ''
        pair = _lineup_key(ids)
        own_row = dict(own)
        opp_row = dict(opp)
        own_row['_opp'] = False
        opp_row['_opp'] = True
        own_row['_pair'] = opp_row['_pair'] = pair
        own_row['_own'] = opp_row['_own'] = dict(own)
        ranked.append((
            plus,
            _ppp_rank(own.get('PPP')),
            _seconds(bucket.get('duration')),
            name,
            own_row,
            opp_row,
        ))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    records = []
    for _plus, _ppp, _seconds_n, _name, own_row, opp_row in ranked:
        records.append(own_row)
        records.append(opp_row)
    return records


def sum_matchups(pairs, team_id):
    """Orient every 5v5 pair so the selected team is the top five."""
    selected = str(team_id)
    summed = {}
    for pair in pairs or ():
        home_team = '' if pair.get('home_team') is None else str(pair.get('home_team'))
        away_team = '' if pair.get('away_team') is None else str(pair.get('away_team'))
        if selected == home_team:
            top_ids = tuple(pair.get('home') or ())
            other_ids = tuple(pair.get('away') or ())
            top_stats = pair.get('home_stats') or {}
            other_stats = pair.get('away_stats') or {}
            other_team = away_team
        elif selected == away_team:
            top_ids = tuple(pair.get('away') or ())
            other_ids = tuple(pair.get('home') or ())
            top_stats = pair.get('away_stats') or {}
            other_stats = pair.get('home_stats') or {}
            other_team = home_team
        else:
            continue
        if len(top_ids) != 5 or len(other_ids) != 5:
            continue
        seconds = _seconds(pair.get('duration'))
        if seconds <= 0:
            continue
        key = (top_ids, other_ids)
        dest = summed.get(key)
        if dest is None:
            dest = {
                'top': top_ids,
                'other': other_ids,
                'other_team': other_team,
                'duration': 0.0,
                'top_stats': empty_side(),
                'other_stats': empty_side(),
            }
            summed[key] = dest
        dest['duration'] += seconds
        dest['top_stats'] = add_sides(dest['top_stats'], top_stats)
        dest['other_stats'] = add_sides(dest['other_stats'], other_stats)
    return [bucket for bucket in summed.values() if bucket['duration'] > 0]


def matchup_records(pairs, team_id, label_for):
    """Both rows stay. The selected five is on top. The other five keeps its name."""
    ranked = []
    for bucket in sum_matchups(pairs, team_id):
        top_name = label_for(str(team_id), bucket['top'])
        other_name = label_for(bucket['other_team'], bucket['other'])
        plus = _whole(bucket['top_stats'].get('PTS')) - _whole(bucket['other_stats'].get('PTS'))
        top = _visible(bucket['top_stats'])
        top['Lineup'] = top_name
        top['Min'] = minutes_to_mmss(bucket['duration'])
        top['+/-'] = plus
        other = _visible(bucket['other_stats'])
        other['Lineup'] = other_name
        other['Min'] = ''
        other['+/-'] = ''
        pair = _lineup_key(bucket['top']) + '|' + _lineup_key(bucket['other'])
        both = '{0} {1}'.format(top_name, other_name).strip()
        top_row = dict(top)
        other_row = dict(other)
        top_row['_opp'] = False
        other_row['_opp'] = True
        top_row['_pair'] = other_row['_pair'] = pair
        top_row['_own'] = other_row['_own'] = dict(top)
        top_row['_filter'] = other_row['_filter'] = both
        ranked.append((
            plus,
            _ppp_rank(top.get('PPP')),
            _seconds(bucket['duration']),
            top_name,
            top_row,
            other_row,
        ))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    records = []
    for _plus, _ppp, _seconds_n, _name, top_row, other_row in ranked:
        records.append(top_row)
        records.append(other_row)
    return records
