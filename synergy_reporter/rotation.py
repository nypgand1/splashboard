# -*- coding: utf-8 -*-
import json
import math
import re

import pandas as pd

CLOCK_RE = re.compile(r'PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', re.IGNORECASE)


def clock_to_seconds(clock):
    if clock is None or (isinstance(clock, float) and pd.isna(clock)):
        return None
    if isinstance(clock, (int, float)) and not isinstance(clock, bool):
        return float(clock)
    text = str(clock).strip()
    if not text:
        return None
    match = CLOCK_RE.search(text)
    if not match:
        try:
            parsed = pd.to_datetime(text, format='PT%MM%SS')
        except (ValueError, TypeError):
            return None
        return float(parsed.minute * 60 + parsed.second)
    minutes = int(match.group(1) or 0)
    seconds = float(match.group(2) or 0)
    return minutes * 60 + seconds


def margin_tick_span(values, step=5):
    abs_max = max((abs(value) for value in values), default=0)
    return max(step, int(math.ceil(abs_max / float(step)) * step))


SCORE_TEXT_DARK = '#1e293b'
SCORE_TEXT_LIGHT = '#ffffff'
SCORE_TEXT_SIZE = 14
SCORE_TEXT_LUMINANCE_THRESHOLD = 0.45
_RGB_RE = re.compile(r'rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)')


def _srgb_to_linear(channel):
    value = channel / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _parse_rgb(color):
    if not color:
        return (30, 41, 59)
    text = str(color).strip()
    match = _RGB_RE.match(text)
    if match:
        return tuple(float(match.group(i)) for i in (1, 2, 3))
    if text.startswith('#') and len(text) == 7:
        return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))
    return (30, 41, 59)


def relative_luminance(color):
    red, green, blue = _parse_rgb(color)
    return (
        0.2126 * _srgb_to_linear(red)
        + 0.7152 * _srgb_to_linear(green)
        + 0.0722 * _srgb_to_linear(blue)
    )


def contrast_text_color(fill_color, threshold=SCORE_TEXT_LUMINANCE_THRESHOLD):
    if relative_luminance(fill_color) < threshold:
        return SCORE_TEXT_LIGHT
    return SCORE_TEXT_DARK


def score_text_colors(score_z, zmax, colorscale='PuBu'):
    from plotly.colors import sample_colorscale

    scale_max = max(1.0, float(zmax or 0))
    colors = []
    for row in score_z:
        row_colors = []
        for value in row:
            if not value:
                row_colors.append(SCORE_TEXT_DARK)
                continue
            t = min(1.0, max(0.0, float(value) / scale_max))
            sampled = sample_colorscale(colorscale, [t])[0]
            row_colors.append(contrast_text_color(sampled))
        colors.append(row_colors)
    return colors


def period_label(period_id):
    try:
        period = int(period_id)
    except (TypeError, ValueError):
        return str(period_id)
    if period <= 4:
        return f'{period}Q'
    if period >= 11:
        ot_n = period - 10
    else:
        ot_n = period - 4
    return 'OT' if ot_n == 1 else f'{ot_n}OT'


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


def _same_id(left, right):
    if left is None or right is None:
        return False
    return str(left) == str(right)


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


def _shirt_label(person_id, id_table, roster_by_id):
    name = id_table.get(person_id, person_id)
    shirt = (roster_by_id.get(str(person_id)) or {}).get('shirtNumber')
    if shirt in (None, ''):
        return str(name)
    return f'#{shirt} {name}'


def _shirt_sort_key(shirt):
    if shirt in (None, ''):
        return (1, 10 ** 9, '')
    text = str(shirt).strip()
    try:
        return (0, int(text), text)
    except ValueError:
        return (0, 10 ** 9, text)


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


