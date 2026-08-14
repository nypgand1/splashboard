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
        'scoring': {'home': [], 'away': []},
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
    seconds_by_player = {str(team_id): {} for team_id in team_ids}
    cells_by_player = {str(team_id): {} for team_id in team_ids}
    first_on_by_player = {str(team_id): {} for team_id in team_ids}
    seen_by_team = {str(team_id): set() for team_id in team_ids}
    scoring = {str(team_id): [0] * len(buckets) for team_id in team_ids}

    def ensure_player(team_id, person_id):
        team_key = str(team_id)
        person_key = person_id
        seen_by_team[team_key].add(person_key)
        if person_key not in cells_by_player[team_key]:
            cells_by_player[team_key][person_key] = [0.0] * len(buckets)
            seconds_by_player[team_key][person_key] = 0.0

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
            events.append((elapsed, lineups, row))
        if not events:
            continue
        events.sort(key=lambda item: item[0])
        if events[0][0] > period['start']:
            events.insert(0, (period['start'], events[0][1], None))
        if events[-1][0] < period['end']:
            events.append((period['end'], events[-1][1], None))

        for index in range(len(events) - 1):
            start_t, lineups, _row = events[index]
            end_t = events[index + 1][0]
            for team_id in team_ids:
                for person_id in lineups.get(str(team_id), []):
                    ensure_player(team_id, person_id)
                    team_key = str(team_id)
                    if person_id not in first_on_by_player[team_key]:
                        first_on_by_player[team_key][person_id] = start_t
                    seconds_by_player[team_key][person_id] += _add_overlap(
                        cells_by_player[team_key][person_id],
                        start_t,
                        end_t,
                        buckets,
                    )

        for elapsed, _lineups, row in events:
            points = _made_points(row)
            if not points or row is None:
                continue
            bucket_i = _bucket_index(elapsed, buckets)
            if bucket_i is None:
                continue
            entity = row.get('entityId')
            for team_id in team_ids:
                if _same_id(entity, team_id):
                    scoring[str(team_id)][bucket_i] += points
                    break

    margin = [{'t': 0.0, 'margin': 0}]
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
            home_score = 0
            away_score = 0
            for key, value in scores.items():
                try:
                    points = int(value)
                except (TypeError, ValueError):
                    continue
                if _same_id(key, home_team_id):
                    home_score = points
                elif _same_id(key, away_team_id):
                    away_score = points
            point = {'t': elapsed, 'margin': home_score - away_score}
            if margin and margin[-1]['t'] == point['t']:
                margin[-1] = point
            else:
                margin.append(point)
    game_end = periods[-1]['end'] if periods else 0.0
    if margin and margin[-1]['t'] < game_end:
        margin.append({'t': game_end, 'margin': margin[-1]['margin']})

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
            raw_cells = cells_by_player.get(team_key, {}).get(person_id, [0.0] * len(buckets))
            cells = []
            for value, bucket in zip(raw_cells, buckets):
                length = bucket['end'] - bucket['start']
                if not value:
                    cells.append(None)
                else:
                    cells.append(round(value / length, 4) if length else None)
            seconds = seconds_by_player.get(team_key, {}).get(person_id, 0.0)
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
                'cells': cells,
            })
        players.sort(key=lambda player: (
            1 if player['dnp'] else 0,
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

    def _score_row(team_id):
        raw = scoring.get(str(team_id), [0] * len(buckets))
        return [points if points else None for points in raw]

    return {
        'periods': periods,
        'buckets': buckets,
        'teams': teams,
        'margin': margin,
        'scoring': {
            'home': _score_row(home_team_id),
            'away': _score_row(away_team_id),
        },
    }


def build_rotation_figure(payload):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    teams = (payload or {}).get('teams') or []
    buckets = (payload or {}).get('buckets') or []
    periods = (payload or {}).get('periods') or []
    margin = (payload or {}).get('margin') or []
    scoring = (payload or {}).get('scoring') or {}
    home = next((team for team in teams if team.get('side') == 'home'), teams[0] if teams else None)
    away = next((team for team in teams if team.get('side') == 'away'), teams[1] if len(teams) > 1 else None)

    home_n = len(home['players']) if home else 1
    away_n = len(away['players']) if away else 1
    height = max(620, 110 + 26 * (home_n + away_n) + 230)
    width = 1220
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.34, 0.20, 0.10, 0.36],
        vertical_spacing=0.05,
        subplot_titles=(
            (home or {}).get('team_name') or '',
            '',
            '',
            (away or {}).get('team_name') or '',
        ),
    )

    x_centers = [(bucket['start'] + bucket['end']) / 2 for bucket in buckets]
    hover_x = []
    for bucket in buckets:
        period = next((item for item in periods if item['id'] == bucket['periodId']), None)
        period_seconds = period['seconds'] if period else 600
        start_remain = period_seconds - (bucket['start'] - (period['start'] if period else 0))
        end_remain = period_seconds - (bucket['end'] - (period['start'] if period else 0))
        hover_x.append(
            f"{bucket['period_label']} {int(start_remain) // 60}:{int(start_remain) % 60:02d}"
            f"–{int(end_remain) // 60}:{int(end_remain) % 60:02d}"
        )

    # ColorBrewer PuBu — same scale as the old seaborn generator.
    colorscale = 'PuBu'
    margin_line = 'rgb(4,90,141)'
    margin_fill = 'rgba(116,169,207,0.35)'

    def add_heatmap(team, row, show_scale):
        players = list((team or {}).get('players') or [{'label': '—', 'cells': [None] * len(buckets)}])
        players = list(reversed(players))
        z = [player.get('cells') or [None] * len(buckets) for player in players]
        y = [player.get('label') or '' for player in players]
        custom = [hover_x for _ in players]
        fig.add_trace(
            go.Heatmap(
                z=z,
                x=x_centers,
                y=y,
                zmin=0,
                zmax=1,
                colorscale=colorscale,
                xgap=2,
                ygap=2,
                hoverongaps=False,
                colorbar=dict(
                    title=dict(text='Play Time %', side='bottom'),
                    tickformat='.0%',
                    len=0.32,
                    y=-0.08,
                    yanchor='top',
                    x=0.5,
                    xanchor='center',
                    orientation='h',
                    thickness=10,
                    outlinewidth=0,
                ) if show_scale else None,
                showscale=show_scale,
                customdata=custom,
                hovertemplate='%{y}<br>%{customdata}<br>Play Time: %{z:.0%}<extra></extra>',
            ),
            row=row,
            col=1,
        )
        fig.update_yaxes(ticksuffix='  ', row=row, col=1)

    add_heatmap(home, 1, False)
    add_heatmap(away, 4, True)

    margin_x = [point['t'] for point in margin] or [0]
    margin_y = [point['margin'] for point in margin] or [0]
    fig.add_trace(
        go.Scatter(
            x=margin_x,
            y=margin_y,
            mode='lines',
            line=dict(color=margin_line, width=1.6, shape='hv'),
            fill='tozeroy',
            fillcolor=margin_fill,
            hovertemplate='Margin: %{y:+d}<extra></extra>',
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    span = margin_tick_span(margin_y, step=5)
    tickvals = list(range(-span, span + 1, 5))
    fig.update_yaxes(
        range=[-span, span],
        tickmode='array',
        tickvals=tickvals,
        ticktext=[str(value) for value in tickvals],
        zeroline=True,
        zerolinecolor='#94a3b8',
        showgrid=True,
        gridcolor='#e2e8f0',
        tickfont=dict(size=10),
        row=2,
        col=1,
    )

    home_pts = scoring.get('home') or [None] * len(buckets)
    away_pts = scoring.get('away') or [None] * len(buckets)
    score_z = [home_pts, away_pts]
    score_y = [
        (home or {}).get('team_name') or 'Home',
        (away or {}).get('team_name') or 'Away',
    ]
    score_max = max([value or 0 for row in score_z for value in row] or [0])
    fig.add_trace(
        go.Heatmap(
            z=score_z,
            x=x_centers,
            y=score_y,
            zmin=0,
            zmax=max(1, score_max),
            colorscale=colorscale,
            xgap=2,
            ygap=2,
            hoverongaps=False,
            showscale=False,
            customdata=[hover_x, hover_x],
            hovertemplate='%{y}<br>%{customdata}<br>PTS: %{z}<extra></extra>',
        ),
        row=3,
        col=1,
    )
    fig.update_yaxes(autorange='reversed', ticksuffix='  ', row=3, col=1)
    text_colors = score_text_colors(score_z, score_max, colorscale)
    by_color = {SCORE_TEXT_DARK: ([], [], []), SCORE_TEXT_LIGHT: ([], [], [])}
    for row_i, y_label in enumerate(score_y):
        for col_i, x_value in enumerate(x_centers):
            value = score_z[row_i][col_i] if col_i < len(score_z[row_i]) else None
            if not value:
                continue
            xs, ys, texts = by_color[text_colors[row_i][col_i]]
            xs.append(x_value)
            ys.append(y_label)
            texts.append(str(value))
    for color, (xs, ys, texts) in by_color.items():
        if not texts:
            continue
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode='text',
                text=texts,
                textfont=dict(size=SCORE_TEXT_SIZE, color=color),
                hoverinfo='skip',
                showlegend=False,
            ),
            row=3,
            col=1,
        )

    tickvals = [period['start'] + period['seconds'] / 2 for period in periods]
    ticktext = [period['label'] for period in periods]
    game_end = periods[-1]['end'] if periods else 1
    for axis_row in (1, 2, 3, 4):
        fig.update_xaxes(
            range=[0, game_end],
            tickvals=tickvals,
            ticktext=ticktext if axis_row == 4 else [],
            showgrid=False,
            row=axis_row,
            col=1,
        )
        if axis_row != 2:
            fig.update_yaxes(showgrid=False, row=axis_row, col=1)

    for period in periods[1:]:
        fig.add_vline(
            x=period['start'],
            line_width=1,
            line_color='#94a3b8',
            line_dash='solid',
        )

    fig.update_layout(
        width=width,
        height=height,
        autosize=False,
        margin=dict(l=140, r=24, t=48, b=72),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#334155', size=12),
        hovermode='closest',
    )
    fig.update_annotations(font=dict(size=14, color='#1e293b'))
    return fig
