# -*- coding: utf-8 -*-
"""Season team cards for one league, season, and game type.

Counting columns are sums divided by GP. Shot percentages and the efficiency
cards sum the inputs first, then use the same formulas as one Box Score half.
"""
import threading
import time

import pandas as pd

from synergy_inbounder.communicator import SynergyAuthError, _cache_hits
from synergy_inbounder.logs import auth as log_auth
from synergy_inbounder.logs import unexpected as log_unexpected
from synergy_inbounder.game_status import is_finished_status
from synergy_inbounder.http_wave import run_wave
from synergy_inbounder.live_budget import SHORT_CACHE_SECONDS
from synergy_inbounder.names import TEAM_TBD, display_name
from synergy_reporter.column_winners import winning_indexes
from synergy_inbounder.parser import Parser
from synergy_inbounder.possessions import possession_counts
from synergy_inbounder.runtime_cache import peek_finished_report, taipei_now_label
from synergy_inbounder.settings import (
    organization_for_league,
    regulation_minutes,
    selectable_seasons,
)
from synergy_inbounder import frame_store
from synergy_reporter.post_game_report import (
    PostGameReport,
    _SPLIT_LEAVES,
    _TEAM_COUNT_FIELDS,
    _chip_spec,
    _filter_periods,
    _flag_split_counts,
    _num,
    _recompute_rates,
    _sum_clocks,
    _sum_fields,
    minutes_to_mmss,
    shot_pct_display,
)
from synergy_reporter.rotation import clock_to_seconds, period_label
from ui_kit import ERROR_GAME

EMPTY_TEAM_STATS = 'No games in this view.'
EMPTY_TEAM_STATS_NEXT = 'Switch Game Type, Team, Opponent, Stadium, or Home/Away.'
TEAM_ALL = 'all'
TEAM_ALL_LABEL = 'All Teams'
OPPONENT_ALL = 'all'
OPPONENT_ALL_LABEL = 'vs All Teams'
STADIUM_ALL = 'all'
STADIUM_ALL_LABEL = 'All Stadiums'
SITE_ALL = 'all'
SITE_OPTIONS = (
    {'label': 'All', 'value': 'all'},
    {'label': 'Away', 'value': 'away'},
    {'label': 'Home', 'value': 'home'},
)
PACE_CARD_TITLE = 'Pace & Four Factors'
ADVANCED_CARD_TITLE = 'ADVANCED'
KEY_CARD_TITLE = 'Paint / 2nd Chance / Fastbreak / Off TO / Bench'

_LOWER_IS_BETTER = frozenset({'TO', 'PF', 'TO%'})
_UNCOLORED = frozenset({'Team', 'GP', 'Min', '3P-R'})
_REGULATION_PERIODS = frozenset({'all', '1', '2', '3', '4', 'h1', 'h2'})