def _window_stats(score_points, i, j, side, max_opp_consecutive):
    _, h0, a0 = score_points[i]
    opp_consecutive = 0
    for k in range(i + 1, j + 1):
        _, h_curr, a_curr = score_points[k]
        _, h_prev, a_prev = score_points[k - 1]
        my_step, opp_step = _side_steps(h_prev, a_prev, h_curr, a_curr, side)
        if opp_step > 0:
            opp_consecutive += opp_step
        if my_step > 0:
            opp_consecutive = 0
        if opp_consecutive > max_opp_consecutive:
            return None
    _, h_end, a_end = score_points[j]
    dh = h_end - h0
    da = a_end - a0
    my_tot = dh if side == 'home' else da
    opp_tot = da if side == 'home' else dh
    return {
        'dh': dh,
        'da': da,
        'my_tot': my_tot,
        'opp_tot': opp_tot,
        'delta': my_tot - opp_tot,
    }


def _qualifies_run(stats, min_delta):
    return (
        stats is not None
        and stats['delta'] >= min_delta
        and stats['my_tot'] >= min_delta
        and stats['opp_tot'] <= 4
    )


def _first_side_score_index(score_points, i, j, side):
    for k in range(i + 1, j + 1):
        _, h_curr, a_curr = score_points[k]
        _, h_prev, a_prev = score_points[k - 1]
        my_step, _ = _side_steps(h_prev, a_prev, h_curr, a_curr, side)
        if my_step > 0:
            return k
    return None


def detect_runs(events_with_scores, min_delta=8, max_opp_consecutive=3):
    """
    Detect basketball momentum runs:
    - Accumulated net margin delta >= min_delta (e.g. 8 pts)
    - Wave breaks when opponent scores > max_opp_consecutive points (>= 4 pts) without response
    - Endpoint is the max-delta instant, not the last still-legal tick
    - Start trims to the first scorer of the tightest qualifying suffix
    events_with_scores: list of (elapsed, home_pts, away_pts)
    returns: list of {'side': 'home'|'away', 'home_pts': int, 'away_pts': int, 'start': float, 'end': float, 'delta': int}
    """
    if not events_with_scores or len(events_with_scores) < 2:
        return []

    score_points = [events_with_scores[0]]
    for pt in events_with_scores[1:]:
        if pt[1] != score_points[-1][1] or pt[2] != score_points[-1][2]:
            score_points.append(pt)

    n = len(score_points)
    raw_runs = []

    for side in ('home', 'away'):
        for i in range(n):
            _, h_start, a_start = score_points[i]
            opp_consecutive = 0
            best_j = None
            best_delta = -1
            best_my = -1
            best_pts = (0, 0)

            for j in range(i + 1, n):
                t_curr, h_curr, a_curr = score_points[j]
                _, h_prev, a_prev = score_points[j - 1]
                my_step, opp_step = _side_steps(h_prev, a_prev, h_curr, a_curr, side)
                if opp_step > 0:
                    opp_consecutive += opp_step
                if my_step > 0:
                    opp_consecutive = 0
                if opp_consecutive > max_opp_consecutive:
                    break

                dh = h_curr - h_start
                da = a_curr - a_start
                my_tot = dh if side == 'home' else da
                opp_tot = da if side == 'home' else dh
                delta = my_tot - opp_tot
                if delta >= min_delta and my_tot >= min_delta and opp_tot <= 4:
                    if (
                        best_j is None
                        or delta > best_delta
                        or (delta == best_delta and my_tot > best_my)
                    ):
                        best_j = j
                        best_delta = delta
                        best_my = my_tot
                        best_pts = (dh, da)

            if best_j is None:
                continue

            i_tight = i
            tight_pts = best_pts
            tight_delta = best_delta
            for i2 in range(i + 1, best_j):
                stats = _window_stats(
                    score_points, i2, best_j, side, max_opp_consecutive,
                )
                if _qualifies_run(stats, min_delta):
                    i_tight = i2
                    tight_pts = (stats['dh'], stats['da'])
                    tight_delta = stats['delta']

            first = _first_side_score_index(score_points, i_tight, best_j, side)
            t_start = (
                score_points[first][0]
                if first is not None
                else score_points[i_tight][0]
            )
            raw_runs.append({
                'side': side,
                'home_pts': tight_pts[0],
                'away_pts': tight_pts[1],
                'start': t_start,
                'end': score_points[best_j][0],
                'delta': tight_delta,
            })

    if not raw_runs:
        return []

    raw_runs.sort(key=lambda r: (-r['delta'], -(r['end'] - r['start'])))
    selected_runs = []
    for r in raw_runs:
        overlap = False
        for s in selected_runs:
            intersect = max(0.0, min(r['end'], s['end']) - max(r['start'], s['start']))
            r_len = max(1.0, r['end'] - r['start'])
            if intersect / r_len > 0.4:
                overlap = True
                break
        if not overlap:
            selected_runs.append(r)

    selected_runs.sort(key=lambda r: r['start'])
    return selected_runs


