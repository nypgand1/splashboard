# -*- coding: utf-8 -*-
import json
import math

import pandas as pd

from domain.clocks import CLOCK_RE, clock_to_seconds
from domain.ids import (
    same_id as _same_id,
    shirt_label as _shirt_label,
    shirt_sort_key as _shirt_sort_key,
)
from domain.periods import period_label
from synergy_inbounder.names import person_name, player_label
from synergy_inbounder.possessions import annotate_possessions
from synergy_inbounder.pre_processing_func import process_lineup_pbp
from ui.charts.rotation_fig import (
    BASE_VERTICAL_SPACING,
    COUNT_INK,
    FIGURE_MARGIN_B,
    FIGURE_MARGIN_T,
    KILL_COLOR,
    KILL_ROW,
    LOWER_SEAM_INK,
    RUN_LABEL_INK,
    RUN_SCORE_SHIFT,
    SCORE_TEXT_DARK,
    SCORE_TEXT_LIGHT,
    SCORE_TEXT_LUMINANCE_THRESHOLD,
    SCORE_TEXT_SIZE,
    SEAM_LINE,
    STOP_COUNT_FONT,
    SUBPLOT_TITLE_FONT,
    _add_kill_annotations,
    _add_stop_counts,
    _open_lower_seam,
    _paint_team_titles,
    _raise_bottom_title,
    away_lane_height,
    build_rotation_figure as _build_rotation_figure_impl,
    contrast_text_color,
    margin_tick_span,
    relative_luminance,
    report_rotation_figure,
    score_text_colors,
    stop_seam_spacing,
)


def _parse_scores(value):
    if isinstance(value, dict):
        return {str(key): value[key] for key in value}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, dict):
            return {str(key): parsed[key] for key in parsed}
    return {}


