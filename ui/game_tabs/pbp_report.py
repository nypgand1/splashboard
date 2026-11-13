# -*- coding: utf-8 -*-
import io
import json

import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd

from synergy_inbounder.logs import payload as log_payload
from synergy_inbounder.runtime_cache import get_cached_report
from synergy_reporter.report_components import render_report_workspace
from synergy_reporter.report_layout import default_layout
from synergy_reporter.rotation import report_rotation_figure
from synergy_reporter.shot_chart import report_shot_chart_payload
from ui.components import loading_skeleton
from ui.game_tabs.common import (
    _empty_view,
    _error_view,
    _game_module,
    _last_update_span,
    _pbp_split_text,
    safe_loads,
)
from ui.tables.ag_grid import _PLAYER_NAME_COMPARATOR


def _open_report_proxy(*args, **kwargs):
    mod = _game_module()
    if mod is not None and hasattr(mod, '_open_report'):
        return mod._open_report(*args, **kwargs)
    kwargs['pin'] = 'open'
    return get_cached_report(*args, **kwargs)


def render_pbp_children(pbp_store, game_id=None, organization_id=None):
    if pbp_store is None:
        return [loading_skeleton('table')]
    payload = safe_loads(pbp_store)
    if payload.get('_ui') == 'waiting':
        return [loading_skeleton('table')]
    if payload.get('_ui') == 'error':
        return [_error_view(payload)]
    raw = _pbp_split_text(pbp_store)
    parsed = safe_loads(raw)
    if not parsed or 'columns' not in parsed:
        return [_empty_view()]
    pbp_df = pd.read_json(io.StringIO(raw), orient='split')
    if pbp_df.empty:
        return [_empty_view()]
    team_name_list = pbp_df['Team'].dropna().unique() if 'Team' in pbp_df.columns else []
    col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'Team', 'Player', 'eventType', 'subType', 'success', 'scores']
    col_list.extend(team_name_list)
    col_list = [c for c in col_list if c in pbp_df.columns]
    pbp_df = pbp_df[col_list][::-1]
    column_defs = []
    for column in pbp_df.columns:
        col_def = {
            "field": column,
            "headerClass": "ag-header-align-center",
            "cellClass": "ag-cell-align-center",
            "cellStyle": {"textAlign": "center"},
            "suppressMovable": True,
        }
        if column == 'Player':
            col_def['comparator'] = _PLAYER_NAME_COMPARATOR
        column_defs.append(col_def)
    grid = dag.AgGrid(
        rowData=pbp_df.to_dict('records'),
        columnDefs=column_defs,
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "suppressMovable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "domLayout": "autoHeight", "suppressMovableColumns": True},
        columnSize="autoSize",
        className="ag-theme-alpine braves-clean-ag-grid",
        style={'width': '100%'},
    )
    return [_last_update_span(game_id, organization_id), dmc.Paper(grid, withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden"})]


def _report_org(match_info):
    info = match_info or {}
    return info.get('organization_id')


def _report_rotation_figure_json(game_id, match_info):
    if not game_id:
        return json.dumps({'_ui': 'empty'})
    try:
        mod = _game_module()
        fig_fn = getattr(mod, 'report_rotation_figure', report_rotation_figure)
        report = _open_report_proxy(game_id, _report_org(match_info))
        payload = report.get_rotation_payload(
            home_team_id=(match_info or {}).get('home_team_id'),
            away_team_id=(match_info or {}).get('away_team_id'),
        )
        if not isinstance(payload, dict) or payload.get('_ui') == 'error':
            return json.dumps({'_ui': 'error'})
        if not payload.get('teams'):
            return json.dumps({'_ui': 'empty'})
        return fig_fn(payload).to_json()
    except Exception:
        log_payload.exception('report rotation payload failed game=%s', game_id)
        return json.dumps({'_ui': 'error'})


def _report_shot_chart_json(game_id, match_info):
    if not game_id:
        return json.dumps({'_ui': 'empty'})
    info = match_info or {}
    try:
        mod = _game_module()
        payload_fn = getattr(mod, 'report_shot_chart_payload', report_shot_chart_payload)
        report = _open_report_proxy(game_id, _report_org(info))
        payload = payload_fn(
            report.get_play_by_play_df(),
            info.get('away_team_id'),
            info.get('home_team_id'),
            info.get('away_team') or 'Away',
            info.get('home_team') or 'Home',
            fixture_id=game_id,
        )
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        log_payload.exception('report shot chart payload failed game=%s', game_id)
        return json.dumps({'_ui': 'error'})


def render_report_children(bs_store, lineup_store, match_info_store, game_id=None):
    bs_dict = safe_loads(bs_store) if bs_store else {}
    match_info = safe_loads(match_info_store) if match_info_store else {}
    mod = _game_module()
    layout_fn = getattr(mod, 'default_layout', default_layout)
    workspace_fn = getattr(mod, 'render_report_workspace', render_report_workspace)
    rot_json_fn = getattr(mod, '_report_rotation_figure_json', _report_rotation_figure_json)
    shot_json_fn = getattr(mod, '_report_shot_chart_json', _report_shot_chart_json)
    layout = layout_fn(match_info)
    if bs_dict.get('_ui') == 'error':
        return [_error_view(bs_dict)]
    if not bs_dict or not bs_dict.get('qt_pts_df'):
        return [_empty_view()]
    return [
        _last_update_span(game_id, match_info.get('organization_id')),
        workspace_fn(
            layout,
            bs_dict,
            lineup_store,
            match_info,
            game_id,
            rotation_json=rot_json_fn(game_id, match_info),
            shot_chart_json=shot_json_fn(game_id, match_info),
        ),
    ]
