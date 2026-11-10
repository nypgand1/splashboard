# -*- coding: utf-8 -*-
"""Season rotation: per-minute on-court rate and mean score margin."""
import pandas as pd

from synergy_inbounder.http_wave import run_wave
from synergy_inbounder.names import person_name
from synergy_inbounder.parser import Parser
from synergy_reporter.rotation import (
    _shirt_label,
    _shirt_sort_key,
    build_rotation_payload,
    margin_tick_span,
    period_label,
    team_on_court_seconds,
    walk_lineup,
)
from synergy_reporter.team_season import OPPONENT_ALL

SELECTED_COLOR = '#0077b6'
OPPONENT_COLOR = '#94a3b8'
SELECTED_FILL = 'rgba(0, 119, 182, 0.20)'
OPPONENT_FILL = 'rgba(148, 163, 184, 0.25)'
ZERO_LINE = '#475569'
TITLE_COLOR = '#1e293b'
LABEL_COLOR = '#334155'
FIGURE_MARGIN = {'l': 112, 'r': 112, 't': 40, 'b': 48}
ROW_PX = 22
MARGIN_BUDGET = 180
FIGURE_CHROME = 200
MIN_FIGURE_HEIGHT = 520
SEAM = 0.06
BAND_MIN = 0.25
BAND_MAX = 0.45
MARGIN_MIN = 0.18
PERIOD_RULE = '#94a3b8'
ROTATION_EMPTY = 'No rotation chart for this view.'
ROTATION_SELECT = 'Select a team.'
ROTATION_SELECT_NEXT = 'Choose one team.'

_STARTERS = {}
_SHIRTS = {}
_FACTS = {}
_FACT_ATTEMPTS = set()
_SUMMARIES = {}
_SHIRT_SOURCE = {}


def clear_rotation_cache():
    _STARTERS.clear()
    _SHIRTS.clear()
    _FACTS.clear()
    _FACT_ATTEMPTS.clear()
    _SUMMARIES.clear()
    _SHIRT_SOURCE.clear()


def infer_opening_five(frame, team_id):
    """Players who are on the floor before their first substitution in.

    Returns five person ids, or None when the opening group is not five.
    """
    if frame is None or getattr(frame, 'empty', True):
        return None
    team = str(team_id)
    opened = []
    seen = set()
    came_in = set()
    for row in frame.itertuples(index=False):
        entity = getattr(row, 'entityId', None)
        if entity is None or str(entity) != team:
            continue
        person = getattr(row, 'personId', None)
        if person is None or (isinstance(person, float) and pd.isna(person)):
            continue
        key = str(person)
        event = str(getattr(row, 'eventType', '') or '')
        subtype = str(getattr(row, 'subType', '') or '')
        if event == 'substitution' and subtype == 'in':
            came_in.add(key)
            continue
        if key in came_in or key in seen:
            continue
        seen.add(key)
        opened.append(person)
        if len(opened) > 5:
            return None
    if len(opened) == 5:
        return opened
    return None


def _starters_from_player_stats(payload):
    return Parser.starter_dict_from_rows((payload or {}).get('data'))


def _on_court(frame, starters, home, away, selected):
    walked = walk_lineup(frame, starters)
    payload = build_rotation_payload(
        walked, starters or {}, {}, home, away, marks=False,
    )
    return walked, team_on_court_seconds(payload, selected)


def _remember_shirts(team_id, roster):
    for row in roster or []:
        if str(row.get('entityId')) != str(team_id) or not row.get('personId'):
            continue
        number = row.get('shirtNumber')
        if number in (None, ''):
            continue
        _SHIRTS.setdefault(str(team_id), {})[str(row['personId'])] = number


