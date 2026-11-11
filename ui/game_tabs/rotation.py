# -*- coding: utf-8 -*-
import os

from dash import dcc, html, no_update
import dash_mantine_components as dmc

from synergy_inbounder.game_status import is_finished_status, is_live_play_status
from synergy_reporter.rotation import (
    build_rotation_figure,
    format_run_label,
    live_playhead_t,
)
from ui.components import loading_skeleton
from ui.game_tabs.common import (
    _empty_view,
    _error_view,
    _game_module,
    _last_update_span,
    safe_loads,
)

ROTATION_GRAPH_CONFIG = {
    'displayModeBar': False,
    'responsive': True,
    'scrollZoom': False,
    'doubleClick': False,
}

DEFAULT_ROTATION_VIEW = {
    't': None,
    'show_dnp': False,
    'follow_live': True,
    'saw_live': False,
    'finished_reset': False,
}


def _rotation_controls():
    return dmc.Group(
        [
            dmc.Button(
                'Live',
                id='rotation-live',
                size='compact-xs',
                variant='filled',
                color='blue',
                radius='sm',
                style={'display': 'none'},
            ),
            dmc.Switch(
                id='rotation-show-dnp',
                label='Show DNP',
                checked=False,
                size='sm',
                color='gray',
                ms='auto',
            ),
        ],
        justify='flex-start',
        align='center',
        mb='sm',
        wrap='wrap',
        gap='sm',
        w='100%',
    )


def _rotation_graph_paper():
    return dmc.Paper(
        dcc.Graph(
            id='rotation-graph',
            figure={},
            config=ROTATION_GRAPH_CONFIG,
            style={'width': '100%', 'height': '520px'},
        ),
        id='rotation-graph-paper',
        withBorder=True,
        radius='md',
        shadow='xs',
        className='braves-card-wrapper',
        style={'overflow': 'hidden', 'display': 'none'},
    )


def _rotation_wrap(hidden=True):
    style = {'display': 'none'} if hidden else {}
    pane = html.Div(id='pane-rotation', children=loading_skeleton('chart'))
    if os.environ.get('SPLASHBOARD_E2E'):
        body = pane
    else:
        body = dcc.Loading(custom_spinner=loading_skeleton('chart'), children=pane)
    return html.Div(
        [
            html.Div(id='rotation-last-update', children=_last_update_span()),
            _rotation_controls(),
            body,
            _rotation_graph_paper(),
        ],
        id='wrap-rotation',
        style=style,
    )


def _rotation_view(view_store):
    data = view_store if isinstance(view_store, dict) else safe_loads(view_store)
    merged = dict(DEFAULT_ROTATION_VIEW)
    if isinstance(data, dict):
        for key in DEFAULT_ROTATION_VIEW:
            if key in data:
                merged[key] = data[key]
    return merged


def _rotation_chip(label, kind, index, side):
    return dmc.Button(
        label,
        id={'type': kind, 'index': index},
        color='blue' if side == 'home' else 'gray',
        variant='light' if kind == 'rotation-run' else 'outline',
        size='compact-xs',
        radius='sm',
        px=8,
    )


def _render_run_buttons(runs, periods):
    items = []
    for index, run in enumerate(runs or []):
        items.append((run.get('start') or 0, index, run))
    if not items:
        return None
    items.sort(key=lambda item: item[0])
    buttons = [
        _rotation_chip(
            format_run_label(run, periods),
            'rotation-run',
            index,
            run.get('side'),
        )
        for _start, index, run in items
    ]
    return dmc.Group(
        buttons,
        gap=6,
        mb='sm',
        w='100%',
        style={'flexWrap': 'wrap'},
    )


def resolve_rotation_playhead(payload, view, match_info_store=None):
    info = match_info_store if isinstance(match_info_store, dict) else safe_loads(match_info_store)
    live = is_live_play_status(info.get('status'))
    periods = (payload or {}).get('periods') or []
    if live and view.get('follow_live', True):
        return live_playhead_t(payload)
    playhead = view.get('t')
    if playhead is not None:
        return playhead
    if live:
        return live_playhead_t(payload)
    if is_finished_status(info.get('status')) and periods:
        return periods[0]['start']
    if periods:
        return periods[-1]['end']
    return None


def _rotation_figure_from_view(payload, view, match_info_store=None):
    playhead = resolve_rotation_playhead(payload, view, match_info_store)
    uirevision = 'dnp' if view.get('show_dnp') else 'roster'
    mod = _game_module()
    fig_fn = getattr(mod, 'build_rotation_figure', build_rotation_figure)
    return fig_fn(
        payload,
        playhead=playhead,
        show_dnp=bool(view.get('show_dnp')),
        uirevision=uirevision,
    )


def render_rotation_children(rotation_store, view_store=None, match_info_store=None):
    if rotation_store is None:
        return [loading_skeleton('chart')]
    payload = safe_loads(rotation_store)
    if payload.get('_ui') == 'waiting':
        return [loading_skeleton('chart')]
    if payload.get('_ui') == 'error':
        return [_error_view(payload)]
    if not payload or not payload.get('teams'):
        return [_empty_view()]
    runs = payload.get('runs') or []
    periods = payload.get('periods') or []
    runs_row = _render_run_buttons(runs, periods)
    if runs_row is not None:
        return [runs_row]
    return []


def apply_rotation_view_event(
    triggered_id,
    show_dnp,
    run_clicks,
    click_t,
    rotation_store,
    game_id,
    view_store,
    match_info_store,
):
    view = _rotation_view(view_store)
    if triggered_id == 'game_id':
        return dict(DEFAULT_ROTATION_VIEW)
    payload = safe_loads(rotation_store)
    periods = payload.get('periods') or []
    runs = payload.get('runs') or []

    if triggered_id == 'rotation-live':
        view['follow_live'] = True
        view['t'] = live_playhead_t(payload)
        return view

    if triggered_id == 'rotation-show-dnp':
        checked = bool(show_dnp)
        if checked == bool(view.get('show_dnp')):
            return no_update
        view['show_dnp'] = checked
        return view

    if isinstance(triggered_id, dict) and triggered_id.get('type') == 'rotation-run':
        index = triggered_id.get('index')
        clicks = run_clicks or []
        if not clicks or not any(clicks):
            return no_update
        if not isinstance(index, int) or index < 0 or index >= len(runs):
            return no_update
        run = runs[index]
        view['t'] = run['start']
        view['follow_live'] = False
        return view

    if triggered_id == 'rotation-click-t':
        if click_t is None:
            return no_update
        try:
            t_val = float(click_t)
        except (TypeError, ValueError):
            return no_update
        game_end = periods[-1]['end'] if periods else None
        if game_end is not None:
            t_val = min(max(0.0, t_val), float(game_end))
        view['t'] = t_val
        view['follow_live'] = False
        return view

    if triggered_id in ('rotation_store', 'match_info_store'):
        info = match_info_store if isinstance(match_info_store, dict) else safe_loads(match_info_store)
        status = info.get('status')
        if is_live_play_status(status):
            changed = False
            if not view.get('saw_live'):
                view['saw_live'] = True
                changed = True
            if view.get('follow_live', True):
                now = live_playhead_t(payload)
                if now != view.get('t'):
                    view['t'] = now
                    changed = True
            return view if changed else no_update
        if (
            is_finished_status(status)
            and view.get('saw_live')
            and not view.get('finished_reset')
        ):
            view['t'] = None
            view['follow_live'] = False
            view['finished_reset'] = True
            return view
        return no_update

    return no_update
