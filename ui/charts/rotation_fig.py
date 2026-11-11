# -*- coding: utf-8 -*-
"""Plotly figure builders and shared dual-axis mirroring for Game and Season Rotation."""
import math
import re

from domain.periods import period_label
from ui.tokens import (
    AWAY_FILL_SOFT,
    AWAY_RUN_FILL,
    AWAY_SLATE,
    BORDER_SLATE,
    BRAVES_BLUE_PRIMARY,
    HOME_FILL_SOFT,
    HOME_RUN_FILL,
    INK_PRIMARY,
    INK_SECONDARY,
    INK_SUBTLE,
    KILL_STOP_RED,
    MARGIN_LINE_BLUE,
    ROTATION_FIGURE_MARGIN,
)

KILL_COLOR = KILL_STOP_RED
KILL_ROW = '3+ STOPS'
STOP_COUNT_FONT = 11
RUN_LABEL_INK = 13
COUNT_INK = 11
SEAM_LINE = 11
SUBPLOT_TITLE_FONT = 14
RUN_SCORE_SHIFT = 2
LOWER_SEAM_INK = (
    RUN_SCORE_SHIFT
    + SUBPLOT_TITLE_FONT
    + SUBPLOT_TITLE_FONT
    + SUBPLOT_TITLE_FONT
    + COUNT_INK
)
BASE_VERTICAL_SPACING = 0.06
FIGURE_MARGIN_T = ROTATION_FIGURE_MARGIN['t']
FIGURE_MARGIN_B = ROTATION_FIGURE_MARGIN['b']

SELECTED_COLOR = BRAVES_BLUE_PRIMARY
OPPONENT_COLOR = AWAY_SLATE
SELECTED_FILL = HOME_FILL_SOFT
OPPONENT_FILL = AWAY_FILL_SOFT
ZERO_LINE = INK_SUBTLE
TITLE_COLOR = INK_PRIMARY
LABEL_COLOR = INK_SECONDARY
FIGURE_MARGIN = dict(ROTATION_FIGURE_MARGIN)
ROW_PX = 22
MARGIN_BUDGET = 180
FIGURE_CHROME = 200
MIN_FIGURE_HEIGHT = 520
SEAM = 0.06
BAND_MIN = 0.25
BAND_MAX = 0.45
MARGIN_MIN = 0.18
PERIOD_RULE = AWAY_SLATE

SCORE_TEXT_DARK = INK_PRIMARY
SCORE_TEXT_LIGHT = '#ffffff'
SCORE_TEXT_SIZE = 14
SCORE_TEXT_LUMINANCE_THRESHOLD = 0.45
_RGB_RE = re.compile(r'rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)')


def margin_tick_span(values, step=5):
    abs_max = max((abs(value) for value in values), default=0)
    return max(step, int(math.ceil(abs_max / float(step)) * step))


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


def stop_seam_spacing(figure_height, base=BASE_VERTICAL_SPACING):
    """Paper gap between the Gantt and the margin, as a fraction of the plot area."""
    plot_h = max(1.0, float(figure_height) - FIGURE_MARGIN_T - FIGURE_MARGIN_B)
    seam = base * plot_h
    if seam < RUN_LABEL_INK + COUNT_INK:
        seam += SEAM_LINE
    return seam / plot_h


def away_lane_height(base_height):
    """Figure height once the lower seam clears the home run number."""
    plot_h = max(1.0, float(base_height) - FIGURE_MARGIN_T - FIGURE_MARGIN_B)
    seam = stop_seam_spacing(base_height) * plot_h
    return float(base_height) + max(0.0, LOWER_SEAM_INK - seam)


