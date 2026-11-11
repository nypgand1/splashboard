# -*- coding: utf-8 -*-
import io
import json
import os
import sys

from dash import dcc, html
import pandas as pd

from synergy_inbounder.logs import data as log_data
from synergy_inbounder.runtime_cache import report_refresh_state
from ui.components import (
    EMPTY_GAME,
    EMPTY_GAME_NEXT,
    ERROR_GAME,
    empty_state,
    error_alert,
    last_update_line,
    loading_skeleton,
)


def _game_module():
    return sys.modules.get('pages.game')


def safe_loads(val):
    if val is None:
        return {}
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except Exception as exc:
            log_data.debug('store json parse failed: %s', exc)
            return {}
        if isinstance(parsed, (dict, list)):
            return parsed
    return {}


def _error_store(message=None, game_id=None):
    payload = {
        '_ui': 'error',
        'message': message or ERROR_GAME,
    }
    if game_id is not None:
        payload['game_id'] = game_id
    return json.dumps(payload)


def _last_update_span(game_id=None, organization_id=None, box=False):
    label = None
    delayed = False
    if game_id:
        mod = _game_module()
        refresh_fn = getattr(mod, 'report_refresh_state', report_refresh_state)
        state = refresh_fn(game_id, organization_id)
        if box and state.get('stats_delayed'):
            label = state.get('stats_label')
            delayed = True
        elif box:
            label = state.get('stats_label') or state.get('label')
            delayed = bool(state.get('delayed'))
        else:
            label = state.get('label')
            delayed = bool(state.get('delayed'))
    return last_update_line(label, delayed=delayed)


def _empty_view():
    return empty_state(EMPTY_GAME, EMPTY_GAME_NEXT)


def _error_view(payload=None):
    data = payload if isinstance(payload, dict) else safe_loads(payload)
    return error_alert(data.get('message') or ERROR_GAME)


def _pane(wrap_id, pane_id, kind, hidden=False):
    body = html.Div(id=pane_id, children=loading_skeleton(kind))
    style = {'display': 'none'} if hidden else {}
    if os.environ.get('SPLASHBOARD_E2E'):
        return html.Div(body, id=wrap_id, style=style)
    return html.Div(
        dcc.Loading(custom_spinner=loading_skeleton(kind), children=body),
        id=wrap_id,
        style=style,
    )


def _pbp_split_text(pbp_store):
    if pbp_store is None:
        return None
    payload = pbp_store if isinstance(pbp_store, dict) else safe_loads(pbp_store)
    if isinstance(payload, dict) and 'frame' in payload and 'generation' in payload:
        frame = payload['frame']
        return frame if isinstance(frame, str) else json.dumps(frame)
    if isinstance(pbp_store, str):
        return pbp_store
    if isinstance(payload, dict):
        return json.dumps(payload)
    return None


def _pbp_frame(pbp_store):
    if pbp_store is None:
        return 'loading', None
    payload = pbp_store if isinstance(pbp_store, dict) else safe_loads(pbp_store)
    if not isinstance(payload, dict) or not payload:
        return 'empty', None
    if payload.get('_ui') == 'waiting':
        return 'loading', None
    if payload.get('_ui') == 'error':
        return 'error', None
    raw = _pbp_split_text(pbp_store)
    parsed = safe_loads(raw)
    if not isinstance(parsed, dict) or 'columns' not in parsed or 'data' not in parsed:
        return 'empty', None
    try:
        frame = pd.read_json(io.StringIO(raw), orient='split')
    except (ValueError, TypeError):
        return 'empty', None
    if frame.empty:
        return 'empty', None
    return 'ready', frame
