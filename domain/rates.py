# -*- coding: utf-8 -*-
"""Basketball counting sums, shooting percentages, efficiency rates, and PBP flag splits."""
import pandas as pd

from domain.periods import filter_periods
from synergy_inbounder.pre_processing_func import _flag_from_parsed, _parsed_option

TEAM_COUNT_FIELDS = (
    'points', 'pointsAgainst', 'plusMinus',
    'pointsTwoMade', 'pointsTwoAttempted',
    'pointsThreeMade', 'pointsThreeAttempted',
    'freeThrowsMade', 'freeThrowsAttempted',
    'reboundsOffensive', 'reboundsDefensive', 'rebounds', 'reboundsDefensiveAgainst',
    'assists', 'turnovers', 'steals', 'blocks',
    'foulsTotal', 'foulsDrawn',
    'pointsInThePaintMade', 'pointsInThePaintAttempted', 'pointsInThePaint',
    'pointsSecondChanceMade', 'pointsSecondChanceAttempted', 'pointsSecondChance',
    'pointsFastBreak', 'pointsFromTurnover', 'pointsFromBench',
    'fieldGoalsMade', 'fieldGoalsAttempted',
    'reboundsTeamOffensive', 'reboundsTeamDefensive', 'reboundsTeamTotal',
    'turnoversTeam',
    'foulsCoachTechnical', 'foulsBenchTechnical', 'foulsCoachDisqualifying',
)

PLAYER_COUNT_FIELDS = (
    'plusMinus', 'plus', 'minus',
    'pointsTwoMade', 'pointsTwoAttempted',
    'pointsThreeMade', 'pointsThreeAttempted',
    'freeThrowsMade', 'freeThrowsAttempted',
    'reboundsOffensive', 'reboundsDefensive', 'rebounds',
    'assists', 'turnovers', 'steals', 'blocks',
    'foulsTotal', 'foulsDrawn', 'points',
)

RATE_FIELDS = (
    'pointsTwoPercentage', 'pointsThreePercentage', 'freeThrowsPercentage',
    'fieldGoalsEffectivePercentage',
)

FLAG_SPLITS = (
    ('SCP', 'secondChance', 'pointsSecondChance'),
    ('FBP', 'fastBreak', 'pointsFastBreak'),
    ('POT', 'fromTurnover', 'pointsFromTurnover'),
)
SPLIT_LEAVES = ('2M', '2A', '3M', '3A')


def as_nonneg_int(value):
    if value is None or value == '':
        return 0
    if isinstance(value, str) and not str(value).strip():
        return 0
    if isinstance(value, float) and pd.isna(value):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def num(value):
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def three_decimal_rate(rate):
    text = f'{float(rate):.3f}'
    if text.startswith('0'):
        return text[1:]
    return text


def shot_pct_display(made, attempted, pct=None):
    """Blank when A==0; .000 when A>0 and M==0. Three decimals, no leading zero."""
    attempted_n = as_nonneg_int(attempted)
    if attempted_n <= 0:
        return ''
    if as_nonneg_int(made) == 0:
        return '.000'
    if pct is not None and pd.notnull(pct):
        rate = float(pct) / 100.0
    else:
        rate = as_nonneg_int(made) / attempted_n
    return three_decimal_rate(rate)


def lineup_ppp_display(points, possessions):
    """Blank when POSS is 0. Two decimals, including 0.00."""
    poss_n = as_nonneg_int(possessions)
    if poss_n <= 0:
        return ''
    return f'{as_nonneg_int(points) / poss_n:.2f}'


def efg_pct_display(made2, attempted2, made3, attempted3, efg_val=None):
    """Blank when FGA==0; 0.0% when FGA>0 and (2M+3M)==0."""
    fga = as_nonneg_int(attempted2) + as_nonneg_int(attempted3)
    if fga <= 0:
        return ''
    made = as_nonneg_int(made2) + as_nonneg_int(made3)
    if made == 0:
        return '0.0%'
    if efg_val is not None and pd.notnull(efg_val):
        return f'{float(efg_val):0.1f}%'
    made3_n = as_nonneg_int(made3)
    return f'{100.0 * (made + 0.5 * made3_n) / fga:0.1f}%'