def add_mirrored_categories_axis(
    fig,
    dest,
    overlay,
    anchor,
    labels,
    x_val=0,
    autorange=None,
    ExplicitRange=False,
    kill_row=None,
    color=LABEL_COLOR,
):
    """Add a right-hand mirrored category y-axis and an invisible anchor trace."""
    import plotly.graph_objects as go

    labels = list(labels or ['—'])
    src_key = 'yaxis' if overlay == 'y' else 'yaxis' + overlay[1:]
    src = fig.layout[src_key]
    axis_cfg = dict(
        overlaying=overlay,
        side='right',
        anchor=anchor,
        domain=list(src.domain),
        categoryorder='array',
        categoryarray=labels,
        tickprefix='  ',
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks='',
        fixedrange=True,
        automargin=False,
        tickfont=dict(size=12, color=color),
    )
    if autorange is not None:
        axis_cfg['autorange'] = autorange
    if ExplicitRange:
        axis_cfg['range'] = [-0.5, len(labels) - 0.5]
    if kill_row and kill_row in labels:
        axis_cfg.update(
            tickmode='array',
            tickvals=labels,
            ticktext=['' if label == kill_row else label for label in labels],
        )
    elif autorange == 'reversed':
        axis_cfg.update(
            tickmode='array',
            tickvals=labels,
            ticktext=labels,
        )
    fig.update_layout(**{dest: axis_cfg})
    fig.add_trace(go.Scatter(
        x=[x_val] * len(labels),
        y=labels,
        xaxis=anchor,
        yaxis=dest.replace('yaxis', 'y'),
        mode='markers',
        marker=dict(opacity=0, size=0),
        hoverinfo='skip',
        showlegend=False,
    ))


def add_mirrored_numbers_axis(
    fig,
    dest,
    src_name,
    overlay,
    anchor,
    x_val=0,
    color=LABEL_COLOR,
):
    """Add a right-hand mirrored numeric y-axis and an invisible anchor trace."""
    import plotly.graph_objects as go

    src = fig.layout[src_name]
    font_size = (src.tickfont.size if getattr(src, 'tickfont', None) else None) or 10
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
        tickfont=dict(size=font_size, color=color),
    )})
    fig.add_trace(go.Scatter(
        x=[x_val],
        y=[0],
        xaxis=anchor,
        yaxis=dest.replace('yaxis', 'y'),
        mode='markers',
        marker=dict(opacity=0, size=0),
        hoverinfo='skip',
        showlegend=False,
    ))


def _open_lower_seam(fig, base_height):
    """Keep the upper seam and the panel pixel sizes. Grow only the lower seam."""
    plot_h = max(1.0, float(base_height) - FIGURE_MARGIN_T - FIGURE_MARGIN_B)
    seam = stop_seam_spacing(base_height) * plot_h
    shortfall = max(0.0, LOWER_SEAM_INK - seam)
    new_plot_h = plot_h + shortfall

    def span_px(domain):
        return (float(domain[1]) - float(domain[0])) * plot_h

    top = fig.layout.yaxis.domain
    margin = fig.layout.yaxis2.domain
    bottom = fig.layout.yaxis3.domain
    top_px = span_px(top)
    margin_px = span_px(margin)
    bottom_px = span_px(bottom)
    upper_px = (float(top[0]) - float(margin[1])) * plot_h
    lower_px = upper_px + shortfall

    cursor = 1.0
    top_hi = cursor
    cursor -= top_px / new_plot_h
    top_lo = cursor
    cursor -= upper_px / new_plot_h
    margin_top = cursor
    cursor -= margin_px / new_plot_h
    margin_bottom = cursor
    cursor -= lower_px / new_plot_h
    bottom_hi = cursor
    cursor -= bottom_px / new_plot_h
    bottom_lo = 0.0 if abs(cursor) < 1e-6 else cursor

    fig.layout.yaxis.domain = (top_lo, top_hi)
    fig.layout.yaxis2.domain = (margin_bottom, margin_top)
    fig.layout.yaxis3.domain = (bottom_lo, bottom_hi)
    return base_height + shortfall