_TEAM_COLUMNS = (
    'Team', 'GP', 'Min',
    '2M', '2A', '2FG%', '3M', '3A', '3FG%',
    'FTM', 'FTA', 'FT%',
    'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS',
)
_KEY_COLUMNS = (
    'Team', 'GP',
    'PIPM', 'PIPA', 'PIP',
    'SCP2M', 'SCP2A', 'SCP3M', 'SCP3A', 'SCP',
    'FBP2M', 'FBP2A', 'FBP3M', 'FBP3A', 'FBP',
    'POT2M', 'POT2A', 'POT3M', 'POT3A', 'POT',
    'BP',
)
_PACE_COLUMNS = ('Team', 'GP', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R')
_ADVANCED_COLUMNS = ('Team', 'GP', 'PPP', 'AS/TO', 'AST%', '3P-R', 'TS%')
_KEY_API = (
    ('PIPM', 'pointsInThePaintMade'),
    ('PIPA', 'pointsInThePaintAttempted'),
    ('PIP', 'pointsInThePaint'),
    ('SCP', 'pointsSecondChance'),
    ('FBP', 'pointsFastBreak'),
    ('POT', 'pointsFromTurnover'),
    ('BP', 'pointsFromBench'),
)
_LEAF_KEYS = tuple(
    prefix + leaf
    for prefix in ('SCP', 'FBP', 'POT')
    for leaf in _SPLIT_LEAVES
)

_bundle_lock = threading.Lock()
_bundles = {}


def clear_team_stats_cache():
    with _bundle_lock:
        _bundles.clear()


def plain_fixture_type(value):
    """Real fixtureType string, or '' for blanks, non-strings, and pandas missing values.

    ``float('nan')`` is truthy, so ``value or ''`` keeps it and ``str(nan).title()``
    becomes the option ``Nan``. SegmentedControl then receives JSON null.
    """
    if not isinstance(value, str):
        return ''
    text = value.strip()
    if text.lower() in ('nan', 'none', 'null', '<na>'):
        return ''
    return text


def fixture_type_options(records):
    """Distinct non-empty fixtureType values in schedule order."""
    options = []
    seen = set()
    for record in records or []:
        if not isinstance(record, dict):
            continue
        value = plain_fixture_type(record.get('fixtureType'))
        if not value or value in seen:
            continue
        seen.add(value)
        options.append({'label': value.title(), 'value': value})
    return options


def choose_game_type(options, requested):
    values = [item['value'] for item in options]
    if requested in values:
        return requested
    for item in options:
        if str(item['value']).title() == 'Regular':
            return item['value']
    return values[0] if values else None


def period_chips_for_ids(period_ids):
    """Quarter, half, and overtime chips from team period ids. No person gate."""
    found = set()
    for value in period_ids or []:
        try:
            found.add(int(value))
        except (TypeError, ValueError):
            continue
    chips = [{'label': 'All', 'value': 'all'}]

    def add(period):
        if period in found:
            chips.append({'label': period_label(period), 'value': str(period)})

    add(1)
    add(2)
    if 1 in found and 2 in found:
        chips.append({'label': '1H', 'value': 'h1'})
    add(3)
    add(4)
    if 3 in found and 4 in found:
        chips.append({'label': '2H', 'value': 'h2'})
    for period in sorted(item for item in found if item not in (1, 2, 3, 4)):
        chips.append({'label': period_label(period), 'value': str(period)})
    return chips


def _records(frame):
    if frame is None or getattr(frame, 'empty', True):
        return []
    return frame.to_dict('records')


def _finished_rows(records, game_type):
    rows = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if not is_finished_status(record.get('status')):
            continue
        fixture_type = plain_fixture_type(record.get('fixtureType'))
        if not fixture_type or fixture_type != game_type:
            continue
        fixture_id = str(record.get('fixtureId') or '').strip()
        if not fixture_id:
            continue
        rows.append(record)
    return rows


def _is_overtime(period):
    if period in _REGULATION_PERIODS:
        return False
    try:
        return int(period) not in (1, 2, 3, 4)
    except (TypeError, ValueError):
        return False


def _period_ids(period):
    if period in (None, '', 'all'):
        return None
    ids, _recompute = _chip_spec(period)
    return ids


def _subset(frame, fixture_id, entity_id):
    if frame is None or len(frame) == 0 or 'fixtureId' not in frame.columns or 'entityId' not in frame.columns:
        return pd.DataFrame()
    fixtures = frame['fixtureId'].astype(str)
    entities = frame['entityId'].astype(str)
    return frame[(fixtures == str(fixture_id)) & (entities == str(entity_id))]


def _slice_rows(totals, periods, fixture_id, entity_id, period):
    if period in (None, '', 'all'):
        return _subset(totals, fixture_id, entity_id)
    matched = _subset(periods, fixture_id, entity_id)
    return _filter_periods(matched, _period_ids(period))


def _blank_sum(entity_id):
    row = {field: 0 for field in _TEAM_COUNT_FIELDS}
    row['entityId'] = entity_id
    row['minutes'] = 'PT0S'
    return row


def _combine(pieces, entity_id):
    if not pieces:
        row = _blank_sum(entity_id)
        _recompute_rates(row)
        return row
    block = pd.concat(pieces, ignore_index=True)
    row = _sum_fields(block, _TEAM_COUNT_FIELDS)
    row['minutes'] = _sum_clocks(block['minutes']) if 'minutes' in block.columns else 'PT0S'
    row['entityId'] = entity_id
    _recompute_rates(row)
    return row


def _column_sum(frame, name):
    if frame is None or len(frame) == 0 or name not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[name], errors='coerce').fillna(0).sum())


def _estimate_poss(frame):
    """Box estimate from the slice rows, before rates rewrite FGA as 2A+3A."""
    if frame is not None and len(frame) and 'fieldGoalsAttempted' in frame.columns:
        fga = _column_sum(frame, 'fieldGoalsAttempted')
    else:
        fga = _column_sum(frame, 'pointsTwoAttempted') + _column_sum(frame, 'pointsThreeAttempted')
    return (
        fga
        + 0.4 * _column_sum(frame, 'freeThrowsAttempted')
        + _column_sum(frame, 'turnovers')
        - _column_sum(frame, 'reboundsOffensive')
    )


def _mean(total, games):
    if games <= 0:
        return ''
    return '{0:.1f}'.format(float(total) / float(games))


def _mean_minutes(clock, games):
    if games <= 0:
        return ''
    seconds = clock_to_seconds(clock)
    if seconds is None:
        seconds = 0
    return minutes_to_mmss(float(seconds) / float(games))


def _raw_name(id_table, entity_id):
    table = id_table or {}
    name = table.get(entity_id)
    if name is None:
        name = table.get(str(entity_id))
    if name is None:
        return ''
    return str(name)


def _entities(totals, periods, fixture_ids, period):
    source = periods if _is_overtime(period) else totals
    if source is None or len(source) == 0 or 'entityId' not in source.columns:
        return []
    wanted = set(fixture_ids)
    found = []
    seen = set()
    fixtures = source['fixtureId'].astype(str)
    for entity, fixture_id in zip(source['entityId'].tolist(), fixtures.tolist()):
        if fixture_id not in wanted or entity in seen:
            continue
        if _is_overtime(period):
            matched = _slice_rows(totals, periods, fixture_id, entity, period)
            if matched is None or len(matched) == 0:
                continue
        seen.add(entity)
        found.append(entity)
    return found


def _game_ids_for_team(entity_id, fixture_ids, totals, periods, period):
    played = []
    for fixture_id in fixture_ids:
        if _is_overtime(period):
            matched = _slice_rows(totals, periods, fixture_id, entity_id, period)
        else:
            matched = _subset(totals, fixture_id, entity_id)
        if matched is not None and len(matched):
            played.append(fixture_id)
    return played


def _possessions(entity_id, game_ids, totals, periods, pbp_by_fixture, period):
    total = 0.0
    period_ids = _period_ids(period)
    for fixture_id in game_ids:
        pbp = (pbp_by_fixture or {}).get(fixture_id)
        if pbp is None:
            matched = _slice_rows(totals, periods, fixture_id, entity_id, period)
            if matched is not None and len(matched):
                total += _estimate_poss(matched)
            continue
        counts = possession_counts(pbp, period_ids)
        total += float(counts.get(entity_id, counts.get(str(entity_id), 0)) or 0)
    return total