def prepare_game(org_id, game, fetch_starters=None, fetch_roster=None, selected_id=None):
    """Lineup columns for one game.

    The selected team must finish the shared walk with on-court seconds.
    A 4- or 6-player substitution row does not drop the game. The opponent
    lineup is not required.
    """
    source = game.get('pbp')
    home = game.get('home')
    away = game.get('away')
    if source is None or getattr(source, 'empty', True) or not home or not away:
        return None
    selected = selected_id or home
    fixture_id = str(game.get('fixture_id'))
    key = (org_id, fixture_id)
    cached = _STARTERS.get(key)
    starters = None
    frame = None
    if cached:
        frame, seconds = _on_court(source, cached, home, away, selected)
        if seconds > 0:
            starters = cached
    if starters is None:
        seeded = {}
        for team in (home, away):
            opening = infer_opening_five(source, team)
            if opening:
                seeded[team] = opening
        frame, seconds = _on_court(source, seeded, home, away, selected)
        if seconds > 0:
            starters = seeded
        else:
            if fetch_starters is None:
                return None
            try:
                official = fetch_starters(org_id, fixture_id, game.get('status')) or {}
            except Exception:
                return None
            frame, seconds = _on_court(source, official, home, away, selected)
            if seconds <= 0:
                return None
            starters = official
        _STARTERS[key] = starters
    if fetch_roster is not None:
        for team in (home, away):
            if _SHIRTS.get(str(team)):
                continue
            try:
                roster = fetch_roster(org_id, fixture_id, game.get('status'))
            except Exception:
                continue
            _remember_shirts(team, roster or [])
    return {
        'home': home,
        'away': away,
        'frame': frame,
        'starters': starters,
    }


def _period_id(period):
    try:
        return int(period.get('id'))
    except (TypeError, ValueError):
        return period.get('id')