def _raise_bottom_title(fig):
    """Shift the bottom panel's title up by one count line."""
    panel_top = float(fig.layout.yaxis3.domain[1])
    titles = [
        ann for ann in fig.layout.annotations or []
        if getattr(ann, 'xref', None) == 'paper'
        and getattr(ann, 'yref', None) == 'paper'
        and getattr(ann, 'yanchor', None) == 'bottom'
        and ann.text
        and ann.text != KILL_ROW
        and not str(ann.text).isdigit()
    ]
    if len(titles) < 2:
        return
    bottom = min(titles, key=lambda ann: float(ann.y))
    bottom.y = panel_top
    bottom.yshift = STOP_COUNT_FONT


def _add_kill_annotations(fig):
    for yref, xref in (('y', 'x'), ('y3', 'x3')):
        for x, anchor, shift in ((0, 'right', -6), (1, 'left', 6)):
            fig.add_annotation(
                x=x,
                xref=f'{xref} domain',
                y=KILL_ROW,
                yref=yref,
                text=KILL_ROW,
                font=dict(size=12, color=KILL_COLOR),
                xanchor=anchor,
                showarrow=False,
                xshift=shift,
            )


def _add_stop_counts(fig, kills, periods, format_kill_label_fn):
    top_bottom = float(fig.layout.yaxis.domain[0])
    bottom_top = float(fig.layout.yaxis3.domain[1])
    for kill in kills or []:
        on_top = kill.get('side') == 'away'
        fig.add_annotation(
            x=(float(kill['start']) + float(kill['end'])) / 2.0,
            xref='x2',
            y=top_bottom if on_top else bottom_top,
            yref='paper',
            text=str(int(kill['stops'])),
            font=dict(size=STOP_COUNT_FONT, color=KILL_COLOR),
            xanchor='center',
            yanchor='top' if on_top else 'bottom',
            showarrow=False,
            hovertext=format_kill_label_fn(kill, periods),
        )


def _paint_team_titles(fig):
    """Team names keep 14px slate. Other annotations keep the font they were given."""
    for ann in fig.layout.annotations or []:
        if (
            getattr(ann, 'xref', None) == 'paper'
            and getattr(ann, 'yref', None) == 'paper'
            and getattr(ann, 'yanchor', None) == 'bottom'
            and ann.text
            and ann.text != KILL_ROW
            and not str(ann.text).isdigit()
        ):
            ann.font.size = SUBPLOT_TITLE_FONT
            ann.font.color = TITLE_COLOR