def _leaves(entity_id, game_ids, pbp_by_fixture, period):
    totals = {key: 0 for key in _LEAF_KEYS}
    period_ids = _period_ids(period)
    for fixture_id in game_ids:
        pbp = (pbp_by_fixture or {}).get(fixture_id)
        if pbp is None or getattr(pbp, 'empty', True):
            continue
        splits = _flag_split_counts(pbp, [entity_id], period_ids)
        bucket = splits.get(entity_id) or splits.get(str(entity_id)) or {}
        for key in _LEAF_KEYS:
            value = bucket.get(key, 0)
            try:
                totals[key] += 0 if value == '' else int(value)
            except (TypeError, ValueError):
                continue
    return totals


def _pace_and_advanced(entity_id, summed, possessions, id_table, minutes):
    source = pd.DataFrame([summed])
    report = PostGameReport.__new__(PostGameReport)
    report.id_table = id_table or {}
    report.team_stats_df = source
    report.playbyplay_df = pd.DataFrame()
    report.regulation_minutes = minutes
    poss = {entity_id: possessions, str(entity_id): possessions}
    pace = report.get_team_advance_stats_df(
        source, share_mean=False, poss_by_entity=poss,
    ).iloc[0]
    advanced = report.get_team_advanced_df(source, poss_by_entity=poss).iloc[0]
    return pace, advanced


def _cell(text):
    return {
        'text': '' if text is None else str(text),
        'winner': False,
        'opp_best': False,
    }


def _parse_stat(text):
    raw = '' if text is None else str(text).strip()
    if not raw or raw.lower() in ('nan', 'none'):
        return None
    if raw.startswith('.') and raw[1:].replace('.', '', 1).isdigit():
        raw = '0' + raw
    if raw.endswith('%'):
        raw = raw[:-1].strip()
    try:
        return float(raw)
    except ValueError:
        return None


def _paint_winners(rows, columns, flag='winner'):
    for column in columns:
        if column in _UNCOLORED:
            continue
        values = [_parse_stat(row[column]['text']) for row in rows]
        lower = column in _LOWER_IS_BETTER
        for index in winning_indexes(values, lower):
            rows[index][column][flag] = True


def _other_entities(frame, fixture_id, entity_id):
    columns = getattr(frame, 'columns', [])
    if frame is None or len(frame) == 0 or 'fixtureId' not in columns or 'entityId' not in columns:
        return []
    fixtures = frame['fixtureId'].astype(str)
    subset = frame.loc[fixtures == str(fixture_id)]
    found = []
    seen = set()
    own = str(entity_id)
    for entity in subset['entityId'].tolist():
        key = str(entity)
        if key == own or key in seen:
            continue
        seen.add(key)
        found.append(entity)
    return found


def _opponent_inputs(entity_id, game_ids, totals, periods, pbp_by_fixture, period):
    pieces = []
    possessions = 0.0
    leaves = {key: 0 for key in _LEAF_KEYS}
    source = totals if period in (None, '', 'all') else periods
    for fixture_id in game_ids:
        for other in _other_entities(source, fixture_id, entity_id):
            matched = _slice_rows(totals, periods, fixture_id, other, period)
            if matched is None or len(matched) == 0:
                continue
            pieces.append(matched)
            possessions += _possessions(
                other, [fixture_id], totals, periods, pbp_by_fixture, period,
            )
            one = _leaves(other, [fixture_id], pbp_by_fixture, period)
            for key in _LEAF_KEYS:
                leaves[key] += one.get(key, 0)
    return _combine(pieces, entity_id), possessions, leaves


def _stat_rows(label, games, summed, leaves, pace, advanced, opp=False, opp_label='Opp'):
    name = opp_label if opp else label
    team = {
        'Team': _cell(name),
        'GP': _cell('' if opp else str(games)),
        'Min': _cell('' if opp else _mean_minutes(summed.get('minutes'), games)),
        '2M': _cell(_mean(summed.get('pointsTwoMade'), games)),
        '2A': _cell(_mean(summed.get('pointsTwoAttempted'), games)),
        '2FG%': _cell(shot_pct_display(summed.get('pointsTwoMade'), summed.get('pointsTwoAttempted'))),
        '3M': _cell(_mean(summed.get('pointsThreeMade'), games)),
        '3A': _cell(_mean(summed.get('pointsThreeAttempted'), games)),
        '3FG%': _cell(shot_pct_display(summed.get('pointsThreeMade'), summed.get('pointsThreeAttempted'))),
        'FTM': _cell(_mean(summed.get('freeThrowsMade'), games)),
        'FTA': _cell(_mean(summed.get('freeThrowsAttempted'), games)),
        'FT%': _cell(shot_pct_display(summed.get('freeThrowsMade'), summed.get('freeThrowsAttempted'))),
        'OR': _cell(_mean(summed.get('reboundsOffensive'), games)),
        'DR': _cell(_mean(summed.get('reboundsDefensive'), games)),
        'REB': _cell(_mean(summed.get('rebounds'), games)),
        'AST': _cell(_mean(summed.get('assists'), games)),
        'TO': _cell(_mean(summed.get('turnovers'), games)),
        'ST': _cell(_mean(summed.get('steals'), games)),
        'BS': _cell(_mean(summed.get('blocks'), games)),
        'PF': _cell(_mean(summed.get('foulsTotal'), games)),
        'FD': _cell(_mean(summed.get('foulsDrawn'), games)),
        'PTS': _cell(_mean(summed.get('points'), games)),
    }
    key = {
        'Team': _cell(name),
        'GP': _cell('' if opp else str(games)),
    }
    for column, field in _KEY_API:
        key[column] = _cell(_mean(summed.get(field), games))
    for leaf in _LEAF_KEYS:
        key[leaf] = _cell(_mean(leaves.get(leaf, 0), games))
    pace_row = {
        'Team': _cell(name),
        'GP': _cell('' if opp else str(games)),
        'Pace': _cell(pace.get('Pace')),
        'eFG%': _cell(pace.get('eFG%')),
        'TO%': _cell(pace.get('TO%')),
        'ORB%': _cell(pace.get('ORB%')),
        'FT-R': _cell(pace.get('FT-R')),
    }
    advanced_row = {
        'Team': _cell(name),
        'GP': _cell('' if opp else str(games)),
        'PPP': _cell(advanced.get('PPP')),
        'AS/TO': _cell(advanced.get('AS/TO')),
        'AST%': _cell(advanced.get('AST%')),
        '3P-R': _cell(advanced.get('3P-R')),
        'TS%': _cell(advanced.get('TS%')),
    }
    if opp:
        for row in (team, key, pace_row, advanced_row):
            row['opp'] = True
    return team, key, pace_row, advanced_row