def period_clock_label(t_seconds, periods):
    for period in periods or []:
        if period['start'] <= t_seconds <= period['end']:
            rem = max(0, int(period['end'] - t_seconds))
            return f"{period['label']} {rem // 60:02d}:{rem % 60:02d}"
    return f"{int(t_seconds // 60):02d}:{int(t_seconds % 60):02d}"


def format_run_label(run, periods):
    start_str = period_clock_label(run['start'], periods)
    end_str = period_clock_label(run['end'], periods)
    if run.get('side') == 'away':
        pts = f"{run['away_pts']}–{run['home_pts']}"
    else:
        pts = f"{run['home_pts']}–{run['away_pts']}"
    start_parts = start_str.split(' ', 1)
    end_parts = end_str.split(' ', 1)
    if len(start_parts) == 2 and len(end_parts) == 2 and start_parts[0] == end_parts[0]:
        span = f"{start_parts[0]} {start_parts[1]}–{end_parts[1]}"
    else:
        span = f"{start_str}–{end_str}"
    return f"{span}  {pts}"


def clamp_time_window(x0, x1, game_end, width):
    game_end = float(game_end or 0)
    if game_end <= 0:
        return 0.0, 0.0
    width = min(max(float(width), 0.0), game_end)
    if width <= 0:
        return 0.0, game_end
    center = (float(x0) + float(x1)) / 2.0
    start = center - width / 2.0
    if start < 0:
        start = 0.0
    if start + width > game_end:
        start = game_end - width
    if start < 0:
        start = 0.0
    return start, start + width


def period_for_window(x0, x1, periods, current=None):
    window = max(1e-6, float(x1) - float(x0))
    best_id = None
    best_overlap = -1.0
    for period in periods or []:
        overlap = max(0.0, min(float(x1), period['end']) - max(float(x0), period['start']))
        if overlap > best_overlap:
            best_overlap = overlap
            best_id = period.get('id')
    if best_id is None:
        return current
    if best_overlap / window > 0.5:
        return str(best_id)
    if current is not None:
        return str(current)
    return str(best_id)


def parse_xaxis_range(relayout):
    if not isinstance(relayout, dict):
        return None
    if 'xaxis.range[0]' in relayout and 'xaxis.range[1]' in relayout:
        return float(relayout['xaxis.range[0]']), float(relayout['xaxis.range[1]'])
    range_val = relayout.get('xaxis.range')
    if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
        return float(range_val[0]), float(range_val[1])
    return None


def apply_camera_relayout(relayout, view, periods):
    parsed = parse_xaxis_range(relayout)
    if parsed is None:
        return None
    if not periods:
        return None
    game_end = float(periods[-1]['end'])
    view = dict(view or {})
    slice_width = view.get('slice_width')
    expected = float(slice_width) if slice_width else game_end
    x0, x1 = clamp_time_window(parsed[0], parsed[1], game_end, expected)
    if expected >= game_end - 1e-6:
        period_value = 'all'
        new_x0, new_x1 = None, None
        new_slice = None
    else:
        period_value = period_for_window(x0, x1, periods, view.get('period'))
        new_x0, new_x1 = x0, x1
        new_slice = expected
    prev_x0, prev_x1 = view.get('x0'), view.get('x1')
    if new_x0 is None:
        camera_same = (
            prev_x0 is None
            and prev_x1 is None
            and view.get('period') in (None, 'all')
            and abs(parsed[0] - 0.0) < 0.5
            and abs(parsed[1] - game_end) < 0.5
        )
    else:
        camera_same = (
            prev_x0 is not None
            and prev_x1 is not None
            and abs(prev_x0 - new_x0) < 0.5
            and abs(prev_x1 - new_x1) < 0.5
            and str(view.get('period')) == str(period_value)
        )
    if camera_same:
        return None
    snapped = (
        abs((parsed[1] - parsed[0]) - (x1 - x0)) > 0.5
        or abs(parsed[0] - x0) > 0.5
        or abs(parsed[1] - x1) > 0.5
    )
    if snapped:
        view['axis_rev'] = int(view.get('axis_rev') or 0) + 1
    view['period'] = period_value
    view['x0'] = new_x0
    view['x1'] = new_x1
    view['slice_width'] = new_slice
    return view


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
    visible = [player for player in players if not player.get('dnp')]
    return visible