def build_rotation_figure(
    payload,
    playhead=None,
    show_dnp=False,
    uirevision=None,
    visible_players_fn=None,
    player_on_court_fn=None,
    format_kill_label_fn=None,
):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from synergy_reporter.rotation import (
        format_kill_label,
        player_on_court,
        visible_players,
    )

    visible_players_fn = visible_players_fn or visible_players
    player_on_court_fn = player_on_court_fn or player_on_court
    format_kill_label_fn = format_kill_label_fn or format_kill_label

    teams = (payload or {}).get('teams') or []
    periods = (payload or {}).get('periods') or []
    margin = (payload or {}).get('margin') or []
    runs = (payload or {}).get('runs') or []
    home = next((team for team in teams if team.get('side') == 'home'), teams[0] if teams else None)
    away = next((team for team in teams if team.get('side') == 'away'), teams[1] if len(teams) > 1 else None)

    kills = (payload or {}).get('kills') or []
    home_kills = [kill for kill in kills if kill.get('side') == 'home']
    away_kills = [kill for kill in kills if kill.get('side') == 'away']
    home_players = visible_players_fn(home, show_dnp) or [{'label': '—', 'stints': []}]
    away_players = visible_players_fn(away, show_dnp) or [{'label': '—', 'stints': []}]
    home_n = len(home_players) + 1 or 1
    away_n = len(away_players) + 1 or 1

    h_weight = max(BAND_MIN, min(BAND_MAX, (home_n * ROW_PX) / (home_n * ROW_PX + away_n * ROW_PX + MARGIN_BUDGET)))
    a_weight = max(BAND_MIN, min(BAND_MAX, (away_n * ROW_PX) / (home_n * ROW_PX + away_n * ROW_PX + MARGIN_BUDGET)))
    m_weight = max(MARGIN_MIN, 1.0 - h_weight - a_weight)

    base_height = max(MIN_FIGURE_HEIGHT, home_n * ROW_PX + away_n * ROW_PX + FIGURE_CHROME)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[a_weight, m_weight, h_weight],
        vertical_spacing=stop_seam_spacing(base_height),
        subplot_titles=(
            (away or {}).get('team_name') or 'Away',
            '',
            (home or {}).get('team_name') or 'Home',
        ),
    )
    _paint_team_titles(fig)
    total_height = _open_lower_seam(fig, base_height)

    game_end = periods[-1]['end'] if periods else 1

    home_color = BRAVES_BLUE_PRIMARY
    away_color = AWAY_SLATE
    margin_line = MARGIN_LINE_BLUE
    home_fill = HOME_FILL_SOFT
    away_fill = AWAY_FILL_SOFT

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
        if player_on_court_fn(player, playhead):
            return f'● {base}'
        return f'  {base}'

    def add_gantt(team, row, bar_color, players, side_kills, kill_edge):
        players_rev = list(reversed(players))
        y_cats = [axis_label(p) for p in players_rev]
        if kill_edge == 'bottom':
            y_cats = [KILL_ROW] + y_cats
        else:
            y_cats = y_cats + [KILL_ROW]
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
            on_floor = playhead is None or player_on_court_fn(player, playhead)
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
        if side_kills:
            for kill in sorted(side_kills, key=lambda item: item['start']):
                fig.add_trace(
                    go.Bar(
                        x=[max(0.0, kill['end'] - kill['start'])],
                        y=[KILL_ROW],
                        base=[kill['start']],
                        orientation='h',
                        marker=dict(
                            color=KILL_COLOR,
                            opacity=1.0,
                            line=dict(width=0),
                        ),
                        hovertext=format_kill_label_fn(kill, periods),
                        hoverinfo='text',
                        showlegend=False,
                    ),
                    row=row,
                    col=1,
                )
        axis = dict(
            ticksuffix='  ',
            categoryorder='array',
            categoryarray=y_cats,
        )
        if KILL_ROW in y_cats:
            axis.update(
                tickmode='array',
                tickvals=y_cats,
                ticktext=['' if cat == KILL_ROW else cat for cat in y_cats],
            )
        fig.update_yaxes(row=row, col=1, **axis)
        return y_cats

    away_labels = add_gantt(away, 1, away_color, away_players, away_kills, 'bottom')

    margin_x = [point['t'] for point in margin] or [0]
    stored_y = [point['margin'] for point in margin] or [0]
    margin_y = [-value for value in stored_y]
    away_lead_y = [max(0, y) for y in margin_y]
    home_lead_y = [min(0, y) for y in margin_y]

    home_name = (home or {}).get('team_name') or 'Home'
    away_name = (away or {}).get('team_name') or 'Away'

    hover_texts = []
    for point, chart_m in zip(margin, margin_y):
        h_score = point.get('home_score', 0)
        a_score = point.get('away_score', 0)
        clock_lbl = point.get('clock_label') or format_clock_str(point['t'])
        desc = point.get('desc', '')
        if chart_m > 0:
            diff_str = f"(+{chart_m})"
        elif chart_m < 0:
            diff_str = f"({chart_m})"
        else:
            diff_str = "(0)"

        lines = [
            f"<b>{clock_lbl}</b>",
            f"{away_name} {a_score} - {h_score} {home_name} {diff_str}",
        ]
        if desc:
            lines.append(f"{desc}")
        hover_texts.append("<br>".join(lines))

    span = margin_tick_span(margin_y, step=5)

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
        zerolinecolor=ZERO_LINE,
        zerolinewidth=1.5,
        showgrid=True,
        gridcolor=BORDER_SLATE,
        tickfont=dict(size=10),
        ticksuffix='  ',
        row=2,
        col=1,
    )

    home_labels = add_gantt(home, 3, home_color, home_players, home_kills, 'top')

    view_start, view_end = 0, game_end
    tickvals = [period['start'] + period['seconds'] / 2 for period in periods]
    ticktext = [period['label'] for period in periods]

    for axis_row in (1, 2, 3):
        fig.update_xaxes(
            range=[view_start, view_end],
            fixedrange=True,
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
            line_color=PERIOD_RULE,
            line_dash='solid',
        )
    fig.add_vline(
        x=game_end,
        line_width=1,
        line_color=PERIOD_RULE,
        line_dash='solid',
    )
    if playhead is not None:
        fig.add_vline(
            x=playhead,
            line_width=2,
            line_color=BRAVES_BLUE_PRIMARY,
            line_dash='solid',
        )

    for run in runs:
        is_home = run['side'] == 'home'
        fill = HOME_RUN_FILL if is_home else AWAY_RUN_FILL
        text_color = BRAVES_BLUE_PRIMARY if is_home else ZERO_LINE
        fig.add_vrect(
            x0=run['start'],
            x1=run['end'],
            fillcolor=fill,
            opacity=1.0,
            layer='below',
            line_width=0,
        )

        x_center = (run['start'] + run['end']) / 2
        pts_label = f"{run['home_pts']}-{run['away_pts']}" if is_home else f"{run['away_pts']}-{run['home_pts']}"
        on_top = not is_home
        y_pos = span if on_top else -span
        y_anchor = 'bottom' if on_top else 'top'
        y_shift = 2 if on_top else -2

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
        dragmode=False,
        barmode='overlay',
        margin=dict(l=112, r=112, t=FIGURE_MARGIN_T, b=FIGURE_MARGIN_B),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=LABEL_COLOR, size=12),
        hovermode='closest',
        uirevision=uirevision if uirevision is not None else 'full',
    )

    add_mirrored_categories_axis(
        fig, 'yaxis4', 'y', 'x', away_labels,
        x_val=view_start, ExplicitRange=True, kill_row=KILL_ROW,
    )
    add_mirrored_numbers_axis(
        fig, 'yaxis5', 'yaxis2', 'y2', 'x2', x_val=view_start,
    )
    add_mirrored_categories_axis(
        fig, 'yaxis6', 'y3', 'x3', home_labels,
        x_val=view_start, ExplicitRange=True, kill_row=KILL_ROW,
    )
    _add_kill_annotations(fig)
    _add_stop_counts(fig, kills, periods, format_kill_label_fn)
    _raise_bottom_title(fig)
    return fig


