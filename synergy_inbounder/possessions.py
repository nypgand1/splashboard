# -*- coding: utf-8 -*-
"""Stats possessions from a play-by-play frame, in the frame's own row order."""
import pandas as pd

_IGNORE = {
    'main', 'substitution', 'videoReview', 'timeOut', 'fixture',
    'possessionArrow', 'assist', 'block', 'possession', 'foul', 'steal',
}
_LAST_FT = {'1Of1', '2Of2', '3Of3'}
_NON_POSSESSION_FOUL = {'technical', 'unsportsmanlike'}


def _missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _made(value):
    return value == 1 or value is True


def annotate_possessions(df):
    """Mark each stats possession in ``df`` without sorting it.

    ``poss_end`` is true on the row that ends a trip which included a shot,
    free throw, or turnover. ``poss_team_id`` is the offense, including when
    the end row is the opponent's defensive rebound. API ``possession`` events
    are not ends. Technical and unsportsmanlike free throws do not end a trip.
    """
    columns = {
        'poss_end': pd.Series(dtype=bool),
        'poss_team_id': pd.Series(dtype=object),
        'poss_id': pd.Series(dtype=object),
    }
    if df is None or len(df) == 0 or 'eventType' not in getattr(df, 'columns', []):
        out = df.copy() if df is not None else pd.DataFrame()
        for name, empty in columns.items():
            out[name] = empty
        return out

    records = df.to_dict('records')
    poss_end = [False] * len(records)
    poss_team = [None] * len(records)
    poss_ids = [None] * len(records)
    teams = []
    open_team = None
    used = False
    trip_id = 0
    current_id = None
    non_poss_ft = False

    def remember(entity):
        if _missing(entity) or entity in teams:
            return
        teams.append(entity)

    def other(team):
        rest = [item for item in teams if item != team]
        if len(rest) == 1:
            return rest[0]
        return None

    def start(team):
        nonlocal open_team, used, trip_id, current_id
        trip_id += 1
        current_id = trip_id
        open_team = team
        used = False

    def close(index, team):
        nonlocal open_team, used, current_id
        if team is not None and used:
            poss_end[index] = True
            poss_team[index] = team
            poss_ids[index] = current_id
        open_team = None
        used = False
        current_id = None

    def ensure(team):
        nonlocal open_team
        if open_team is None:
            start(team)
            return
        if open_team != team:
            open_team = None
            start(team)

    def next_ball(index):
        cursor = index + 1
        while cursor < len(records):
            event_type = records[cursor].get('eventType')
            if event_type == 'period' and records[cursor].get('subType') in {'end', 'confirmed', 'pending'}:
                return records[cursor]
            if event_type not in _IGNORE and event_type != 'period':
                return records[cursor]
            cursor += 1
        return None

    for index, event in enumerate(records):
        event_type = event.get('eventType')
        sub_type = event.get('subType')
        entity = event.get('entityId')
        if event_type == 'foul' and sub_type in _NON_POSSESSION_FOUL:
            non_poss_ft = True
            continue
        if event_type == 'freeThrow' and non_poss_ft:
            if sub_type in _LAST_FT:
                non_poss_ft = False
            continue
        if event_type == 'period' and sub_type == 'end':
            if open_team is not None:
                poss_ids[index] = current_id
                poss_team[index] = open_team
            close(index, open_team)
            non_poss_ft = False
            continue
        if event_type in _IGNORE or event_type == 'period' or _missing(entity):
            continue
        non_poss_ft = False
        remember(entity)
        if current_id is not None and open_team is not None:
            poss_ids[index] = current_id
            poss_team[index] = open_team

        if event_type == 'jumpBall':
            if sub_type == 'won':
                ensure(entity)
                poss_ids[index] = current_id
                poss_team[index] = open_team
            continue
        if event_type in ('2pt', '3pt'):
            ensure(entity)
            used = True
            poss_ids[index] = current_id
            poss_team[index] = open_team
            if _made(event.get('success')):
                nxt = next_ball(index)
                and_one = (
                    nxt is not None
                    and nxt.get('eventType') == 'freeThrow'
                    and nxt.get('entityId') == entity
                )
                if not and_one:
                    close(index, entity)
            continue
        if event_type == 'freeThrow':
            ensure(entity)
            used = True
            poss_ids[index] = current_id
            poss_team[index] = open_team
            if sub_type in _LAST_FT and _made(event.get('success')):
                close(index, entity)
            continue
        if event_type == 'rebound' and sub_type == 'offensive':
            ensure(entity)
            poss_ids[index] = current_id
            poss_team[index] = open_team
            continue
        if event_type == 'rebound' and sub_type == 'defensive':
            if open_team is not None and open_team != entity:
                close(index, open_team)
                start(entity)
                if not poss_end[index]:
                    poss_ids[index] = current_id
                    poss_team[index] = open_team
            elif open_team is None:
                start(entity)
                poss_ids[index] = current_id
                poss_team[index] = open_team
            continue
        if event_type == 'turnover':
            ensure(entity)
            used = True
            poss_ids[index] = current_id
            poss_team[index] = open_team
            close(index, entity)
            nxt_team = other(entity)
            if nxt_team is not None:
                start(nxt_team)
            continue

    out = df.copy()
    out['poss_end'] = poss_end
    out['poss_team_id'] = poss_team
    out['poss_id'] = poss_ids
    return out


def _period_id(value):
    if _missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def possession_counts(df, period_ids=None):
    """Map offense entity id to the number of ended possessions."""
    if df is None or len(df) == 0:
        return {}
    annotated = df if 'poss_end' in df.columns else annotate_possessions(df)
    ended = annotated[annotated['poss_end'] == True]  # noqa: E712
    if period_ids is not None:
        wanted = {int(period) for period in period_ids}
        ended = ended[ended['periodId'].map(_period_id).isin(wanted)]
    counts = {}
    for team, size in ended.groupby('poss_team_id').size().items():
        if _missing(team):
            continue
        counts[team] = int(size)
    return counts