def build_rotation_payload(
    pbp_df,
    starter_dict,
    id_table,
    home_team_id,
    away_team_id,
    roster=None,
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
    }
    if pbp_df is None or getattr(pbp_df, 'empty', True):
        return empty
    if home_team_id is None or away_team_id is None:
        team_ids = list(starter_dict.keys())
        if home_team_id is None and team_ids:
            home_team_id = team_ids[0]
        if away_team_id is None and len(team_ids) > 1:
            away_team_id = team_ids[1]
    if home_team_id is None:
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

    # Extract continuous stints
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
                    # Merge contiguous stints if matching
                    if stints and abs(stints[-1]['end'] - start_t) < 1e-3:
                        stints[-1]['end'] = end_t
                    else:
                        stints.append({'start': start_t, 'end': end_t})

    # Extract score margin and score events with accurate scorer and shot type
    margin = [{'t': 0.0, 'margin': 0, 'home_score': 0, 'away_score': 0, 'desc': GAME_START_DESC, 'clock_label': '1Q 12:00' if periods else '0:00'}]
    score_events = [(0.0, 0, 0)]
    curr_h, curr_a = 0, 0
    
    def _clean_shot_type(event_type, sub_type):
        s = (sub_type or event_type or '').lower()
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
            
            # Only record if the score actually changed!
            if h_val == curr_h and a_val == curr_a:
                continue
                
            curr_h, curr_a = h_val, a_val
            
            # Scorer / event detail
            pid = row.get('personId')
            player_name = str(id_table.get(pid, row.get('Player') or ''))
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

    runs = detect_runs(score_events, min_delta=8)


    # Function to query net score margin diff between two timestamps for stint +/-
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
                # Home team +/- is m_end - m_start; Away team +/- is -(m_end - m_start)
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
    }