def _columns(minutes, ot_lengths):
    quarter = max(1, int(minutes) // 4)
    columns = []
    for period_id in (1, 2, 3, 4):
        for minute in range(quarter):
            columns.append({'period': period_id, 'minute': minute})
    for period_id, length in ot_lengths:
        for minute in range(length):
            columns.append({'period': period_id, 'minute': minute})
    return columns


def _clock_label(period_id, minute, lengths):
    length = (lengths or {}).get(period_id) or 1
    start = length - minute
    end = start - 1
    return '{0} {1:02d}:00–{2:02d}:00'.format(period_label(period_id), start, end)


def _overlap(start, end, left, right):
    return max(0.0, min(end, right) - max(start, left))


def _margin_at(points, moment):
    value = 0.0
    for point in points:
        if point['t'] <= moment + 1e-6:
            value = point['margin']
        else:
            break
    return value


def _roster_rows(starters, shirts):
    rows = []
    for team_id, people in (starters or {}).items():
        for person_id in people or []:
            rows.append({
                'personId': person_id,
                'entityId': team_id,
                'starter': True,
                'shirtNumber': (shirts or {}).get(str(team_id), {}).get(str(person_id)),
            })
    for team_id, people in (shirts or {}).items():
        known = {str(row['personId']) for row in rows if str(row['entityId']) == str(team_id)}
        for person_id, shirt in people.items():
            if str(person_id) in known:
                continue
            rows.append({
                'personId': person_id,
                'entityId': team_id,
                'starter': False,
                'shirtNumber': shirt,
            })
    return rows


def aggregate_games(games, selected_id, opponent_id, minutes, id_table, shirts=None):
    """Per-minute rates. ``games`` are prepared frames with lineup columns."""
    selected = str(selected_id)
    opponent = None if not opponent_id or opponent_id == OPPONENT_ALL else str(opponent_id)
    payloads = []
    ot_lengths = {}
    for game in games or []:
        home = game.get('home')
        away = game.get('away')
        if not home or not away:
            continue
        if selected not in (str(home), str(away)):
            continue
        summary = game.get('summary') or {}
        if summary.get('payload'):
            payload = _labeled(summary['payload'], id_table, shirts)
        elif game.get('frame') is not None:
            payload = build_rotation_payload(
                game.get('frame'), game.get('starters') or {}, id_table, home, away,
                _roster_rows(game.get('starters'), shirts),
            )
        else:
            continue
        if not payload.get('periods'):
            continue
        if team_on_court_seconds(payload, selected) <= 0:
            continue
        payloads.append((game, payload))
        for period in payload['periods']:
            period_id = _period_id(period)
            if period_id in (1, 2, 3, 4) or not isinstance(period_id, int):
                continue
            ot_lengths[period_id] = max(
                ot_lengths.get(period_id, 0), max(1, int(period['seconds']) // 60),
            )
    columns = _columns(minutes, sorted(ot_lengths.items()))
    quarter = max(1, int(minutes) // 4)
    lengths = {period_id: quarter for period_id in (1, 2, 3, 4)}
    lengths.update(ot_lengths)
    index = {(column['period'], column['minute']): pos for pos, column in enumerate(columns)}
    counts = [0 for _ in columns]
    margin_sum = [0.0 for _ in columns]
    margin_start = [0.0 for _ in columns]
    seconds = {}

    def _bucket(team_id):
        return seconds.setdefault(str(team_id), {})

    for game, payload in payloads:
        home = str(game['home'])
        sign = 1.0 if selected == home else -1.0
        windows = {}
        present = set()
        for period in payload['periods']:
            period_id = _period_id(period)
            if (period_id, 0) not in index and period_id not in (1, 2, 3, 4):
                continue
            length = quarter if period_id in (1, 2, 3, 4) else ot_lengths.get(period_id, 0)
            present.add(period_id)
            for minute in range(length):
                pos = index.get((period_id, minute))
                if pos is None:
                    continue
                windows[pos] = (
                    period['start'] + minute * 60.0,
                    period['start'] + (minute + 1) * 60.0,
                )
                counts[pos] += 1
                margin_start[pos] += sign * _margin_at(payload.get('margin') or [], period['start'])
                margin_sum[pos] += sign * _margin_at(
                    payload.get('margin') or [], windows[pos][1],
                )
        for side in payload.get('teams') or []:
            team_id = str(side.get('team_id'))
            if team_id != selected and team_id != opponent:
                continue
            bucket = _bucket(team_id)
            for player in side.get('players') or []:
                if player.get('dnp'):
                    continue
                person = str(player.get('person_id'))
                shirt = player.get('shirt_number')
                cells = bucket.setdefault(person, {
                    'label': player.get('label') or person_name(id_table, person),
                    'shirt': shirt,
                    'seconds': [0.0 for _ in columns],
                })
                if shirt not in (None, '') and cells.get('shirt') in (None, ''):
                    cells['shirt'] = shirt
                    cells['label'] = player.get('label') or cells['label']
                for stint in player.get('stints') or []:
                    for pos, window in windows.items():
                        cells['seconds'][pos] += _overlap(
                            stint['start'], stint['end'], window[0], window[1],
                        )
    def _players(team_id):
        rows = []
        for person, info in _bucket(team_id).items():
            total = sum(info['seconds'])
            if total <= 0:
                continue
            rates = []
            for pos, amount in enumerate(info['seconds']):
                sample = counts[pos]
                rates.append(None if not sample else amount / 60.0 / sample)
            rows.append({
                'person_id': person,
                'label': info['label'],
                'shirt': info.get('shirt'),
                'seconds': total,
                'rates': rates,
            })
        rows.sort(key=_player_sort_key)
        return rows

    regulation_n = 0
    if columns:
        regulation_n = counts[0]
    opponent_rows = _players(opponent) if opponent else []
    margin = []
    for pos, column in enumerate(columns):
        sample = counts[pos]
        margin.append({
            'n': sample,
            'y': None if not sample else margin_sum[pos] / sample,
            'start': None if not sample else margin_start[pos] / sample,
            'period': column['period'],
            'minute': column['minute'],
        })
    return {
        'columns': columns,
        'counts': counts,
        'quarter': quarter,
        'lengths': lengths,
        'n': regulation_n,
        'clock': _clock_label,
        'players': _players(selected),
        'opponent_players': opponent_rows,
        'margin': margin,
        'opponent': opponent if opponent_rows else None,
    }


def _segments(margin):
    segments = []
    current = None
    previous = None
    for pos, point in enumerate(margin):
        sample = point['n']
        if not sample or point['y'] is None:
            current = None
            previous = sample
            continue
        if current is None or sample != previous:
            current = []
            segments.append(current)
            if point['minute'] == 0 or sample != previous:
                current.append((pos, point['start']))
        current.append((pos + 1, point['y']))
        previous = sample
    return segments


def _step_runs(points):
    """Split an hv step at zero. The jump stays on the later x.

    The value holds flat from the left sample. A sign change is the vertical
    jump at the next sample, split at zero. No point is placed between the
    two x values.
    """
    if len(points) < 2:
        return []

    def kind(value):
        if value > 0:
            return 'pos'
        if value < 0:
            return 'neg'
        return 'zero'

    runs = []
    chunk = None
    chunk_kind = None

    def emit():
        nonlocal chunk, chunk_kind
        if chunk_kind in ('pos', 'neg') and chunk and len(chunk) >= 2:
            runs.append((chunk_kind, chunk))
        chunk = None
        chunk_kind = None

    for prev, nxt in zip(points, points[1:]):
        x1, y1 = nxt
        held = kind(prev[1])
        landed = kind(y1)
        if held in ('pos', 'neg'):
            if chunk_kind != held or not chunk:
                emit()
                chunk_kind = held
                chunk = [prev]
            elif chunk[-1] != prev:
                chunk.append(prev)
            if landed == held or landed == 'zero':
                chunk.append(nxt)
            else:
                chunk.append((x1, 0))
                emit()
                chunk_kind = landed
                chunk = [(x1, 0), (x1, y1)]
        elif landed in ('pos', 'neg'):
            if chunk_kind == landed and chunk:
                chunk.append(nxt)
            else:
                emit()
                chunk_kind = landed
                chunk = [(x1, 0), (x1, y1)]
        else:
            emit()
    emit()
    return runs


def _band_layout(top_n, bot_n):
    """Figure height and subplot weights. One band skips the 0.25–0.45 clamp."""
    top_n = max(1, int(top_n))
    bot_n = max(0, int(bot_n))
    height = max(MIN_FIGURE_HEIGHT, top_n * ROW_PX + bot_n * ROW_PX + FIGURE_CHROME)
    if bot_n:
        denom = float(top_n * ROW_PX + bot_n * ROW_PX + MARGIN_BUDGET)
        top_w = max(BAND_MIN, min(BAND_MAX, (top_n * ROW_PX) / denom))
        bot_w = max(BAND_MIN, min(BAND_MAX, (bot_n * ROW_PX) / denom))
        mid_w = max(MARGIN_MIN, 1.0 - top_w - bot_w)
        return height, [top_w, mid_w, bot_w]
    denom = float(top_n * ROW_PX + MARGIN_BUDGET)
    top_w = (top_n * ROW_PX) / denom
    return height, [top_w, 1.0 - top_w]


def _period_axis(columns):
    """Midpoint ticks, and rules at each later period plus the right edge."""
    columns = list(columns or [])
    if not columns:
        return [], [], []
    groups = []
    start = 0
    for pos, column in enumerate(columns):
        if pos and column['period'] != columns[pos - 1]['period']:
            groups.append((start, pos - 1, columns[start]['period']))
            start = pos
    groups.append((start, len(columns) - 1, columns[start]['period']))
    vals = [(first + last) / 2.0 for first, last, _period in groups]
    text = [period_label(period) for _first, _last, period in groups]
    rules = [
        pos - 0.5
        for pos in range(1, len(columns))
        if columns[pos]['period'] != columns[pos - 1]['period']
    ]
    rules.append(len(columns) - 0.5)
    return vals, text, rules


def _player_sort_key(row):
    """Higher on-court rate in an earlier minute ranks above.

    A minute nobody played compares as zero, the same for every row. Jersey,
    then name, breaks a tie that survives every minute.
    """
    rates = tuple(
        -(0.0 if rate is None else float(rate)) for rate in (row.get('rates') or [])
    )
    return (rates, _shirt_sort_key(row.get('shirt')), row.get('label') or '')


def _name_axis(labels):
    labels = list(labels or ['—'])
    return dict(
        autorange='reversed',
        categoryorder='array',
        categoryarray=labels,
        tickmode='array',
        tickvals=labels,
        ticktext=labels,
        ticksuffix='  ',
        tickfont=dict(size=12, color=LABEL_COLOR),
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks='',
        fixedrange=True,
        automargin=False,
        title_text='',
    )


def build_team_rotation_figure(aggregate, selected_name, opponent_name=None):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    columns = aggregate.get('columns') or []
    players = aggregate.get('players') or []
    opponent_players = aggregate.get('opponent_players') or []
    opponent = aggregate.get('opponent')
    lengths = aggregate.get('lengths') or {}
    tick_vals, tick_text, period_rules = _period_axis(columns)

    def _heat(rows, color):
        z = []
        y = []
        custom = []
        for row in rows:
            z.append(list(row['rates']))
            y.append(row['label'])
            custom.append([
                [
                    aggregate['clock'](column['period'], column['minute'], lengths),
                    '' if rate is None else '{0:.0f}% · {1}/{2}'.format(
                        rate * 100,
                        int(round(rate * (aggregate['counts'][pos] or 0))),
                        aggregate['counts'][pos],
                    ),
                ]
                for pos, (column, rate) in enumerate(zip(columns, row['rates']))
            ])
        heat = go.Heatmap(
            z=z,
            x=list(range(len(columns))),
            y=y,
            zmin=0,
            zmax=1,
            colorscale=[[0, '#ffffff'], [1, color]],
            showscale=False,
            hovertemplate='%{y}<br>%{customdata[0]}<br>%{customdata[1]}<extra></extra>',
            customdata=custom,
            xgap=1,
            ygap=1,
        )
        return heat, y

    show_opponent = bool(opponent) and bool(opponent_players)
    top_rows = players or [{'label': '—', 'rates': [None] * len(columns)}]
    top_n = max(1, len(top_rows))
    bot_n = len(opponent_players) if show_opponent else 0
    height, weights = _band_layout(top_n, bot_n)
    if show_opponent:
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            row_heights=weights,
            vertical_spacing=SEAM,
            subplot_titles=(selected_name or '', '', opponent_name or ''),
        )
    else:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=weights,
            vertical_spacing=SEAM,
            subplot_titles=(selected_name or '', ''),
        )
    top, top_y = _heat(top_rows, SELECTED_COLOR)
    fig.add_trace(top, row=1, col=1)
    fig.update_yaxes(row=1, col=1, **_name_axis(top_y))
    margin_values = []
    for segment in _segments(aggregate.get('margin') or []):
        margin_values.extend(point[1] for point in segment)
        for kind, run in _step_runs(segment):
            color, fill = (
                (SELECTED_COLOR, SELECTED_FILL) if kind == 'pos'
                else (OPPONENT_COLOR, OPPONENT_FILL)
            )
            fig.add_trace(go.Scatter(
                x=[point[0] for point in run],
                y=[point[1] for point in run],
                mode='lines',
                line={'color': color, 'width': 2, 'shape': 'hv'},
                fill='tozeroy',
                fillcolor=fill,
                hovertemplate='Margin %{y:.1f}<extra></extra>',
                showlegend=False,
            ), row=2, col=1)
    bottom_y = []
    if show_opponent:
        bottom, bottom_y = _heat(opponent_players, OPPONENT_COLOR)
        fig.add_trace(bottom, row=3, col=1)
        fig.update_yaxes(row=3, col=1, **_name_axis(bottom_y))
    span = margin_tick_span(margin_values, step=5)
    margin_ticks = list(range(-span, span + 1, 5))
    fig.update_yaxes(
        range=[-span, span],
        tickmode='array',
        tickvals=margin_ticks,
        ticktext=[str(value) for value in margin_ticks],
        zeroline=True,
        zerolinecolor=ZERO_LINE,
        zerolinewidth=1.5,
        showgrid=True,
        gridcolor='#e2e8f0',
        tickfont=dict(size=10, color=LABEL_COLOR),
        ticksuffix='  ',
        fixedrange=True,
        automargin=False,
        title_text='',
        row=2, col=1,
    )
    bottom_row = 3 if show_opponent else 2
    x_end = max(0, len(columns) - 0.5)
    for row in range(1, bottom_row + 1):
        fig.update_xaxes(
            range=[-0.5, x_end],
            fixedrange=True,
            tickmode='array',
            tickvals=tick_vals,
            ticktext=tick_text if row == bottom_row else [],
            showticklabels=(row == bottom_row),
            showgrid=False,
            row=row, col=1,
        )
        fig.update_yaxes(fixedrange=True, row=row, col=1)
    for rule in period_rules:
        fig.add_vline(x=rule, line_width=1, line_color=PERIOD_RULE)
    fig.update_layout(
        margin=dict(FIGURE_MARGIN),
        paper_bgcolor='#ffffff',
        plot_bgcolor='#ffffff',
        font=dict(color=LABEL_COLOR, size=12),
        height=height,
        dragmode=False,
    )

    def mirror_names(dest, overlay, anchor, labels):
        src = fig.layout['yaxis' if overlay == 'y' else 'yaxis' + overlay[1:]]
        fig.update_layout(**{dest: dict(
            overlaying=overlay,
            side='right',
            anchor=anchor,
            domain=list(src.domain),
            autorange='reversed',
            categoryorder='array',
            categoryarray=list(labels),
            tickmode='array',
            tickvals=list(labels),
            ticktext=list(labels),
            tickprefix='  ',
            showgrid=False,
            zeroline=False,
            showline=False,
            ticks='',
            fixedrange=True,
            automargin=False,
            tickfont=dict(size=12, color=LABEL_COLOR),
        )})
        fig.add_trace(go.Scatter(
            x=[0] * len(labels),
            y=list(labels),
            xaxis=anchor,
            yaxis=dest.replace('yaxis', 'y'),
            mode='markers',
            marker=dict(opacity=0, size=0),
            hoverinfo='skip',
            showlegend=False,
        ))

    def mirror_numbers(dest, overlay, anchor):
        src = fig.layout.yaxis2
        fig.update_layout(**{dest: dict(
            overlaying=overlay,
            side='right',
            anchor=anchor,
            domain=list(src.domain),
            range=list(src.range),
            tickmode='array',
            tickvals=list(src.tickvals),
            ticktext=[str(value) for value in src.ticktext],
            tickprefix='  ',
            showgrid=False,
            zeroline=False,
            showline=False,
            ticks='',
            fixedrange=True,
            automargin=False,
            tickfont=dict(size=10, color=LABEL_COLOR),
        )})
        fig.add_trace(go.Scatter(
            x=[0],
            y=[0],
            xaxis=anchor,
            yaxis=dest.replace('yaxis', 'y'),
            mode='markers',
            marker=dict(opacity=0, size=0),
            hoverinfo='skip',
            showlegend=False,
        ))

    if show_opponent:
        mirror_names('yaxis4', 'y', 'x', top_y)
        mirror_numbers('yaxis5', 'y2', 'x2')
        mirror_names('yaxis6', 'y3', 'x3', bottom_y)
    else:
        mirror_names('yaxis3', 'y', 'x', top_y)
        mirror_numbers('yaxis4', 'y2', 'x2')
    for ann in fig.layout.annotations or []:
        if not ann.text:
            continue
        ann.font = dict(size=14, color=TITLE_COLOR)
    return fig


def _labeled(payload, id_table, shirts):
    teams = []
    for side in payload.get('teams') or []:
        team_id = str(side.get('team_id'))
        known = (shirts or {}).get(team_id) or {}
        roster_by_id = {
            person_id: {'shirtNumber': number}
            for person_id, number in known.items()
        }
        players = []
        for player in side.get('players') or []:
            person = player.get('person_id')
            copied = dict(player)
            copied['shirt_number'] = known.get(str(person))
            copied['label'] = _shirt_label(person, id_table, roster_by_id)
            players.append(copied)
        copied_side = dict(side)
        copied_side['players'] = players
        teams.append(copied_side)
    copied_payload = dict(payload)
    copied_payload['teams'] = teams
    return copied_payload


def _walk_payload(pbp, starters, home, away):
    walked = walk_lineup(pbp, starters)
    return build_rotation_payload(
        walked, starters or {}, {}, home, away, marks=False,
    )


def _fact_key(org_id, fixture_id):
    return (str(org_id), str(fixture_id))


def _store_shirt(team_id, person_id, number, source):
    if number in (None, '') or not team_id or not person_id:
        return
    key = (str(team_id), str(person_id))
    if _SHIRT_SOURCE.get(key) == 'roster' and source != 'roster':
        return
    _SHIRTS.setdefault(key[0], {})[key[1]] = number
    _SHIRT_SOURCE[key] = 'roster' if source == 'roster' else 'stats'


def _absorb_facts(org_id, fixture_id, roster_payload, stats_rows):
    if isinstance(roster_payload, list):
        roster_rows = roster_payload
    else:
        roster_rows = Parser._roster_from_fixture_json(roster_payload or {})
    if isinstance(stats_rows, dict):
        stats_rows = Parser._roster_from_json(stats_rows)
    roster_rows = list(roster_rows or [])
    stats_rows = list(stats_rows or [])
    merged = Parser._merge_roster(roster_rows, stats_rows)
    _FACTS[_fact_key(org_id, fixture_id)] = merged
    roster_people = set()
    for row in roster_rows:
        person_id = row.get('personId')
        team_id = row.get('entityId')
        number = row.get('shirtNumber')
        if number in (None, '') or not person_id or not team_id:
            continue
        roster_people.add((str(team_id), str(person_id)))
        _store_shirt(team_id, person_id, number, 'roster')
    for row in merged:
        team_id = row.get('entityId')
        person_id = row.get('personId')
        if (str(team_id), str(person_id)) in roster_people:
            continue
        _store_shirt(team_id, person_id, row.get('shirtNumber'), 'stats')
    _FACT_ATTEMPTS.add(_fact_key(org_id, fixture_id))


def _ensure_summary(org_id, game, selected):
    pbp = game.get('pbp')
    home = game.get('home')
    away = game.get('away')
    if pbp is None or getattr(pbp, 'empty', True) or not home or not away:
        return None
    key = (str(org_id), str(game.get('fixture_id')), id(pbp))
    current = _SUMMARIES.get(key)
    selected = str(selected)

    def usable(payload):
        return team_on_court_seconds(payload, selected) > 0

    if current and usable(current.get('payload')):
        return current
    if current and current.get('official_tried'):
        return None
    facts = _FACTS.get(_fact_key(org_id, game.get('fixture_id'))) or []
    if current is None:
        seeded = {}
        for team in (home, away):
            opening = infer_opening_five(pbp, team)
            if opening:
                seeded[team] = opening
        payload = _walk_payload(pbp, seeded, home, away)
        if usable(payload):
            saved = {
                'payload': payload,
                'starters': seeded,
                'official_tried': False,
            }
            _SUMMARIES[key] = saved
            _STARTERS[_fact_key(org_id, game.get('fixture_id'))] = seeded
            return saved
        current = {'payload': payload, 'starters': seeded, 'official_tried': False}
    official = Parser.starter_dict_from_rows(facts) if facts else {}
    if not official:
        current['official_tried'] = True
        _SUMMARIES[key] = current
        return None
    payload = _walk_payload(pbp, official, home, away)
    saved = {'payload': payload, 'starters': official, 'official_tried': True}
    _SUMMARIES[key] = saved
    if usable(payload):
        _STARTERS[_fact_key(org_id, game.get('fixture_id'))] = official
        return saved
    return None


def default_fetch_starters(org_id, fixture_id, status):
    from synergy_inbounder.communicator import Communicator
    payload = Communicator.get_game_player_stats_synergy(
        org_id, fixture_id, live=False, fixture_status=status,
    )
    return _starters_from_player_stats(payload)


def default_fetch_roster(org_id, fixture_id, status):
    from synergy_inbounder.communicator import Communicator
    payload = Communicator.get_fixture_roster_synergy(
        org_id, fixture_id, fixture_status=status,
    )
    return Parser._roster_from_fixture_json(payload)


def default_fetch_player_rows(org_id, fixture_id, status):
    from synergy_inbounder.communicator import Communicator
    payload = Communicator.get_game_player_stats_synergy(
        org_id, fixture_id, live=False, fixture_status=status,
    )
    return Parser._roster_from_json(payload or {})


def season_aggregate(source, fetch_starters=None, fetch_roster=None, fetch_player_rows=None):
    """Walk each game once. Roster and player-stats bibs share one wave.

    ``fetch_starters`` stays in the signature for callers that still pass it.
    Starters come from the opening five, then from the merged roster rows.
    """
    del fetch_starters
    if fetch_roster is None:
        fetch_roster = default_fetch_roster
    if fetch_player_rows is None:
        fetch_player_rows = default_fetch_player_rows
    org_id = source.get('org_id')
    selected = source.get('team')
    games = list(source.get('games') or [])
    pending = [
        game for game in games
        if game.get('pbp') is not None
        and not getattr(game.get('pbp'), 'empty', True)
        and _fact_key(org_id, game.get('fixture_id')) not in _FACT_ATTEMPTS
    ]

    def _one(game):
        fixture = str(game.get('fixture_id'))
        status = game.get('status')
        roster_payload = None
        stats_rows = None
        roster_error = False
        stats_error = False
        try:
            roster_payload = fetch_roster(org_id, fixture, status)
        except Exception:
            roster_error = True
        try:
            stats_rows = fetch_player_rows(org_id, fixture, status)
        except Exception:
            stats_error = True
        return fixture, roster_payload, stats_rows, roster_error and stats_error

    if pending:
        fetched = run_wave([lambda game=game: _one(game) for game in pending])
        for fixture, roster_payload, stats_rows, both_failed in fetched:
            if both_failed:
                continue
            _absorb_facts(org_id, fixture, roster_payload, stats_rows)
    prepared = []
    for game in games:
        summary = _ensure_summary(org_id, game, selected)
        if summary is None:
            continue
        prepared.append({
            'home': game.get('home'),
            'away': game.get('away'),
            'summary': summary,
        })
    shirts = {team: dict(people) for team, people in _SHIRTS.items()}
    return aggregate_games(
        prepared,
        selected,
        source.get('opponent'),
        source.get('minutes') or 48,
        source.get('id_table') or {},
        shirts,
    )