def _entity_text(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except TypeError:
        pass
    text = str(value).strip()
    if not text or text.lower() in ('nan', 'none'):
        return ''
    return text


def _menu(found, all_label):
    ordered = sorted(found.items(), key=lambda item: (item[1], item[0]))
    options = [{'label': all_label, 'value': 'all'}]
    options.extend(
        {'label': name, 'value': entity} for entity, name in ordered
    )
    return options, len(ordered) >= 2


def _named_teams(records, id_table):
    found = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        for key in ('teamIdHome', 'teamIdAway'):
            entity = _entity_text(record.get(key))
            if not entity or display_name(id_table, entity) == TEAM_TBD:
                continue
            found.setdefault(entity, display_name(id_table, entity))
    return sorted(found.items(), key=lambda item: (item[1], item[0]))


def team_menu(records, id_table):
    """Named teams on this season's fixture list. The first option is All Teams."""
    ordered = _named_teams(records, id_table)
    options = [{'label': TEAM_ALL_LABEL, 'value': TEAM_ALL}]
    options.extend({'label': name, 'value': entity} for entity, name in ordered)
    return options, len(ordered) >= 2


def opponent_menu(records, id_table):
    """Named teams on this season's fixture list. Game type does not shrink it."""
    ordered = _named_teams(records, id_table)
    options = [{'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL}]
    options.extend(
        {'label': 'vs ' + name, 'value': entity} for entity, name in ordered
    )
    return options, len(ordered) >= 2


def stadium_menu(records, id_table):
    """Venues on the finished games of one game type."""
    found = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        venue = _entity_text(record.get('venueId'))
        if not venue or display_name(id_table, venue) == TEAM_TBD:
            continue
        found.setdefault(venue, display_name(id_table, venue))
    return _menu(found, STADIUM_ALL_LABEL)


def _coerce_menu(value, options, visible, default='all'):
    if not visible:
        return default
    text = _entity_text(value) or default
    if text == default:
        return default
    ids = {item['value'] for item in options if item['value'] != default}
    if text in ids:
        return text
    return default


def _coerce_site(value):
    text = _entity_text(value) or SITE_ALL
    if text in ('all', 'away', 'home'):
        return text
    return SITE_ALL


def _sides(record):
    if not isinstance(record, dict):
        return '', ''
    return _entity_text(record.get('teamIdHome')), _entity_text(record.get('teamIdAway'))


def _rows_for_chips(included, stadium, opponent):
    rows = []
    for record in included or []:
        if stadium != STADIUM_ALL and _entity_text(record.get('venueId')) != stadium:
            continue
        if opponent != OPPONENT_ALL:
            home, away = _sides(record)
            if opponent not in (home, away):
                continue
        rows.append(record)
    return rows


def _game_passes(record, entity_id, opponent, stadium, site):
    if not isinstance(record, dict):
        return False
    if stadium != STADIUM_ALL and _entity_text(record.get('venueId')) != stadium:
        return False
    home, away = _sides(record)
    own = str(entity_id)
    if opponent != OPPONENT_ALL:
        if own == opponent or own not in (home, away) or opponent not in (home, away):
            return False
    if site == 'home':
        return home == own
    if site == 'away':
        return away == own
    return True


def _other_side(record, entity_id):
    home, away = _sides(record)
    own = str(entity_id)
    if home == own:
        return away
    if away == own:
        return home
    return ''


def _mark_summary(rows):
    for row in rows:
        row['summary'] = True
    return rows


def _collect_side(
    entity, game_ids, label, opp_label, totals, periods, pbp_by_fixture,
    period, id_table, minutes, summary=False,
):
    pieces = []
    for fixture_id in game_ids:
        matched = _slice_rows(totals, periods, fixture_id, entity, period)
        if matched is not None and len(matched):
            pieces.append(matched)
    summed = _combine(pieces, entity)
    possessions = _possessions(
        entity, game_ids, totals, periods, pbp_by_fixture, period,
    )
    leaves = _leaves(entity, game_ids, pbp_by_fixture, period)
    pace, advanced = _pace_and_advanced(entity, summed, possessions, id_table, minutes)
    team, key, pace_row, advanced_row = _stat_rows(
        label, len(game_ids), summed, leaves, pace, advanced,
    )
    opp_summed, opp_poss, opp_leaves = _opponent_inputs(
        entity, game_ids, totals, periods, pbp_by_fixture, period,
    )
    opp_pace, opp_advanced = _pace_and_advanced(
        entity, opp_summed, opp_poss, id_table, minutes,
    )
    opp_team, opp_key, opp_pace_row, opp_advanced_row = _stat_rows(
        label, len(game_ids), opp_summed, opp_leaves, opp_pace, opp_advanced,
        opp=True, opp_label=opp_label,
    )
    if summary:
        _mark_summary((
            team, key, pace_row, advanced_row,
            opp_team, opp_key, opp_pace_row, opp_advanced_row,
        ))
    return (
        team, key, pace_row, advanced_row,
        opp_team, opp_key, opp_pace_row, opp_advanced_row,
    )


def _paint_pair(rows, opp_rows, columns):
    _paint_winners([row for row in rows if not row.get('summary')], columns)
    _paint_winners(
        [row for row in opp_rows if not row.get('summary')], columns, 'opp_best',
    )


def build_team_cards(
    fixtures, totals, periods, pbp_by_fixture, id_table, minutes, game_type, period,
    opponent=OPPONENT_ALL, stadium=STADIUM_ALL, site=SITE_ALL, team=TEAM_ALL,
):
    """Pure card payload for fixtures and stats already in memory."""
    schedule = _records(fixtures) if not isinstance(fixtures, list) else list(fixtures)
    options = fixture_type_options(schedule)
    selected_type = choose_game_type(options, game_type)
    included = _finished_rows(schedule, selected_type) if selected_type else []
    opponent_options, opponent_visible = opponent_menu(schedule, id_table)
    team_options, team_visible = team_menu(schedule, id_table)
    stadium_options, stadium_visible = stadium_menu(included, id_table)
    selected_opponent = _coerce_menu(opponent, opponent_options, opponent_visible)
    selected_team = _coerce_menu(team, team_options, team_visible, TEAM_ALL)
    if selected_team != TEAM_ALL and selected_team == selected_opponent:
        selected_opponent = OPPONENT_ALL
    selected_stadium = _coerce_menu(stadium, stadium_options, stadium_visible)
    selected_site = _coerce_site(site)
    chip_rows = _rows_for_chips(included, selected_stadium, selected_opponent)
    if selected_team != TEAM_ALL:
        chip_rows = [row for row in chip_rows if selected_team in _sides(row)]
    fixture_ids = [str(row.get('fixtureId')) for row in chip_rows]
    by_fixture = {str(row.get('fixtureId')): row for row in chip_rows}
    shown_opponents = [
        item for item in opponent_options
        if item['value'] == OPPONENT_ALL or item['value'] != selected_team
    ]
    # Menu labels are "vs {name}". The Opp cell keeps the bare name.
    opp_label = 'Opp'
    if selected_opponent != OPPONENT_ALL:
        bare = display_name(id_table, selected_opponent)
        if bare != TEAM_TBD:
            opp_label = bare
    period_rows = periods
    if period_rows is not None and len(period_rows) and 'fixtureId' in period_rows.columns:
        mask = period_rows['fixtureId'].astype(str).isin(fixture_ids)
        period_rows = period_rows.loc[mask]
    chips = period_chips_for_ids(
        period_rows['periodId'].tolist() if period_rows is not None and len(period_rows) and 'periodId' in period_rows.columns else []
    )
    chip_values = {item['value'] for item in chips}
    selected_period = period if period in chip_values else 'all'
    entities = _entities(totals, periods, fixture_ids, selected_period)
    named = []
    for entity in entities:
        if display_name(id_table, entity) == TEAM_TBD:
            continue
        named.append(entity)
    named.sort(key=lambda entity: (_raw_name(id_table, entity), str(entity)))

    buckets = [[] for _ in range(8)]

    def _push(parts):
        for bucket, part in zip(buckets, parts):
            bucket.append(part)

    if selected_team == TEAM_ALL:
        for entity in named:
            if selected_opponent != OPPONENT_ALL and str(entity) == selected_opponent:
                continue
            game_ids = [
                fixture_id for fixture_id in _game_ids_for_team(
                    entity, fixture_ids, totals, periods, selected_period,
                )
                if _game_passes(
                    by_fixture.get(str(fixture_id)), entity,
                    selected_opponent, selected_stadium, selected_site,
                )
            ]
            if not game_ids:
                continue
            _push(_collect_side(
                entity, game_ids, display_name(id_table, entity), opp_label,
                totals, periods, pbp_by_fixture, selected_period, id_table, minutes,
            ))
    else:
        own_name = display_name(id_table, selected_team)
        played = [
            fixture_id for fixture_id in _game_ids_for_team(
                selected_team, fixture_ids, totals, periods, selected_period,
            )
            if _game_passes(
                by_fixture.get(str(fixture_id)), selected_team,
                selected_opponent, selected_stadium, selected_site,
            )
        ]
        groups = {}
        for fixture_id in played:
            other = _other_side(by_fixture.get(str(fixture_id)), selected_team)
            if not other or display_name(id_table, other) == TEAM_TBD:
                continue
            groups.setdefault(other, []).append(fixture_id)
        ordered = sorted(
            groups.items(),
            key=lambda item: (_raw_name(id_table, item[0]), str(item[0])),
        )
        if selected_opponent == OPPONENT_ALL and played:
            _push(_collect_side(
                selected_team, played, own_name, 'Opp',
                totals, periods, pbp_by_fixture, selected_period, id_table, minutes,
                summary=True,
            ))
        for other, game_ids in ordered:
            _push(_collect_side(
                selected_team, game_ids, own_name + ' vs', display_name(id_table, other),
                totals, periods, pbp_by_fixture, selected_period, id_table, minutes,
            ))
    (
        team_rows, key_rows, pace_rows, advanced_rows,
        opp_team_rows, opp_key_rows, opp_pace_rows, opp_advanced_rows,
    ) = buckets
    _paint_pair(team_rows, opp_team_rows, _TEAM_COLUMNS)
    _paint_pair(key_rows, opp_key_rows, _KEY_COLUMNS)
    _paint_pair(pace_rows, opp_pace_rows, _PACE_COLUMNS)
    _paint_pair(advanced_rows, opp_advanced_rows, _ADVANCED_COLUMNS)
    visible = bool(team_rows)
    return {
        'game_types': options,
        'game_type': selected_type,
        'game_type_visible': len(options) > 1,
        'period': selected_period if visible else 'all',
        'period_chips': chips if visible else [],
        'period_visible': visible and bool(chips),
        'empty': not visible,
        'team': selected_team,
        'team_options': team_options,
        'team_visible': team_visible,
        'show_opp_locked': selected_team != TEAM_ALL,
        'opponent': selected_opponent,
        'opponent_options': shown_opponents,
        'opponent_width_labels': [item['label'] for item in opponent_options],
        'opponent_visible': opponent_visible,
        'stadium': selected_stadium,
        'stadium_options': stadium_options,
        'stadium_visible': stadium_visible,
        'site': selected_site,
        'cards': None if not visible else {
            'pace': {
                'id': 'pace', 'title': PACE_CARD_TITLE, 'columns': list(_PACE_COLUMNS),
                'rows': pace_rows, 'opp_rows': opp_pace_rows,
            },
            'advanced': {
                'id': 'advanced', 'title': ADVANCED_CARD_TITLE, 'columns': list(_ADVANCED_COLUMNS),
                'rows': advanced_rows, 'opp_rows': opp_advanced_rows,
            },
            'key': {
                'id': 'key', 'title': KEY_CARD_TITLE, 'columns': list(_KEY_COLUMNS),
                'rows': key_rows, 'opp_rows': opp_key_rows,
            },
            'team': {
                'id': 'team', 'title': None, 'columns': list(_TEAM_COLUMNS),
                'rows': team_rows, 'opp_rows': opp_team_rows,
            },
        },
    }


def _normalize_items(items, with_period):
    records = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        stats = item.get('statistics') if isinstance(item.get('statistics'), dict) else {}
        row = dict(stats)
        for key, value in item.items():
            if key == 'statistics':
                continue
            row.setdefault(key, value)
        row['fixtureId'] = item.get('fixtureId') or row.get('fixtureId')
        row['entityId'] = item.get('entityId') or row.get('entityId')
        if with_period:
            row['periodId'] = item.get('periodId') if item.get('periodId') is not None else row.get('periodId')
        records.append(row)
    return pd.DataFrame(records)


def _split_into_frames(org_id, schedule, totals, periods):
    status = {}
    for record in schedule:
        fixture_id = str(record.get('fixtureId') or '').strip()
        if fixture_id:
            status[fixture_id] = record.get('status')
    if totals is not None and len(totals) and 'fixtureId' in totals.columns:
        for fixture_id, group in totals.groupby(totals['fixtureId'].astype(str)):
            frame_store.store(
                org_id, fixture_id, status=status.get(str(fixture_id)),
                team_df=group, touch=('team_df',),
            )
    if periods is not None and len(periods) and 'fixtureId' in periods.columns:
        for fixture_id, group in periods.groupby(periods['fixtureId'].astype(str)):
            frame_store.store(
                org_id, fixture_id, status=status.get(str(fixture_id)),
                periods_df=group, touch=('periods_df',),
            )


def _remember_report_pbp(org_id, row):
    fixture_id = str(row.get('fixtureId'))
    frame = frame_store.peek(org_id, fixture_id)
    if frame_store.piece_fresh(frame, 'playbyplay_df'):
        return False
    report = peek_finished_report(fixture_id, org_id)
    pbp = getattr(report, 'playbyplay_df', None) if report is not None else None
    if pbp is None:
        return False
    frame_store.store(
        org_id, fixture_id, status=row.get('status'),
        playbyplay_df=pbp, touch=('playbyplay_df',),
    )
    return True


def _download_pbp(org_id, row):
    fixture_id = str(row.get('fixtureId'))
    status = row.get('status')

    def _build():
        try:
            payload = Communicator_pbp(org_id, fixture_id, status)
            frame = Parser._pbp_df_from_json(payload)
            frame_store.store(
                org_id, fixture_id, status=status,
                playbyplay_df=frame, touch=('playbyplay_df',),
            )
        except Exception:
            log_unexpected.exception('team stats play-by-play failed fixture=%s', fixture_id)
            frame_store.store(
                org_id, fixture_id, status=status,
                pbp_failed=True, touch=('playbyplay_df',),
            )
    frame_store.singleflight((org_id, fixture_id, 'pbp'), _build)


def Communicator_pbp(org_id, fixture_id, status):
    from synergy_inbounder.communicator import Communicator
    return Communicator.get_game_play_by_play_synergy(
        org_id, fixture_id, live=False, fixture_status=status,
    )


def _pbp_pending(org_id, rows):
    """Rows whose play-by-play is not already in memory.

    Fresh frame-store pieces are skipped. A finished report that already holds
    the frame is copied in and skipped, so that copy is not a Synergy download.
    """
    pending = []
    for row in rows or []:
        fixture_id = str(row.get('fixtureId') or '').strip()
        if not fixture_id:
            continue
        frame = frame_store.peek(org_id, fixture_id)
        if frame_store.piece_fresh(frame, 'playbyplay_df'):
            continue
        if _remember_report_pbp(org_id, row):
            continue
        pending.append(row)
    return pending


def _ensure_pbp(org_id, rows):
    pending = _pbp_pending(org_id, rows)
    if not pending:
        return
    run_wave([lambda row=row: _download_pbp(org_id, row) for row in pending])


def type_needs_download(league, season_id, game_type):
    """True when showing this game type still has to call Synergy.

    No organization or no season bundle means the click must hit the API.
    A blank type has nothing to download. Pending rows are the same set
    ``_ensure_pbp`` would fetch.
    """
    org_id = organization_for_league(league)
    if org_id is None or not season_id:
        return True
    with _bundle_lock:
        bundle = _bundles.get((org_id, season_id))
    if not bundle:
        return True
    chosen = plain_fixture_type(game_type)
    if not chosen:
        return False
    return bool(_pbp_pending(org_id, _finished_rows(bundle.get('schedule') or [], chosen)))


def _pbp_map(org_id, rows):
    found = {}
    for row in rows:
        fixture_id = str(row.get('fixtureId'))
        frame = frame_store.peek(org_id, fixture_id)
        if frame is None or frame.pbp_failed or frame.playbyplay_df is None:
            found[fixture_id] = None
        else:
            found[fixture_id] = frame.playbyplay_df
    return found


def _load_bundle(org_id, season_id, reason):
    key = (org_id, season_id)
    now = time.monotonic()
    with _bundle_lock:
        current = _bundles.get(key)
    if current and reason in ('chip', 'type', 'slice'):
        return current
    if current and reason == 'scope' and (now - current['fetched_at']) < SHORT_CACHE_SECONDS:
        return current
    box = []
    token = _cache_hits.set(box)
    try:
        season_df, total_rows, period_rows, id_table = run_wave([
            lambda: Parser.parse_season_game_list_df(org_id, season_id),
            lambda: Communicator_totals(org_id, season_id),
            lambda: Communicator_periods(org_id, season_id),
            lambda: Parser.parse_id_tables(org_id),
        ])
    finally:
        _cache_hits.reset(token)
    schedule = _records(season_df)
    totals = _normalize_items(total_rows, with_period=False)
    periods = _normalize_items(period_rows, with_period=True)
    _split_into_frames(org_id, schedule, totals, periods)
    network = any(not hit for hit in box)
    stamp = current['stamp'] if current and not network else taipei_now_label()
    entry = {
        'schedule': schedule,
        'totals': totals,
        'periods': periods,
        'id_table': id_table or {},
        'stamp': stamp,
        'fetched_at': time.monotonic(),
    }
    with _bundle_lock:
        _bundles[key] = entry
    finished_ids = [
        str(row.get('fixtureId'))
        for row in schedule
        if is_finished_status(row.get('status')) and row.get('fixtureId')
    ]
    frame_store.pin_season(org_id, season_id, finished_ids)
    return entry


def Communicator_totals(org_id, season_id):
    from synergy_inbounder.communicator import Communicator
    return Communicator.get_season_team_totals(org_id, season_id)


def Communicator_periods(org_id, season_id):
    from synergy_inbounder.communicator import Communicator
    return Communicator.get_season_team_periods(org_id, season_id)


def _error_payload(league, season_id, seasons):
    return {
        'ok': False,
        'empty': False,
        'message': ERROR_GAME,
        'next_step': '',
        'stamp': 'Last Update: —',
        'league': league,
        'season_id': season_id,
        'seasons': seasons,
        'game_type': None,
        'game_types': [],
        'game_type_visible': False,
        'period': 'all',
        'period_chips': [],
        'period_visible': False,
        'team': TEAM_ALL,
        'team_options': [{'label': TEAM_ALL_LABEL, 'value': TEAM_ALL}],
        'team_visible': False,
        'show_opp_locked': False,
        'opponent': OPPONENT_ALL,
        'opponent_options': [{'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL}],
        'opponent_width_labels': [OPPONENT_ALL_LABEL],
        'opponent_visible': False,
        'stadium': STADIUM_ALL,
        'stadium_options': [{'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL}],
        'stadium_visible': False,
        'site': SITE_ALL,
        'cards': None,
    }


def team_stats_payload(
    league, season_id=None, game_type=None, period='all', reason='scope',
    opponent=OPPONENT_ALL, stadium=STADIUM_ALL, site=SITE_ALL, team=TEAM_ALL,
):
    """Load one season view and return the four Box Score team cards.

    ``reason`` is ``scope`` (entry, league, or season), ``type`` (game type),
    ``chip`` (period), or ``slice`` (opponent, stadium, or site). A chip or
    slice does not refetch and does not move Last Update.
    """
    key = str(league or '').strip().upper()
    seasons = [
        {'label': label, 'value': value}
        for label, value in selectable_seasons(key)
    ]
    org_id = organization_for_league(key)
    if org_id is None or not seasons:
        return _error_payload(key or None, season_id, seasons)
    selected_season = season_id if any(item['value'] == season_id for item in seasons) else seasons[0]['value']
    minutes = regulation_minutes(selected_season)
    if minutes is None:
        return _error_payload(key, selected_season, seasons)
    view_reason = reason if reason in ('scope', 'type', 'chip', 'slice') else 'scope'
    if view_reason == 'scope':
        opponent = OPPONENT_ALL
        stadium = STADIUM_ALL
        site = SITE_ALL
        team = TEAM_ALL
    try:
        with _bundle_lock:
            had_bundle = (org_id, selected_season) in _bundles
        bundle = _load_bundle(org_id, selected_season, view_reason)
        schedule = bundle['schedule']
        options = fixture_type_options(schedule)
        selected_type = choose_game_type(options, None if view_reason == 'scope' else game_type)
        included = _finished_rows(schedule, selected_type) if selected_type else []
        if view_reason not in ('chip', 'slice') or not had_bundle:
            box = []
            token = _cache_hits.set(box)
            try:
                _ensure_pbp(org_id, included)
            finally:
                _cache_hits.reset(token)
            if any(not hit for hit in box):
                bundle['stamp'] = taipei_now_label()
        built = build_team_cards(
            schedule,
            bundle['totals'],
            bundle['periods'],
            _pbp_map(org_id, included),
            bundle['id_table'],
            minutes,
            selected_type,
            'all' if view_reason in ('scope', 'type') else period,
            opponent=opponent,
            stadium=stadium,
            site=site,
            team=team,
        )
    except SynergyAuthError:
        log_auth.exception('team stats load auth failed %s %s', key, selected_season)
        return _error_payload(key, selected_season, seasons)
    except Exception:
        log_unexpected.exception('team stats load failed %s %s', key, selected_season)
        return _error_payload(key, selected_season, seasons)
    payload = {
        'ok': True,
        'message': EMPTY_TEAM_STATS if built['empty'] else '',
        'next_step': EMPTY_TEAM_STATS_NEXT if built['empty'] else '',
        'stamp': bundle['stamp'],
        'league': key,
        'season_id': selected_season,
        'seasons': seasons,
        'game_type': built['game_type'],
        'game_types': built['game_types'],
        'game_type_visible': built['game_type_visible'],
        'period': built['period'],
        'period_chips': built['period_chips'],
        'period_visible': built['period_visible'],
        'team': built['team'],
        'team_options': built['team_options'],
        'team_visible': built['team_visible'],
        'show_opp_locked': built['show_opp_locked'],
        'opponent': built['opponent'],
        'opponent_options': built['opponent_options'],
        'opponent_width_labels': built['opponent_width_labels'],
        'opponent_visible': built['opponent_visible'],
        'stadium': built['stadium'],
        'stadium_options': built['stadium_options'],
        'stadium_visible': built['stadium_visible'],
        'site': built['site'],
        'empty': built['empty'],
        'cards': built['cards'],
        'card_order': ['pace', 'advanced', 'key', 'team'],
    }
    return payload


def rotation_games(league, season_id, game_type, opponent, stadium, site, team):
    """Finished games for one club after the shared filters.

    Uses the season bundle already loaded for Box Score. A slice reason does
    not refetch when that bundle is warm.
    """
    key = str(league or '').strip().upper()
    org_id = organization_for_league(key)
    minutes = regulation_minutes(season_id) if season_id else None
    empty = {
        'ok': True,
        'select_team': True,
        'empty': False,
        'games': [],
        'minutes': minutes,
        'id_table': {},
        'org_id': org_id,
        'team': TEAM_ALL,
        'opponent': OPPONENT_ALL,
    }
    if org_id is None or minutes is None or not season_id:
        empty['ok'] = False
        return empty
    if not team or team == TEAM_ALL:
        return empty
    try:
        bundle = _load_bundle(org_id, season_id, 'slice')
        schedule = bundle.get('schedule') or []
        selected_type = choose_game_type(fixture_type_options(schedule), game_type)
        included = _finished_rows(schedule, selected_type) if selected_type else []
        menu, visible = opponent_menu(schedule, bundle.get('id_table'))
        chosen_opponent = _coerce_menu(opponent, menu, visible)
        if str(chosen_opponent) == str(team):
            chosen_opponent = OPPONENT_ALL
        chosen_stadium = _entity_text(stadium) or STADIUM_ALL
        chosen_site = _coerce_site(site)
        rows = []
        for record in included:
            if str(team) not in _sides(record):
                continue
            if not _game_passes(record, team, chosen_opponent, chosen_stadium, chosen_site):
                continue
            rows.append(record)
        _ensure_pbp(org_id, rows)
        pbp = _pbp_map(org_id, rows)
        games = []
        for record in rows:
            fixture_id = str(record.get('fixtureId'))
            games.append({
                'fixture_id': fixture_id,
                'status': record.get('status'),
                'home': _entity_text(record.get('teamIdHome')),
                'away': _entity_text(record.get('teamIdAway')),
                'pbp': pbp.get(fixture_id),
            })
    except SynergyAuthError:
        log_auth.exception('team rotation load auth failed %s %s', key, season_id)
        empty['ok'] = False
        return empty
    except Exception:
        log_unexpected.exception('team rotation load failed %s %s', key, season_id)
        empty['ok'] = False
        return empty
    return {
        'ok': True,
        'select_team': False,
        'empty': not games,
        'games': games,
        'minutes': minutes,
        'id_table': bundle.get('id_table') or {},
        'org_id': org_id,
        'team': str(team),
        'opponent': chosen_opponent,
    }