def build_rotation_figure(payload, playhead=None, x_range=None, show_dnp=False, uirevision=None):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    teams = (payload or {}).get('teams') or []
    periods = (payload or {}).get('periods') or []
    margin = (payload or {}).get('margin') or []
    runs = (payload or {}).get('runs') or []
    home = next((team for team in teams if team.get('side') == 'home'), teams[0] if teams else None)
    away = next((team for team in teams if team.get('side') == 'away'), teams[1] if len(teams) > 1 else None)

    home_players = visible_players(home, show_dnp) or [{'label': '—', 'stints': []}]
    away_players = visible_players(away, show_dnp) or [{'label': '—', 'stints': []}]
    home_n = len(home_players) or 1
    away_n = len(away_players) or 1

    h_weight = max(0.25, min(0.45, (home_n * 22) / (home_n * 22 + away_n * 22 + 180)))
    a_weight = max(0.25, min(0.45, (away_n * 22) / (home_n * 22 + away_n * 22 + 180)))
    m_weight = max(0.18, 1.0 - h_weight - a_weight)

    total_height = max(520, home_n * 22 + away_n * 22 + 200)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[h_weight, m_weight, a_weight],
        vertical_spacing=0.06,
        subplot_titles=(
            (home or {}).get('team_name') or 'Home',
            '',
            (away or {}).get('team_name') or 'Away',
        ),
    )


    game_end = periods[-1]['end'] if periods else 1

    home_color = '#0077b6'
    away_color = '#94a3b8'
    margin_line = '#0284c7'
    home_fill = 'rgba(0, 119, 182, 0.20)'
    away_fill = 'rgba(148, 163, 184, 0.25)'

    def format_clock_str(t_seconds):
        for period in periods:
            if period['start'] <= t_seconds <= period['end']:
                rem = max(0, int(period['end'] - t_seconds))
                return f"{period['label']} {rem // 60:02d}:{rem % 60:02d}"
        m = int(t_seconds // 60)
        sec = int(t_seconds % 60)
        return f"{m:02d}:{sec:02d}"

    def format_duration(s):
        m = int(s // 60)
        sec = int(s % 60)
        return f"{m:02d}:{sec:02d}"

    def axis_label(player):
        base = player.get('label') or ''
        if playhead is None:
            return base
        if player_on_court(player, playhead):
            return f'● {base}'
        return f'  {base}'

    def add_gantt(team, row, bar_color, players):
        players_rev = list(reversed(players))
        y_cats = [axis_label(p) for p in players_rev]
        fig.add_trace(
            go.Scatter(
                x=[0] * len(y_cats),
                y=y_cats,
                mode='markers',
                marker=dict(opacity=0),
                hoverinfo='skip',
                showlegend=False,
            ),
            row=row,
            col=1,
        )

        for player in players_rev:
            p_label = player.get('label') or ''
            y_label = axis_label(player)
            on_floor = playhead is None or player_on_court(player, playhead)
            bar_opacity = 1.0 if on_floor else 0.32
            stints = player.get('stints') or []
            for stint in stints:
                dur = stint['end'] - stint['start']
                if dur <= 0:
                    continue
                c_start = format_clock_str(stint['start'])
                c_end = format_clock_str(stint['end'])
                dur_str = format_duration(dur)
                pm = stint.get('pm', 0)
                pm_str = f"+{pm}" if pm > 0 else f"{pm}"
                hover_text = (
                    f"<b>{p_label} ({pm_str})</b><br>"
                    f"{c_start} – {c_end} ({dur_str})"
                )
                fig.add_trace(
                    go.Bar(
                        x=[dur],
                        y=[y_label],
                        base=[stint['start']],
                        orientation='h',
                        marker=dict(
                            color=bar_color,
                            opacity=bar_opacity,
                            line=dict(color='rgba(255,255,255,0.6)', width=1),
                        ),
                        customdata=[[stint['start'], stint['end']]],
                        hovertext=hover_text,
                        hoverinfo='text',
                        showlegend=False,
                    ),
                    row=row,
                    col=1,
                )
        fig.update_yaxes(ticksuffix='  ', row=row, col=1)

    add_gantt(home, 1, home_color, home_players)

    # 2. Score Margin Step-line with Dual-Color Fill & Rich Hover Tooltips
    margin_x = [point['t'] for point in margin] or [0]
    margin_y = [point['margin'] for point in margin] or [0]
    home_lead_y = [max(0, y) for y in margin_y]
    away_lead_y = [min(0, y) for y in margin_y]

    home_name = (home or {}).get('team_name') or 'Home'
    away_name = (away or {}).get('team_name') or 'Away'

    hover_texts = []
    for point in margin:
        m = point.get('margin', 0)
        h_score = point.get('home_score', 0)
        a_score = point.get('away_score', 0)
        clock_lbl = point.get('clock_label') or format_clock_str(point['t'])
        desc = point.get('desc', '')
        if m > 0:
            diff_str = f"(+{m})"
        elif m < 0:
            diff_str = f"({m})"
        else:
            diff_str = "(0)"
        
        lines = [
            f"<b>{clock_lbl}</b>",
            f"{home_name} {h_score} - {a_score} {away_name} {diff_str}",
        ]
        if desc:
            lines.append(f"{desc}")
        hover_texts.append("<br>".join(lines))

    span = margin_tick_span(margin_y, step=5)

    # Home Lead Positive Fill (Blue)
    fig.add_trace(
        go.Scatter(
            x=margin_x,
            y=home_lead_y,
            mode='lines',
            line=dict(color='rgba(0,0,0,0)', width=0, shape='hv'),
            fill='tozeroy',
            fillcolor=home_fill,
            hoverinfo='skip',
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Away Lead Negative Fill (Gray)
    fig.add_trace(
        go.Scatter(
            x=margin_x,
            y=away_lead_y,
            mode='lines',
            line=dict(color='rgba(0,0,0,0)', width=0, shape='hv'),
            fill='tozeroy',
            fillcolor=away_fill,
            hoverinfo='skip',
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Margin Main Step-line Trace with Hover
    fig.add_trace(
        go.Scatter(
            x=margin_x,
            y=margin_y,
            mode='lines',
            line=dict(color=margin_line, width=2.0, shape='hv'),
            hovertext=hover_texts,
            hoverinfo='text',
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    tickvals = list(range(-span, span + 1, 5))
    fig.update_yaxes(
        range=[-span, span],
        tickmode='array',
        tickvals=tickvals,
        ticktext=[str(value) for value in tickvals],
        zeroline=True,
        zerolinecolor='#475569',
        zerolinewidth=1.5,
        showgrid=True,
        gridcolor='#e2e8f0',
        tickfont=dict(size=10),
        ticksuffix='  ',
        row=2,
        col=1,
    )


    add_gantt(away, 3, away_color, away_players)

    view_start, view_end = 0, game_end
    if x_range and len(x_range) == 2 and x_range[0] is not None and x_range[1] is not None:
        view_start, view_end = x_range
    tickvals = [period['start'] + period['seconds'] / 2 for period in periods]
    ticktext = [period['label'] for period in periods]

    for axis_row in (1, 2, 3):
        fig.update_xaxes(
            range=[view_start, view_end],
            minallowed=0,
            maxallowed=game_end,
            tickvals=tickvals,
            ticktext=ticktext if axis_row == 3 else [],
            showgrid=False,
            row=axis_row,
            col=1,
        )
        fig.update_yaxes(
            fixedrange=True,
            showgrid=(axis_row == 2),
            row=axis_row,
            col=1,
        )

    for period in periods[1:]:
        fig.add_vline(
            x=period['start'],
            line_width=1,
            line_color='#94a3b8',
            line_dash='solid',
        )
    if playhead is not None:
        fig.add_vline(
            x=playhead,
            line_width=2,
            line_color='#0077b6',
            line_dash='solid',
        )

    # Add full-height Run bands (vrect) across the whole figure and score annotations
    for run in runs:
        is_home = run['side'] == 'home'
        fill = 'rgba(0, 119, 182, 0.15)' if is_home else 'rgba(148, 163, 184, 0.20)'
        text_color = '#0077b6' if is_home else '#475569'
        fig.add_vrect(
            x0=run['start'],
            x1=run['end'],
            fillcolor=fill,
            opacity=1.0,
            layer='below',
            line_width=0,
        )
        
        # Add bold text annotation: top for home runs, bottom for away runs
        x_center = (run['start'] + run['end']) / 2
        pts_label = f"{run['home_pts']}-{run['away_pts']}" if is_home else f"{run['away_pts']}-{run['home_pts']}"
        y_pos = span if is_home else -span
        y_anchor = 'bottom' if is_home else 'top'
        y_shift = 2 if is_home else -2
        
        fig.add_annotation(
            x=x_center,
            y=y_pos,
            text=f"<b>{pts_label}</b>",
            showarrow=False,
            font=dict(size=11, color=text_color),
            yanchor=y_anchor,
            yshift=y_shift,
            xref='x2',
            yref='y2',
        )


    fig.update_layout(
        height=total_height,
        autosize=True,
        dragmode='pan',
        barmode='overlay',
        margin=dict(l=112, r=24, t=40, b=48),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#334155', size=12),
        hovermode='closest',
        uirevision=uirevision if uirevision is not None else f'{view_end - view_start:.3f}',
    )
    fig.update_annotations(font=dict(size=14, color='#1e293b'))
    return fig

