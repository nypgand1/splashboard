"""Away-then-home order for team rows and stacked team sections."""

import json

HOME_DOT = '#00b4d8'
AWAY_DOT = '#94a3b8'
HOME_STRIPE = '#0077b6'
AWAY_STRIPE = '#94a3b8'


def side_names(match_info):
    """Display names for the fixture's away team and home team."""
    info = match_info
    if isinstance(match_info, str):
        try:
            info = json.loads(match_info) if match_info.strip() else {}
        except Exception:
            info = {}
    if not isinstance(info, dict):
        info = {}
    away = info.get('away_team') or ''
    home = info.get('home_team') or ''
    return (str(away) if away else '', str(home) if home else '')


def names_known(away_name, home_name):
    return bool(away_name) and bool(home_name) and away_name != home_name


def _ranked(name, away_name, home_name):
    if name == away_name:
        return 0
    if name == home_name:
        return 1
    return 2


def order_named_items(items, away_name, home_name):
    """Away, then home, then any other name in its previous order.

    Without two distinct side names, keep the team-name sort.
    """
    pairs = list(items)
    if not names_known(away_name, home_name):
        return sorted(pairs, key=lambda item: str(item[0]))
    return sorted(pairs, key=lambda item: _ranked(item[0], away_name, home_name))


def order_team_frame(df, away_name, home_name):
    """Put the away row above the home row. Leave other rows after them."""
    if df is None or getattr(df, 'empty', True) or 'Team' not in getattr(df, 'columns', []):
        return df
    if not names_known(away_name, home_name):
        return df.sort_values(by=['Team'], kind='mergesort').reset_index(drop=True)
    rank = df['Team'].map(lambda name: _ranked(name, away_name, home_name))
    ordered = df.assign(_side_rank=rank).sort_values('_side_rank', kind='mergesort')
    return ordered.drop(columns='_side_rank').reset_index(drop=True)


def order_team_split_json(payload, away_name, home_name):
    """Reorder a split-orient team table. Return the original text when it already matches."""
    if not isinstance(payload, str) or not payload.strip():
        return payload
    if not names_known(away_name, home_name):
        return payload
    try:
        parsed = json.loads(payload)
    except Exception:
        return payload
    columns = parsed.get('columns') if isinstance(parsed, dict) else None
    data = parsed.get('data') if isinstance(parsed, dict) else None
    if not isinstance(columns, list) or 'Team' not in columns or not isinstance(data, list):
        return payload
    index = columns.index('Team')
    decorated = []
    for pos, row in enumerate(data):
        name = row[index] if isinstance(row, (list, tuple)) and len(row) > index else None
        decorated.append((_ranked(name, away_name, home_name), pos, row))
    decorated.sort()
    new_data = [row for _, _, row in decorated]
    if new_data == data:
        return payload
    parsed['data'] = new_data
    return json.dumps(parsed, ensure_ascii=False)


def section_dot(name, away_name, home_name, index):
    """Cyan stays on the home team. Gray stays on the away team."""
    if names_known(away_name, home_name):
        if name == away_name:
            return AWAY_DOT
        if name == home_name:
            return HOME_DOT
    return HOME_DOT if index == 0 else AWAY_DOT


def team_stripe(name, away_name, home_name, row_idx):
    """Home stripe is blue. Away stripe is gray. Index is only a fallback."""
    if names_known(away_name, home_name):
        if name == home_name:
            return HOME_STRIPE
        if name == away_name:
            return AWAY_STRIPE
    return HOME_STRIPE if row_idx == 0 else AWAY_STRIPE
