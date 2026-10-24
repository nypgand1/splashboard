# -*- coding: utf-8 -*-
"""Season team cards for one league, season, and game type.

Counting columns are sums divided by GP. Shot percentages and the efficiency
cards sum the inputs first, then use the same formulas as one Box Score half.
"""
import logging
import threading
import time

import pandas as pd

from synergy_inbounder.communicator import SynergyApiError, _cache_hits
from synergy_inbounder.game_status import is_finished_status
from synergy_inbounder.http_wave import run_wave
from synergy_inbounder.live_budget import SHORT_CACHE_SECONDS
from synergy_inbounder.names import TEAM_TBD, display_name
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

LOGGER = logging.getLogger('SynergyInbounder')

EMPTY_TEAM_STATS = 'No games in this view.'
EMPTY_TEAM_STATS_NEXT = 'Switch Game Type.'
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
    return {'text': '' if text is None else str(text), 'winner': False}


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


def _paint_winners(rows, columns):
    if len(rows) < 2:
        return
    for column in columns:
        if column in _UNCOLORED:
            continue
        numbers = []
        for row in rows:
            number = _parse_stat(row[column]['text'])
            if number is None:
                numbers = None
                break
            numbers.append(number)
        if not numbers:
            continue
        best = min(numbers) if column in _LOWER_IS_BETTER else max(numbers)
        if numbers.count(best) != 1:
            continue
        rows[numbers.index(best)][column]['winner'] = True


def build_team_cards(fixtures, totals, periods, pbp_by_fixture, id_table, minutes, game_type, period):
    """Pure card payload for fixtures and stats already in memory."""
    schedule = _records(fixtures) if not isinstance(fixtures, list) else list(fixtures)
    options = fixture_type_options(schedule)
    selected_type = choose_game_type(options, game_type)
    included = _finished_rows(schedule, selected_type) if selected_type else []
    fixture_ids = [str(row.get('fixtureId')) for row in included]
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

    team_rows = []
    key_rows = []
    pace_rows = []
    advanced_rows = []
    for entity in named:
        game_ids = _game_ids_for_team(entity, fixture_ids, totals, periods, selected_period)
        games = len(game_ids)
        if games <= 0:
            continue
        pieces = []
        for fixture_id in game_ids:
            matched = _slice_rows(totals, periods, fixture_id, entity, selected_period)
            if matched is not None and len(matched):
                pieces.append(matched)
        summed = _combine(pieces, entity)
        label = display_name(id_table, entity)
        possessions = _possessions(
            entity, game_ids, totals, periods, pbp_by_fixture, selected_period,
        )
        leaves = _leaves(entity, game_ids, pbp_by_fixture, selected_period)
        pace, advanced = _pace_and_advanced(entity, summed, possessions, id_table, minutes)
        team_rows.append({
            'Team': _cell(label),
            'GP': _cell(str(games)),
            'Min': _cell(_mean_minutes(summed.get('minutes'), games)),
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
        })
        key = {
            'Team': _cell(label),
            'GP': _cell(str(games)),
        }
        for column, field in _KEY_API:
            key[column] = _cell(_mean(summed.get(field), games))
        for leaf in _LEAF_KEYS:
            key[leaf] = _cell(_mean(leaves.get(leaf, 0), games))
        key_rows.append(key)
        pace_rows.append({
            'Team': _cell(label),
            'GP': _cell(str(games)),
            'Pace': _cell(pace.get('Pace')),
            'eFG%': _cell(pace.get('eFG%')),
            'TO%': _cell(pace.get('TO%')),
            'ORB%': _cell(pace.get('ORB%')),
            'FT-R': _cell(pace.get('FT-R')),
        })
        advanced_rows.append({
            'Team': _cell(label),
            'GP': _cell(str(games)),
            'PPP': _cell(advanced.get('PPP')),
            'AS/TO': _cell(advanced.get('AS/TO')),
            'AST%': _cell(advanced.get('AST%')),
            '3P-R': _cell(advanced.get('3P-R')),
            'TS%': _cell(advanced.get('TS%')),
        })
    _paint_winners(team_rows, _TEAM_COLUMNS)
    _paint_winners(key_rows, _KEY_COLUMNS)
    _paint_winners(pace_rows, _PACE_COLUMNS)
    _paint_winners(advanced_rows, _ADVANCED_COLUMNS)
    visible = bool(team_rows)
    return {
        'game_types': options,
        'game_type': selected_type,
        'game_type_visible': len(options) > 1,
        'period': selected_period if visible else 'all',
        'period_chips': chips if visible else [],
        'period_visible': visible and bool(chips),
        'empty': not visible,
        'cards': None if not visible else {
            'pace': {'id': 'pace', 'title': PACE_CARD_TITLE, 'columns': list(_PACE_COLUMNS), 'rows': pace_rows},
            'advanced': {'id': 'advanced', 'title': ADVANCED_CARD_TITLE, 'columns': list(_ADVANCED_COLUMNS), 'rows': advanced_rows},
            'key': {'id': 'key', 'title': KEY_CARD_TITLE, 'columns': list(_KEY_COLUMNS), 'rows': key_rows},
            'team': {'id': 'team', 'title': None, 'columns': list(_TEAM_COLUMNS), 'rows': team_rows},
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
            LOGGER.warning('Team Stats play-by-play failed for %s', fixture_id)
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
    if current and reason in ('chip', 'type'):
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
        'cards': None,
    }


def team_stats_payload(league, season_id=None, game_type=None, period='all', reason='scope'):
    """Load one season view and return the four Box Score team cards.

    ``reason`` is ``scope`` (entry, league, or season), ``type`` (game type),
    or ``chip`` (period). A chip does not refetch and does not move Last Update.
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
    view_reason = reason if reason in ('scope', 'type', 'chip') else 'scope'
    try:
        with _bundle_lock:
            had_bundle = (org_id, selected_season) in _bundles
        bundle = _load_bundle(org_id, selected_season, view_reason)
        schedule = bundle['schedule']
        options = fixture_type_options(schedule)
        selected_type = choose_game_type(options, None if view_reason == 'scope' else game_type)
        included = _finished_rows(schedule, selected_type) if selected_type else []
        if view_reason != 'chip' or not had_bundle:
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
            'all' if view_reason == 'scope' else period,
        )
    except (SynergyApiError, Exception):
        LOGGER.warning('Team Stats failed to load %s %s', key, selected_season)
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
        'empty': built['empty'],
        'cards': built['cards'],
        'card_order': ['pace', 'advanced', 'key', 'team'],
    }
    return payload