def report_rotation_figure(payload):
    fig = build_rotation_figure(
        payload,
        playhead=None,
        show_dnp=False,
    )
    fig.update_layout(
        font=dict(size=12, color=LABEL_COLOR),
        margin=dict(l=112, r=112, t=FIGURE_MARGIN_T, b=FIGURE_MARGIN_B),
    )
    _raise_bottom_title(fig)
    return fig


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
    """Split an hv step at zero. The jump stays on the later x."""
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
        gridcolor=BORDER_SLATE,
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

    if show_opponent:
        add_mirrored_categories_axis(fig, 'yaxis4', 'y', 'x', top_y, autorange='reversed')
        add_mirrored_numbers_axis(fig, 'yaxis5', 'yaxis2', 'y2', 'x2')
        add_mirrored_categories_axis(fig, 'yaxis6', 'y3', 'x3', bottom_y, autorange='reversed')
    else:
        add_mirrored_categories_axis(fig, 'yaxis3', 'y', 'x', top_y, autorange='reversed')
        add_mirrored_numbers_axis(fig, 'yaxis4', 'yaxis2', 'y2', 'x2')
    for ann in fig.layout.annotations or []:
        if not ann.text:
            continue
        ann.font = dict(size=14, color=TITLE_COLOR)
    return fig