def rate_text(numer, denom, digits, scale=1, suffix=''):
    if pd.isnull(numer) or pd.isnull(denom) or denom == 0:
        return ''
    return f'{(scale * float(numer) / float(denom)):.{digits}f}{suffix}'


def true_shooting(points, fga, fta):
    """TS% = 100 * PTS / (2 * (FGA + 0.44 * FTA)). Blank when denominator is 0."""
    if pd.isnull(points) or pd.isnull(fga) or pd.isnull(fta):
        return ''
    denom = float(fga) + 0.44 * float(fta)
    if denom == 0:
        return ''
    return f'{100.0 * float(points) / (2.0 * denom):0.1f}%'


def sum_fields(rows, fields):
    summed = {}
    for field in fields:
        if field in rows.columns:
            summed[field] = float(pd.to_numeric(rows[field], errors='coerce').fillna(0).sum())
        else:
            summed[field] = 0
    return summed


def recompute_rates(row):
    two_m = num(row.get('pointsTwoMade'))
    two_a = num(row.get('pointsTwoAttempted'))
    three_m = num(row.get('pointsThreeMade'))
    three_a = num(row.get('pointsThreeAttempted'))
    ft_m = num(row.get('freeThrowsMade'))
    ft_a = num(row.get('freeThrowsAttempted'))
    fga = two_a + three_a
    row['fieldGoalsAttempted'] = fga
    row['fieldGoalsMade'] = two_m + three_m
    row['pointsTwoPercentage'] = (100.0 * two_m / two_a) if two_a else None
    row['pointsThreePercentage'] = (100.0 * three_m / three_a) if three_a else None
    row['freeThrowsPercentage'] = (100.0 * ft_m / ft_a) if ft_a else None
    row['fieldGoalsEffectivePercentage'] = (
        (100.0 * (two_m + 1.5 * three_m) / fga) if fga else None
    )
    row['usageRate'] = None
    return row


def shot_made(value):
    if value is True or value == 1:
        return True
    try:
        if pd.isna(value):
            return False
    except TypeError:
        return False
    try:
        return float(value) == 1.0
    except (TypeError, ValueError):
        return False


def flag_split_counts(pbp, entity_ids, period_ids):
    """2M/2A/3M/3A for SCP, FBP, and POT. Blank strings when play-by-play is missing."""
    keys = [prefix + leaf for prefix, _flag, _points in FLAG_SPLITS for leaf in SPLIT_LEAVES]
    entities = list(entity_ids)
    missing = pbp is None or len(pbp) == 0 or 'entityId' not in getattr(pbp, 'columns', [])
    if missing:
        return {entity: {key: '' for key in keys} for entity in entities}
    frame = pbp if period_ids is None else filter_periods(pbp, period_ids)
    counts = {entity: {key: 0 for key in keys} for entity in entities}
    if frame is None or len(frame) == 0:
        return counts
    events = frame['eventType'].tolist() if 'eventType' in frame.columns else [None] * len(frame)
    teams = frame['entityId'].tolist()
    successes = frame['success'].tolist() if 'success' in frame.columns else [None] * len(frame)
    options = frame['options'].tolist() if 'options' in frame.columns else [None] * len(frame)
    for entity, event, success, raw_options in zip(teams, events, successes, options):
        if entity not in counts or event not in ('2pt', '3pt'):
            continue
        parsed = _parsed_option(raw_options)
        if not parsed:
            continue
        kind = '2' if event == '2pt' else '3'
        made = shot_made(success)
        bucket = counts[entity]
        for prefix, flag, _points in FLAG_SPLITS:
            if not _flag_from_parsed(parsed, flag):
                continue
            bucket[f'{prefix}{kind}A'] += 1
            if made:
                bucket[f'{prefix}{kind}M'] += 1
    return counts