def _as_player_list(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        return [p for p in value if p is not None and not (isinstance(p, float) and pd.isna(p))]
    return []


def _find_column(df, team_id):
    for column in df.columns:
        if _same_id(column, team_id):
            return column
    return None


def _infer_period_seconds(clocks):
    values = [clock_to_seconds(clock) for clock in clocks]
    values = [value for value in values if value is not None]
    if not values:
        return 600
    return int(math.ceil(max(values) / 60.0) * 60) or 60


def _made_points(row):
    if row is None:
        return 0
    success = row.get('success') if hasattr(row, 'get') else None
    if success not in (1, True, 1.0):
        return 0
    return {'freeThrow': 1, '2pt': 2, '3pt': 3}.get(row.get('eventType'), 0)


def _bucket_index(elapsed, buckets):
    for index, bucket in enumerate(buckets):
        if bucket['start'] <= elapsed < bucket['end']:
            return index
    if buckets and elapsed >= buckets[-1]['end']:
        return len(buckets) - 1
    if buckets and elapsed < buckets[0]['start']:
        return 0
    return None


def _add_overlap(cells, start_t, end_t, buckets):
    if end_t <= start_t:
        return 0.0
    added = 0.0
    for index, bucket in enumerate(buckets):
        overlap = min(end_t, bucket['end']) - max(start_t, bucket['start'])
        if overlap > 0:
            cells[index] += overlap
            added += overlap
    return added


GAME_START_DESC = 'Game start'
GAME_END_DESC = 'Game end'


def _side_steps(h_prev, a_prev, h_curr, a_curr, side):
    my_step = (h_curr - h_prev) if side == 'home' else (a_curr - a_prev)
    opp_step = (a_curr - a_prev) if side == 'home' else (h_curr - h_prev)
    return my_step, opp_step


RUN_MAX_GAP = 120
RUN_OPP_CAP = 4


def _crosses_halftime(score_points, i, j, halftime):
    if halftime is None:
        return False
    for k in range(i + 1, j + 1):
        if score_points[k - 1][0] < halftime <= score_points[k][0]:
            return True
    return False


def _side_score_times(score_points, i, j, side):
    times = []
    for k in range(i + 1, j + 1):
        my_step, _ = _side_steps(
            score_points[k - 1][1], score_points[k - 1][2],
            score_points[k][1], score_points[k][2], side,
        )
        if my_step > 0:
            times.append(score_points[k][0])
    return times


def _gap_breaks(times, max_gap):
    return any(later - earlier > max_gap for earlier, later in zip(times, times[1:]))


def _window_points(score_points, i, j, side, min_delta, max_opp_consecutive, halftime):
    """Points across a baseline→end stretch, or None when the stretch is not a run."""
    if i >= j or _crosses_halftime(score_points, i, j, halftime):
        return None
    streak = 0
    for k in range(i + 1, j + 1):
        my_step, opp_step = _side_steps(
            score_points[k - 1][1], score_points[k - 1][2],
            score_points[k][1], score_points[k][2], side,
        )
        if opp_step > 0:
            streak += opp_step
        if my_step > 0:
            streak = 0
        if streak > max_opp_consecutive:
            return None
    _, h0, a0 = score_points[i]
    _, h1, a1 = score_points[j]
    dh = h1 - h0
    da = a1 - a0
    my_tot = dh if side == 'home' else da
    opp_tot = da if side == 'home' else dh
    delta = my_tot - opp_tot
    if delta >= min_delta and my_tot >= min_delta and opp_tot <= RUN_OPP_CAP:
        return dh, da, delta
    return None


def _first_side_score_index(score_points, i, j, side):
    for k in range(i + 1, j + 1):
        my_step, _ = _side_steps(
            score_points[k - 1][1], score_points[k - 1][2],
            score_points[k][1], score_points[k][2], side,
        )
        if my_step > 0:
            return k
    return None


def _first_peak(score_points, i, side, min_delta, max_opp_consecutive, halftime, max_gap):
    """Earliest index where the net from `i` is at its maximum."""
    streak = 0
    best = None
    previous_side_time = None
    _, h0, a0 = score_points[i]
    for j in range(i + 1, len(score_points)):
        if _crosses_halftime(score_points, j - 1, j, halftime):
            break
        my_step, opp_step = _side_steps(
            score_points[j - 1][1], score_points[j - 1][2],
            score_points[j][1], score_points[j][2], side,
        )
        if my_step > 0 and previous_side_time is not None and score_points[j][0] - previous_side_time > max_gap:
            break
        if opp_step > 0:
            streak += opp_step
        if my_step > 0:
            streak = 0
            previous_side_time = score_points[j][0]
        if streak > max_opp_consecutive:
            break
        dh = score_points[j][1] - h0
        da = score_points[j][2] - a0
        my_tot = dh if side == 'home' else da
        opp_tot = da if side == 'home' else dh
        delta = my_tot - opp_tot
        if delta >= min_delta and my_tot >= min_delta and opp_tot <= RUN_OPP_CAP:
            if best is None or delta > best[0]:
                best = (delta, j)
    return None if best is None else best[1]


def detect_runs(events_with_scores, min_delta=8, max_opp_consecutive=3, halftime=None, max_gap=RUN_MAX_GAP):
    """Detect basketball momentum runs."""
    if not events_with_scores or len(events_with_scores) < 2:
        return []

    score_points = [events_with_scores[0]]
    for pt in events_with_scores[1:]:
        if pt[1] != score_points[-1][1] or pt[2] != score_points[-1][2]:
            score_points.append(pt)

    n = len(score_points)
    raw_runs = []
    for side in ('home', 'away'):
        for j in range(1, n):
            my_step, _ = _side_steps(
                score_points[j - 1][1], score_points[j - 1][2],
                score_points[j][1], score_points[j][2], side,
            )
            if my_step <= 0:
                continue
            chosen = None
            for i in range(j - 1, -1, -1):
                if _crosses_halftime(score_points, i, j, halftime):
                    break
                if _gap_breaks(_side_score_times(score_points, i, j, side), max_gap):
                    break
                stats = _window_points(
                    score_points, i, j, side, min_delta, max_opp_consecutive, halftime,
                )
                if stats is not None:
                    chosen = i
            if chosen is None:
                continue
            if _first_peak(
                score_points, chosen, side, min_delta, max_opp_consecutive, halftime, max_gap,
            ) != j:
                continue
            stats = _window_points(
                score_points, chosen, j, side, min_delta, max_opp_consecutive, halftime,
            )
            if stats is None:
                continue
            dh, da, delta = stats
            first = _first_side_score_index(score_points, chosen, j, side)
            if first is None:
                continue
            raw_runs.append({
                'side': side,
                'home_pts': dh,
                'away_pts': da,
                'start': score_points[first][0],
                'end': score_points[j][0],
                'delta': delta,
                'events': [score_points[k][0] for k in range(first, j + 1)],
            })

    raw_runs.sort(key=lambda r: (-r['delta'], r['end'] - r['start'], r['start']))
    selected_runs = []
    for run in raw_runs:
        stamps = set(run['events'])
        if any(stamps & set(kept['events']) for kept in selected_runs):
            continue
        selected_runs.append(run)
    selected_runs.sort(key=lambda r: r['start'])
    for run in selected_runs:
        del run['events']
    return selected_runs


def period_clock_label(t_seconds, periods):
    for period in periods or []:
        if period['start'] <= t_seconds <= period['end']:
            rem = max(0, int(period['end'] - t_seconds))
            return f"{period['label']} {rem // 60:02d}:{rem % 60:02d}"
    return f"{int(t_seconds // 60):02d}:{int(t_seconds % 60):02d}"


def _clock_span(start, end, periods):
    start_str = period_clock_label(start, periods)
    end_str = period_clock_label(end, periods)
    start_parts = start_str.split(' ', 1)
    end_parts = end_str.split(' ', 1)
    if len(start_parts) == 2 and len(end_parts) == 2 and start_parts[0] == end_parts[0]:
        return f"{start_parts[0]} {start_parts[1]}–{end_parts[1]}"
    return f"{start_str}–{end_str}"


def format_run_label(run, periods):
    if run.get('side') == 'away':
        pts = f"{run['away_pts']}–{run['home_pts']}"
    else:
        pts = f"{run['home_pts']}–{run['away_pts']}"
    return f"{_clock_span(run['start'], run['end'], periods)}  {pts}"


def format_kill_label(kill, periods):
    return f"{_clock_span(kill['start'], kill['end'], periods)}  {kill['stops']} STOPS"


def _made_shot(value):
    return value == 1 or value is True


def _event_points(event_type, success):
    if not _made_shot(success):
        return 0
    if event_type == '3pt':
        return 3
    if event_type == 'freeThrow':
        return 1
    if event_type == '2pt':
        return 2
    return 0


def _elapsed_on_period(period_id, clock, periods):
    remaining = clock_to_seconds(clock)
    if remaining is None:
        return None
    for period in periods or []:
        if _same_id(period.get('id'), period_id):
            return period['start'] + max(0.0, float(period['seconds']) - remaining)
    return None


def possession_trips(df, periods):
    """Ended stats trips in frame order, with elapsed start and end."""
    annotated = annotate_possessions(df)
    if 'poss_id' not in getattr(annotated, 'columns', []):
        return []
    grouped = {}
    order = []
    for row in annotated.to_dict('records'):
        poss_id = row.get('poss_id')
        if poss_id is None or (isinstance(poss_id, float) and pd.isna(poss_id)):
            continue
        if poss_id not in grouped:
            grouped[poss_id] = []
            order.append(poss_id)
        grouped[poss_id].append(row)
    trips = []
    for poss_id in order:
        rows = grouped[poss_id]
        end_row = None
        for row in rows:
            if row.get('poss_end'):
                end_row = row
        if end_row is None:
            continue
        start_t = _elapsed_on_period(rows[0].get('periodId'), rows[0].get('clock'), periods)
        end_t = _elapsed_on_period(end_row.get('periodId'), end_row.get('clock'), periods)
        if start_t is None or end_t is None:
            continue
        points = sum(_event_points(row.get('eventType'), row.get('success')) for row in rows)
        trips.append({
            'offense': end_row.get('poss_team_id'),
            'points': points,
            'start': float(start_t),
            'end': float(max(start_t, end_t)),
        })
    return trips


def _close_kill_streak(streak, side, kills):
    if len(streak) < 3:
        return []
    kills.append({
        'side': side,
        'stops': len(streak),
        'start': float(streak[0]['start']),
        'end': float(streak[-1]['end']),
    })
    return []


def _split_kill_streak(streak, trip, halftime):
    """Halftime is the only hard cut. A trip that starts at the cut begins a new streak."""
    if not streak or halftime is None:
        return False
    try:
        cut = float(halftime)
        previous = float(streak[-1].get('start'))
        start = float(trip.get('start'))
        end = float(trip.get('end'))
    except (TypeError, ValueError):
        return False
    if previous < cut <= start:
        return True
    return start < cut <= end and previous < cut


def detect_kills(trips, home_team_id, away_team_id, halftime=None):
    """One kill is three or more consecutive opponent trips that score 0."""
    kills = []
    for side, offense_id in (('home', away_team_id), ('away', home_team_id)):
        if offense_id is None:
            continue
        streak = []
        for trip in trips or []:
            if not _same_id(trip.get('offense'), offense_id):
                continue
            if int(trip.get('points') or 0) > 0:
                streak = _close_kill_streak(streak, side, kills)
                continue
            if _split_kill_streak(streak, trip, halftime):
                streak = _close_kill_streak(streak, side, kills)
            streak.append(trip)
        _close_kill_streak(streak, side, kills)
    kills.sort(key=lambda kill: (kill['start'], 0 if kill['side'] == 'home' else 1))
    return kills


def live_playhead_t(payload):
    times = []
    skip = {GAME_END_DESC, '比賽結束'}
    for point in (payload or {}).get('margin') or []:
        if point.get('desc') in skip:
            continue
        if point.get('t') is not None:
            times.append(point['t'])
    for team in (payload or {}).get('teams') or []:
        for player in team.get('players') or []:
            for stint in player.get('stints') or []:
                times.append(stint.get('end') or 0)
    return max(times) if times else None


def player_on_court(player, t):
    if t is None:
        return False
    for stint in player.get('stints') or []:
        start = stint.get('start')
        end = stint.get('end')
        if start is None or end is None:
            continue
        if start - 1e-9 <= t <= end + 1e-9:
            return True
    return False


def visible_players(team, show_dnp=False):
    players = list((team or {}).get('players') or [])
    if show_dnp:
        return players
    return [player for player in players if not player.get('dnp')]


def walk_lineup(frame, starter_dict):
    """Copy ``frame`` and run the Game page substitution walk."""
    if frame is None:
        walked = pd.DataFrame()
    else:
        walked = frame.copy()
    process_lineup_pbp(walked, starter_dict or {})
    return walked


def team_on_court_seconds(payload, team_id):
    """Seconds ``build_rotation_payload`` gave ``team_id``. DNP rows are omitted."""
    if not payload or team_id is None:
        return 0.0
    for side in payload.get('teams') or []:
        if not _same_id(side.get('team_id'), team_id):
            continue
        total = 0.0
        for player in side.get('players') or []:
            if player.get('dnp'):
                continue
            total += float(player.get('seconds') or 0)
        return total
    return 0.0


def build_rotation_payload(
    pbp_df,
    starter_dict,
    id_table,
    home_team_id,
    away_team_id,
    roster=None,
    marks=True,
):
    id_table = id_table or {}
    starter_dict = starter_dict or {}
    roster = roster or []
    empty = {
        'periods': [],
        'buckets': [],
        'teams': [],
        'margin': [],
        'runs': [],
        'kills': [],
    }
    if pbp_df is None or getattr(pbp_df, 'empty', True):
        return empty
    if home_team_id is None or away_team_id is None:
        return empty

    df = pbp_df.copy()
    if 'periodId' not in df.columns or 'clock' not in df.columns:
        return empty

    period_ids = []
    for period_id in df['periodId'].dropna().tolist():
        if period_id not in period_ids:
            period_ids.append(period_id)

    periods = []
    cursor = 0.0
    for period_id in period_ids:
        clocks = df.loc[df['periodId'] == period_id, 'clock']
        seconds = _infer_period_seconds(clocks)
        native_period = int(period_id) if pd.notna(period_id) and str(period_id).replace('.', '', 1).isdigit() else period_id
        periods.append({
            'id': native_period,
            'label': period_label(native_period),
            'seconds': int(seconds),
            'start': float(cursor),
            'end': float(cursor + seconds),
        })
        cursor += seconds

    buckets = []
    for period in periods:
        minutes = max(1, int(period['seconds'] // 60))
        bucket_len = period['seconds'] / minutes
        for minute in range(minutes):
            start = period['start'] + minute * bucket_len
            buckets.append({
                'periodId': period['id'],
                'period_label': period['label'],
                'minute': minute,
                'label': period['label'],
                'start': start,
                'end': start + bucket_len,
            })

    team_ids = [team_id for team_id in (home_team_id, away_team_id) if team_id is not None]
    stints_by_player = {str(team_id): {} for team_id in team_ids}
    first_on_by_player = {str(team_id): {} for team_id in team_ids}
    seen_by_team = {str(team_id): set() for team_id in team_ids}

    for period in periods:
        period_rows = df[df['periodId'] == period['id']]
        events = []
        for _, row in period_rows.iterrows():
            remaining = clock_to_seconds(row.get('clock'))
            if remaining is None:
                continue
            elapsed = period['start'] + max(0.0, period['seconds'] - remaining)
            lineups = {}
            for team_id in team_ids:
                column = _find_column(df, team_id)
                lineups[str(team_id)] = _as_player_list(row[column] if column else None)
            events.append((elapsed, lineups))
        if not events:
            continue
        events.sort(key=lambda item: item[0])
        if events[0][0] > period['start']:
            events.insert(0, (period['start'], events[0][1]))
        if events[-1][0] < period['end']:
            events.append((period['end'], events[-1][1]))

        for index in range(len(events) - 1):
            start_t, lineups = events[index]
            end_t = events[index + 1][0]
            if end_t <= start_t:
                continue
            for team_id in team_ids:
                team_key = str(team_id)
                for person_id in lineups.get(team_key, []):
                    seen_by_team[team_key].add(person_id)
                    if person_id not in first_on_by_player[team_key]:
                        first_on_by_player[team_key][person_id] = start_t
                    if person_id not in stints_by_player[team_key]:
                        stints_by_player[team_key][person_id] = []

                    stints = stints_by_player[team_key][person_id]
                    if stints and abs(stints[-1]['end'] - start_t) < 1e-3:
                        stints[-1]['end'] = end_t
                    else:
                        stints.append({'start': start_t, 'end': end_t})

    margin = [{'t': 0.0, 'margin': 0, 'home_score': 0, 'away_score': 0, 'desc': GAME_START_DESC, 'clock_label': '1Q 12:00' if periods else '0:00'}]
    score_events = [(0.0, 0, 0)]
    curr_h, curr_a = 0, 0

    def _clean_shot_type(event_type, sub_type):
        s = sub_type if isinstance(sub_type, str) and sub_type.strip() else event_type
        if not isinstance(s, str):
            s = ''
        s = s.strip().lower()
        if '3' in s:
            return '3PT'
        if 'free' in s or 'ft' in s:
            return 'FT'
        return '2PT'

    for period in periods:
        period_rows = df[df['periodId'] == period['id']]
        for _, row in period_rows.iterrows():
            scores = _parse_scores(row.get('scores'))
            if not scores:
                continue
            remaining = clock_to_seconds(row.get('clock'))
            if remaining is None:
                continue
            elapsed = period['start'] + max(0.0, period['seconds'] - remaining)
            h_val = curr_h
            a_val = curr_a
            for key, value in scores.items():
                try:
                    points = int(value)
                except (TypeError, ValueError):
                    continue
                if _same_id(key, home_team_id):
                    h_val = points
                elif _same_id(key, away_team_id):
                    a_val = points

            if h_val == curr_h and a_val == curr_a:
                continue

            curr_h, curr_a = h_val, a_val

            pid = row.get('personId')
            player_name = person_name(id_table, pid)
            if not player_name or player_name == str(pid).strip():
                fallback = row.get('Player') or ''
                if str(fallback).strip():
                    player_name = player_label(str(fallback).strip())
                elif player_name == '':
                    player_name = ''
            shot_type = _clean_shot_type(row.get('eventType'), row.get('subType'))
            desc = f"{player_name} {shot_type}".strip() if player_name else shot_type

            rem_sec = max(0, int(remaining))
            clock_label = f"{period['label']} {rem_sec // 60:02d}:{rem_sec % 60:02d}"

            point = {
                't': elapsed,
                'margin': curr_h - curr_a,
                'home_score': curr_h,
                'away_score': curr_a,
                'desc': desc,
                'clock_label': clock_label,
            }
            if margin and margin[-1]['t'] == point['t']:
                margin[-1] = point
                score_events[-1] = (elapsed, curr_h, curr_a)
            else:
                margin.append(point)
                score_events.append((elapsed, curr_h, curr_a))

    game_end = periods[-1]['end'] if periods else 0.0
    if margin and margin[-1]['t'] < game_end:
        last_m = margin[-1]
        margin.append({
            't': game_end,
            'margin': last_m['margin'],
            'home_score': last_m['home_score'],
            'away_score': last_m['away_score'],
            'desc': GAME_END_DESC,
            'clock_label': f"{periods[-1]['label']} 00:00" if periods else '0:00',
        })
        score_events.append((game_end, curr_h, curr_a))

    halftime = next((period['end'] for period in periods if period.get('id') == 2), None)
    if marks:
        runs = detect_runs(score_events, min_delta=8, halftime=halftime)
        kills = detect_kills(
            possession_trips(df, periods), home_team_id, away_team_id, halftime=halftime,
        )
    else:
        runs = []
        kills = []

    def get_margin_at(t):
        if not margin:
            return 0
        val = margin[0]['margin']
        for p in margin:
            if p['t'] <= t:
                val = p['margin']
            else:
                break
        return val

    roster_by_id = {str(item.get('personId')): item for item in roster if item.get('personId') is not None}
    teams = []
    for side, team_id in (('home', home_team_id), ('away', away_team_id)):
        if team_id is None:
            continue
        team_key = str(team_id)
        person_ids = set(seen_by_team.get(team_key, set()))
        for item in roster:
            if _same_id(item.get('entityId'), team_id) and item.get('personId') is not None:
                person_ids.add(item['personId'])
        starters = set(starter_dict.get(team_id, []) or [])
        if team_id not in starter_dict:
            for key, value in starter_dict.items():
                if _same_id(key, team_id):
                    starters = set(value or [])
                    break

        players = []
        for person_id in person_ids:
            stints_raw = stints_by_player.get(team_key, {}).get(person_id, [])
            stints = []
            for s in stints_raw:
                m_start = get_margin_at(s['start'])
                m_end = get_margin_at(s['end'])
                pm = (m_end - m_start) if side == 'home' else -(m_end - m_start)
                stints.append({
                    'start': s['start'],
                    'end': s['end'],
                    'pm': pm,
                })
            seconds = sum(s['end'] - s['start'] for s in stints)
            first_on = first_on_by_player.get(team_key, {}).get(person_id)
            roster_row = roster_by_id.get(str(person_id), {})
            is_starter = person_id in starters or bool(roster_row.get('starter'))
            players.append({
                'person_id': person_id,
                'label': _shirt_label(person_id, id_table, roster_by_id),
                'starter': is_starter,
                'dnp': seconds <= 0 or first_on is None,
                'seconds': seconds,
                'first_on': first_on,
                'shirt_number': roster_row.get('shirtNumber'),
                'stints': stints,
            })

        players.sort(key=lambda player: (
            1 if player['dnp'] else 0,
            0 if player['starter'] else 1,
            player['first_on'] if player['first_on'] is not None else 0,
            _shirt_sort_key(player.get('shirt_number')),
            player['label'],
        ))
        teams.append({
            'team_id': team_id,
            'team_name': id_table.get(team_id, team_id),
            'side': side,
            'players': players,
        })

    return {
        'periods': periods,
        'buckets': buckets,
        'teams': teams,
        'margin': margin,
        'runs': runs,
        'kills': kills,
    }


def build_rotation_figure(payload, playhead=None, show_dnp=False, uirevision=None):
    return _build_rotation_figure_impl(
        payload,
        playhead=playhead,
        show_dnp=show_dnp,
        uirevision=uirevision,
        visible_players_fn=visible_players,
        player_on_court_fn=player_on_court,
        format_kill_label_fn=format_kill_label,
    )
