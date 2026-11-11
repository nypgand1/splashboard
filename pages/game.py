import datetime
import io
import json
import os

from dash import ALL, ctx, dcc, html, Input, Output, State, callback, register_page, clientside_callback, no_update
import dash_mantine_components as dmc
import dash_ag_grid as dag
import pandas as pd

from synergy_inbounder.communicator import LiveBudgetWait, SynergyAuthError
from synergy_inbounder.logs import auth as log_auth
from synergy_inbounder.logs import data as log_data
from synergy_inbounder.logs import payload as log_payload
from synergy_inbounder.logs import unexpected as log_unexpected
from synergy_inbounder.live_clock import scoreboard_from_pbp_frame
from synergy_inbounder.names import display_name
from synergy_inbounder.settings import organization_for_league, season_ids_for_organization
from synergy_inbounder.parser import Parser
from synergy_inbounder.runtime_cache import (
    LIVE_CADENCE_SECONDS,
    get_cached_report,
    lookup_game_status,
    report_generation,
    report_refresh_state,
    warmup_game_report,
)


def _open_report(*args, **kwargs):
    """Game page reads and pins the open fixture frame."""
    kwargs['pin'] = 'open'
    return get_cached_report(*args, **kwargs)
from synergy_inbounder.game_status import (
    is_finished_status,
    is_live_play_status,
    status_bucket,
)
from synergy_reporter.column_winners import winning_indexes
from synergy_reporter.report_components import (
    apply_page_cmd,
    lineup_tables_for_size,
    read_split_frame,
    render_report_workspace,
)
from synergy_reporter.report_layout import (
    default_layout,
    report_tab_is_visible,
)
from synergy_reporter.rotation import (
    build_rotation_figure,
    format_run_label,
    live_playhead_t,
    report_rotation_figure,
)
from synergy_reporter.matchups import matchup_grid_records
from synergy_reporter.team_order import (
    order_named_items,
    order_team_frame,
    section_dot,
    side_names,
    team_stripe,
)
from synergy_reporter.shot_chart import (
    COURT_IMAGE_STYLE,
    court_data_uri,
    court_zones,
    period_chips as shot_period_chips,
    player_options,
    report_shot_chart_payload,
)
from ui_kit import (
    EMPTY_GAME,
    EMPTY_GAME_NEXT,
    EMPTY_MATCHUPS,
    ERROR_GAME,
    REFRESH_DELAYED,
    empty_state,
    error_alert,
    filter_control,
    game_banner,
    icon,
    loading_skeleton,
    shot_chart_paper,
    shot_court_column,
)
from ui.game_tabs.box_score import (
    BS_SYNC_KEYS,
    _BS_BAR,
    _BS_HIDE,
    _BS_SHOW,
    _bs_blank,
    _bs_frames,
    _bs_player_outputs,
    _bs_shell,
    _format_metric,
    _player_grid_options,
    _player_model,
    _row_id_records,
    _table_children,
    box_score_screen,
    box_score_sync_values,
    period_bar_state,
    render_bs_children,
    render_bs_sections,
    resolve_bs_period,
)
from ui.game_tabs.common import (
    _empty_view,
    _error_store,
    _error_view,
    _last_update_span,
    _pane,
    _pbp_frame,
    _pbp_split_text,
    safe_loads,
)
from ui.game_tabs.lineup_matchups import (
    _lineup_controls,
    _lineup_wrap,
    _matchup_wrap,
    matchup_team_value,
    render_lineup_children,
)
from ui.game_tabs.pbp_report import (
    _report_org,
    _report_rotation_figure_json,
    _report_shot_chart_json,
    render_pbp_children,
    render_report_children,
)
from ui.game_tabs.rotation import (
    DEFAULT_ROTATION_VIEW,
    ROTATION_GRAPH_CONFIG,
    _render_run_buttons,
    _rotation_chip,
    _rotation_controls,
    _rotation_figure_from_view,
    _rotation_graph_paper,
    _rotation_view,
    _rotation_wrap,
    apply_rotation_view_event,
    render_rotation_children,
    resolve_rotation_playhead,
)
from ui.game_tabs.shot_chart import (
    _court_image,
    _shot_chart_court,
    _shot_chart_wrap,
    resolve_shot_chart_filters,
    shot_chart_outputs,
    shot_chart_panel,
    shot_chart_period_state,
    shot_chart_player_state,
)
from ui.tables.ag_grid import (
    DESC_FIRST_SORT,
    LINEUP_COL_SIZES,
    _DESC_SORT_FIELDS,
    _LINEUP_FIT_EVENTS,
    _LINEUP_POST_SORT,
    _PLAYER_NAME_COMPARATOR,
    _ag_grid_from_df,
    _append_def_class,
    _apply_click_sort,
    _apply_click_sort_columns,
    _apply_lineup_pair_columns,
    _apply_matchup_pair_columns,
    _build_stats_column_defs,
    _display_cell,
    _lineup_col_size,
    _lineup_pair_comparator,
    _lineup_pair_records,
    _lineup_visible_columns,
    _lock_column_move,
    _mark_ag_group_edges,
    _matchup_column_defs,
    _matchup_grid,
    _numeric_rank_js,
    _stamp_designed_widths,
)
from ui.tables.stat_cards import (
    ADVANCED_CARD_TITLE,
    KEY_CARD_TITLE,
    KEY_STAT_GROUPS as _KEY_STAT_GROUPS,
    KEY_STAT_LEAVES as _KEY_STAT_LEAVES,
    PACE_CARD_TITLE,
    boundary_columns as _boundary_columns,
    dmc_table_from_df as _dmc_table_from_df,
    parse_numeric_stat as _parse_numeric_stat,
    scroll_card_paper as _bs_scroll_card,
    stat_header_label as _stat_header,
    stat_th as _th,
)

register_page(
    __name__,
    name='Splashboard TFB | Game',
    top_nav=True,
    path_template='/game/<league>/<game_id>'
)


def _bs_player_block(index, dot_color):
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.Box(style={
                        'width': '8px',
                        'height': '8px',
                        'borderRadius': '50%',
                        'backgroundColor': dot_color,
                    }),
                    dmc.Text('', id=f'bs-player-title-{index}', fw=800, fz='16px'),
                ],
                gap=8,
                align='center',
                mt='md',
                mb=10,
            ),
            dmc.Paper(
                dag.AgGrid(
                    id=f'bs-player-grid-{index}',
                    rowData=[],
                    columnDefs=[],
                    defaultColDef={
                        'sortable': True,
                        'filter': False,
                        'resizable': True,
                        'suppressMovable': True,
                        'cellClassRules': {'ag-sorted-col-bg': 'params.column.isSortActive()'},
                        'cellDataType': False,
                    },
                    dashGridOptions={
                        'domLayout': 'autoHeight',
                        'suppressHorizontalScroll': False,
                        'suppressMovableColumns': True,
                        'enableBrowserTooltips': True,
                        'tooltipShowDelay': 200,
                    },
                    className='ag-theme-alpine braves-clean-ag-grid',
                    style={'width': '100%'},
                    getRowId='params.data._row',
                ),
                id=f'bs-player-wrap-{index}',
                withBorder=True,
                radius='md',
                shadow='xs',
                mb='md',
                className='braves-grid-wrap',
                style={'overflowX': 'auto'},
            ),
        ],
        id=f'bs-player-block-{index}',
    )


def _box_score_wrap():
    matrix = html.Div(
        [
            html.Div(loading_skeleton('cards'), id='bs-skeleton'),
            html.Div(id='bs-status', style={'display': 'none'}),
            html.Div(
                [
                    html.Div(id='bs-last-update'),
                    dmc.SimpleGrid(
                        cols={"base": 1, "lg": 3},
                        spacing='12px',
                        children=[
                            _bs_scroll_card('bs-score-scroll', 'Score'),
                            _bs_scroll_card('bs-fouls-scroll', 'Fouls'),
                            _bs_scroll_card('bs-tout-scroll', 'Timeouts'),
                        ],
                        style={'marginBottom': '12px'},
                    ),
                ],
                id='bs-matrix-body',
                style={'display': 'none'},
            ),
        ],
        id='bs-matrix',
    )
    bar = dmc.Group(
        [
            dmc.SegmentedControl(
                id='bs-period-control',
                data=[{'label': 'All', 'value': 'all'}],
                value='all',
                radius='md',
                size='xs',
            ),
        ],
        id='bs-period-bar',
        mb='sm',
        wrap='wrap',
        gap='sm',
        style={'display': 'none'},
    )
    detail = html.Div(
        html.Div(
            [
                dmc.SimpleGrid(
                    cols={"base": 1, "lg": 2},
                    spacing='12px',
                    children=[
                        _bs_scroll_card('bs-pace-scroll', PACE_CARD_TITLE),
                        _bs_scroll_card('bs-advanced-scroll', ADVANCED_CARD_TITLE),
                    ],
                    style={'marginBottom': '12px'},
                ),
                dmc.Box(
                    _bs_scroll_card('bs-key-scroll', KEY_CARD_TITLE),
                    mb='sm',
                ),
                dmc.Box(_bs_scroll_card('bs-team-scroll'), mb='sm'),
                _bs_player_block(0, '#94a3b8'),
                _bs_player_block(1, '#00b4d8'),
            ],
            id='bs-detail-body',
            style={'display': 'none'},
        ),
        id='bs-detail',
    )
    body = html.Div(id='pane-bs', children=[matrix, bar, detail])
    return html.Div(body, id='wrap-bs')


def layout(game_id=None, league='plg'):
    return html.Div([
        html.Div([
            html.Span(id='game_league', children=league, hidden=True),
            html.Span(id='game_id', children=game_id, hidden=True),
        ]),
        
        # Game Info Banner Card (visible across all tabs)
        html.Div(id='game-info-banner-wrap'),

        dmc.Tabs(
            [
                dmc.TabsList(
                    [
                        dmc.TabsTab("Box Score", value="tab-bs", leftSection=icon("tabler:table", width=14)),
                        dmc.TabsTab("Rotation", value="tab-rotation", leftSection=icon("tabler:chart-bar", width=14)),
                        dmc.TabsTab("Shot Chart", value="tab-shot-chart", leftSection=icon("tabler:ball-basketball", width=14)),
                        dmc.TabsTab("Lineup Stats", value="tab-lineup", leftSection=icon("tabler:users", width=14)),
                        dmc.TabsTab("Matchups", value="tab-matchups", leftSection=icon("tabler:users-group", width=14)),
                        dmc.TabsTab("Play-By-Play", value="tab-pbp", leftSection=icon("tabler:list-numbers", width=14)),
                        dmc.TabsTab(
                            "Report",
                            value="tab-report",
                            id="report-tab",
                            leftSection=icon("tabler:file-text", width=14),
                            style={"display": "none"},
                        ),
                    ],
                )
            ],
            id="tabs",
            value="tab-bs",
            variant="default",
            className="braves-clean-tabs",
            style={
                "margin": "0 0 16px 0",
                "padding": "0",
                "borderBottom": "none",
            }
        ),
        
        _box_score_wrap(),
        _rotation_wrap(hidden=True),
        _shot_chart_wrap(hidden=True),
        _pane('wrap-pbp', 'pane-pbp', 'table', hidden=True),
        _lineup_wrap(hidden=True),
        _matchup_wrap(hidden=True),
        _pane('wrap-report', 'pane-report', 'table', hidden=True),
        html.Div(id='pbp_table', style={'display': 'block'}),
        
        # Background Stores & Intervals
        dcc.Interval(
            id='interval-component',
            interval=LIVE_CADENCE_SECONDS * 1000,
            n_intervals=0
        ),
        dcc.Store(id='bs_store'),
        dcc.Store(id='bs-period', data='all'),
        dcc.Store(id='bs-player-columns'),
        dcc.Store(id='bs-view-reset'),
        dcc.Store(id='pbp_store'),
        dcc.Store(id='lineup_store'),
        dcc.Store(id='lineup-show-opp-sync'),
        dcc.Store(id='matchup_store'),
        dcc.Store(id='rotation_store'),
        dcc.Store(id='rotation-click-t'),
        html.Button(id='rotation-click-fire', n_clicks=0, style={'display': 'none'}),
        dcc.Store(id='rotation_view_store', data={
            't': None,
            'show_dnp': False,
            'follow_live': True,
            'saw_live': False,
            'finished_reset': False,
        }),
        dcc.Store(id='match_info_store'),
        # Dash hashes allow_duplicate outputs from Inputs only. Nothing writes
        # this store; it keeps the finished publisher off the live callbacks' hash.
        dcc.Store(
            id='finished-snapshot-sentinel',
            data='finished',
            storage_type='memory',
        ),
        dcc.Store(id='report-pane-ready', data=''),
        
        # Dummy grid to force Dash to load AG Grid JS/CSS resources on initial load
        html.Div(dag.AgGrid(id="dummy-grid", rowData=[], columnDefs=[]), style={'display': 'none'})
    ])



def _organization(league):
    return organization_for_league(league)


def _triggered_id():
    try:
        return ctx.triggered_id
    except Exception as exc:
        log_data.debug('triggered id unavailable: %s', exc)
        return None


def _is_game_load(n_intervals, triggered):
    """A load is a game or league change, or the callback before the interval ticks."""
    if triggered in ('game_id', 'game_league'):
        return True
    return not isinstance(n_intervals, int) or n_intervals == 0


def _fixture_status(game_id, org):
    return lookup_game_status(game_id, org)


def _report_slot(report, name):
    """Return ``(present, value)`` for a real attribute. Misses Mock children."""
    try:
        data = object.__getattribute__(report, '__dict__')
    except Exception:
        return False, None
    if not isinstance(data, dict) or name not in data:
        return False, None
    return True, data[name]


def _store_slot(report, name, value):
    try:
        data = object.__getattribute__(report, '__dict__')
    except Exception as exc:
        log_data.debug('report memo skipped: %s', exc)
        return
    if isinstance(data, dict):
        data[name] = value


def _memo_unlocked(report, name, builder):
    present, cached = _report_slot(report, name)
    if present and cached is not None:
        return cached
    value = builder()
    _store_slot(report, name, value)
    return value


def _memo_on_report(report, name, builder):
    """Return a cached raw payload. A second caller waits out the first build."""
    present, lock = _report_slot(report, '_derive_lock')
    if present and lock is not None:
        with lock:
            return _memo_unlocked(report, name, builder)
    return _memo_unlocked(report, name, builder)


def _box_dict(report, game_id):
    _, cached = _report_slot(report, '_box_dict')
    if isinstance(cached, dict) and cached.get('game_id') == game_id:
        return cached

    def build():
        return {
            'game_id': game_id,
            'qt_pts_df': report.get_period_team_pts_df().to_json(date_format='iso', orient='split'),
            'qt_foul_df': report.get_period_team_fouls_df().to_json(date_format='iso', orient='split'),
            'qt_tout_df': report.get_period_team_timeout_df().to_json(date_format='iso', orient='split'),
            't_adv_df': report.get_team_advance_stats_df().to_json(date_format='iso', orient='split'),
            'adv_df': report.get_team_advanced_df().to_json(date_format='iso', orient='split'),
            't_df': report.get_team_stats_df().to_json(date_format='iso', orient='split'),
            'k_df': report.get_team_key_stats_df().to_json(date_format='iso', orient='split'),
            'p_df_dict': report.get_player_stats_json_dict(),
            'p_summary_dict': report.get_player_box_score_summary_json_dict(),
            'period_chips': report.box_score_period_chips() if hasattr(report, 'box_score_period_chips') else [],
            'slices': report.box_score_slice_json() if hasattr(report, 'box_score_slice_json') else {},
        }

    value = _memo_on_report(report, '_box_dict', build)
    if isinstance(value, dict) and value.get('game_id') != game_id:
        return build()
    return value


def _box_payload(report, game_id):
    return json.dumps(_box_dict(report, game_id))


def _pbp_split_json(report):
    def build():
        return report.get_play_by_play_df().to_json(date_format='iso', orient='split')
    return _memo_on_report(report, '_pbp_split_json', build)


def _lineup_dict(report):
    return _memo_on_report(
        report,
        '_lineup_store_dict',
        lambda: report.get_all_lineup_stats_json_dict(sizes=(5,)),
    )


def _lineup_payload(report):
    return json.dumps(_lineup_dict(report))


def _matchup_dict(report, info):
    if not info.get('home_team_id') or not info.get('away_team_id'):
        return {}
    key = (str(info.get('home_team_id')), str(info.get('away_team_id')))
    _, cached = _report_slot(report, '_matchup_store_dict')
    _, cached_key = _report_slot(report, '_matchup_store_key')
    if cached is not None and cached_key == key:
        return cached
    data = report.get_matchup_payload(
        home_team_id=info.get('home_team_id'),
        away_team_id=info.get('away_team_id'),
    )
    _store_slot(report, '_matchup_store_dict', data)
    _store_slot(report, '_matchup_store_key', key)
    return data


def _matchup_payload(report, info):
    return json.dumps(_matchup_dict(report, info))


def _rotation_dict(report, info):
    key = (str(info.get('home_team_id')), str(info.get('away_team_id')))
    _, cached = _report_slot(report, '_rotation_store_dict')
    _, cached_key = _report_slot(report, '_rotation_store_key')
    if cached is not None and cached_key == key:
        return cached
    data = report.get_rotation_payload(
        home_team_id=info.get('home_team_id'),
        away_team_id=info.get('away_team_id'),
    )
    _store_slot(report, '_rotation_store_dict', data)
    _store_slot(report, '_rotation_store_key', key)
    return data


def _rotation_payload(report, info):
    return json.dumps(_rotation_dict(report, info))


def _paint_info(match_info, game_id, league):
    """Names for a paint. The fixture row fills a banner that has not arrived."""
    info = match_info if isinstance(match_info, dict) else safe_loads(match_info)
    if not isinstance(info, dict):
        info = {}
    ready = (
        info.get('home_team') and info.get('away_team')
        and info.get('home_team_id') and info.get('away_team_id')
        and info.get('organization_id')
    )
    if ready or not game_id:
        return info
    org = info.get('organization_id') or _organization(league)
    if not org:
        return info
    try:
        fresh = _info_dict(org, game_id) or {}
    except Exception as exc:
        log_data.debug('fixture names unavailable: %s', exc)
        return info
    if not isinstance(fresh, dict):
        return info
    merged = dict(fresh)
    for key, value in info.items():
        if value not in (None, ''):
            merged[key] = value
    return merged


def _info_dict(org, game_id):
    row = Parser.find_game_row(org, game_id, season_ids_for_organization(org))
    if row is None:
        return None
    id_table = Parser.parse_id_tables(org)
    dt_str = str(row['startTimeLocal'])
    try:
        dt = pd.to_datetime(dt_str)
        date_display = dt.strftime('%Y-%m-%d')
        time_display = dt.strftime('%H:%M')
    except Exception as exc:
        log_data.debug('fixture start time parse failed: %s', exc)
        date_display = dt_str
        time_display = ''
    home_id = row.get('teamIdHome')
    away_id = row.get('teamIdAway')
    return {
        'date': date_display,
        'time': time_display,
        'venue': display_name(id_table, row.get('venueId')),
        'home_team': display_name(id_table, home_id),
        'away_team': display_name(id_table, away_id),
        'home_team_id': None if pd.isna(home_id) else str(home_id),
        'away_team_id': None if pd.isna(away_id) else str(away_id),
        'home_score': str(row.get('teamScoreHome', '')),
        'away_score': str(row.get('teamScoreAway', '')),
        'status': str(row.get('status', '')).strip(),
        'organization_id': org,
    }


def _success_text(previous):
    """Return the previous store text when it is a painted success."""
    if previous is None:
        return None
    kept = safe_loads(previous)
    if not isinstance(kept, dict) or kept.get('_ui') in ('error', 'waiting'):
        return None
    useful = (
        kept.get('status')
        or kept.get('qt_pts_df')
        or kept.get('columns')
        or kept.get('frame')
        or kept.get('pairs')
        or kept.get('teams')
        or kept.get('generation')
        or any(str(key).isdigit() for key in kept)
    )
    if not useful:
        return None
    return previous if isinstance(previous, str) else json.dumps(kept)


def _keep_previous(previous, game_id=None):
    kept = _success_text(previous)
    if kept is not None:
        return kept
    return _error_store(game_id=game_id)


def _waiting_store(game_id=None):
    payload = {'_ui': 'waiting'}
    if game_id is not None:
        payload['game_id'] = game_id
    return json.dumps(payload)


def _keep_or_wait(previous, game_id=None):
    kept = _success_text(previous)
    if kept is not None:
        return kept
    return _waiting_store(game_id)


def _already_painted(previous, generation, game_id, org):
    if not generation:
        return False
    prev = safe_loads(previous)
    if prev.get('game_id') and str(prev.get('game_id')) != str(game_id):
        return False
    if prev.get('_ui') in ('error', 'waiting') or prev.get('generation') != generation:
        return False
    state = report_refresh_state(game_id, org)
    if state.get('delayed') and prev.get('delay_seen') != state.get('label'):
        return False
    return True


def _frame_text(payload):
    """A play-by-play split string wrapped so generation can stamp it once."""
    if isinstance(payload, dict) and set(payload) == {'frame'} and isinstance(payload.get('frame'), str):
        return payload['frame']
    return None


def _with_generation(payload, generation, game_id, org):
    frame = _frame_text(payload)
    if not generation:
        if frame is not None:
            return frame
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)
    state = report_refresh_state(game_id, org)
    delay = state.get('label') if state.get('delayed') else None
    if frame is not None:
        wrapped = {
            'generation': generation,
            'game_id': game_id,
            'frame': frame,
        }
        if delay:
            wrapped['delay_seen'] = delay
        return json.dumps(wrapped)
    if isinstance(payload, str):
        data = safe_loads(payload)
        if isinstance(data, dict) and 'columns' in data and 'data' in data:
            wrapped = {
                'generation': generation,
                'game_id': game_id,
                'frame': payload,
            }
            if delay:
                wrapped['delay_seen'] = delay
            return json.dumps(wrapped)
        if not isinstance(data, dict):
            return payload
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        return payload
    data['generation'] = generation
    data['game_id'] = game_id
    if delay:
        data['delay_seen'] = delay
    else:
        data.pop('delay_seen', None)
    return json.dumps(data)


def _stale(game_id, org, generation):
    if not generation:
        return False
    return report_generation(game_id, org) != generation


def _banner_time_and_scores(info):
    status = str(info.get('status') or '').strip()
    tip = info.get('time') or ''
    if status == 'IN_PROGRESS':
        if not info.get('banner_ready'):
            return tip, None, None
        clock = info.get('banner_clock')
        return clock or tip, info.get('banner_home_score'), info.get('banner_away_score')
    if is_live_play_status(status):
        return tip, None, None
    return tip, info.get('home_score'), info.get('away_score')


@callback(
    Output('bs_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    State('bs_store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def update_bs_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store(game_id=game_id)
    try:
        status = _fixture_status(game_id, org)
    except SynergyAuthError:
        log_auth.exception('box score status failed game=%s', game_id)
        return _error_store(game_id=game_id)
    except Exception:
        log_unexpected.exception('box score status failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if not is_live_play_status(status):
        return no_update
    try:
        report = _open_report(game_id, org)
    except LiveBudgetWait:
        return _keep_or_wait(previous, game_id)
    except SynergyAuthError:
        return _error_store(game_id=game_id)
    except Exception:
        return _keep_previous(previous, game_id)
    generation = report_generation(game_id, org)
    if getattr(report, 'stats_failed', False):
        if _stale(game_id, org, generation):
            return no_update
        kept = safe_loads(previous)
        if kept.get('qt_pts_df') and kept.get('_ui') != 'error':
            if kept.get('stats_delayed') and kept.get('generation') == generation:
                return no_update
            if _stale(game_id, org, generation):
                return no_update
            kept['stats_delayed'] = True
            kept['generation'] = generation
            return json.dumps(kept)
        return _error_store(game_id=game_id)
    if _already_painted(previous, generation, game_id, org):
        return no_update
    if _stale(game_id, org, generation):
        return no_update
    try:
        payload = _box_dict(report, game_id)
    except Exception:
        log_payload.exception('box score payload failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if _stale(game_id, org, generation):
        return no_update
    return _with_generation(payload, generation, game_id, org)

@callback(
    Output('match_info_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    State('match_info_store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def update_match_info_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store(game_id=game_id)
    try:
        info = _info_dict(org, game_id)
    except SynergyAuthError:
        log_auth.exception('match info failed game=%s', game_id)
        return _error_store(game_id=game_id)
    except Exception:
        log_unexpected.exception('match info failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if not info:
        return json.dumps({})
    if not is_live_play_status(info.get('status')):
        return no_update
    if info.get('status') != 'IN_PROGRESS':
        if safe_loads(previous) == info:
            return no_update
        return json.dumps(info, ensure_ascii=False)
    try:
        report = _open_report(game_id, org)
    except LiveBudgetWait:
        kept = _success_text(previous)
        return kept if kept is not None else json.dumps(info, ensure_ascii=False)
    except SynergyAuthError:
        return _error_store(game_id=game_id)
    except Exception:
        kept = _success_text(previous)
        return kept if kept is not None else json.dumps(info, ensure_ascii=False)
    generation = report_generation(game_id, org)
    previous_info = safe_loads(previous)
    if (
        generation
        and previous_info.get('banner_generation') == generation
        and previous_info.get('status') == info.get('status')
    ):
        return no_update
    frame = getattr(report, 'playbyplay_df', None)
    clock, home_score, away_score = scoreboard_from_pbp_frame(
        frame, info.get('home_team_id'), info.get('away_team_id'),
    )
    info['banner_ready'] = True
    info['banner_clock'] = clock
    info['banner_home_score'] = home_score
    info['banner_away_score'] = away_score
    info['banner_generation'] = generation
    if _stale(game_id, org, generation):
        return no_update
    return json.dumps(info, ensure_ascii=False)

@callback(
    Output('game-info-banner-wrap', 'children'),
    Input('match_info_store', 'data'),
)
def render_game_info_banner(match_info_store):
    info = safe_loads(match_info_store)
    if not info or info.get('_ui') == 'error':
        return html.Div()
    time_display, home_score, away_score = _banner_time_and_scores(info)
    return game_banner(
        home_team=info.get('home_team') or 'Home',
        away_team=info.get('away_team') or 'Away',
        home_score=home_score,
        away_score=away_score,
        status=info.get('status') or '',
        date=info.get('date') or '',
        time=time_display,
        venue=info.get('venue') or '',
    )

@callback(
    Output('interval-component', 'disabled'),
    Input('match_info_store', 'data'),
)
def set_interval_disabled(match_info_store):
    info = safe_loads(match_info_store)
    if info.get('_ui') == 'error':
        return False
    return not is_live_play_status(info.get('status'))


@callback(
    Output('report-tab', 'style'),
    Output('tabs', 'value'),
    Input('match_info_store', 'data'),
    State('tabs', 'value'),
)
def toggle_report_tab(match_info_store, active_tab):
    info = safe_loads(match_info_store)
    visible = report_tab_is_visible(info.get('status'))
    style = {} if visible else {'display': 'none'}
    if (not visible) and active_tab == 'tab-report':
        return style, 'tab-bs'
    return style, no_update

def _live_report(game_id, org):
    """Return ``(report, generation)`` while the fixture is still live."""
    status = _fixture_status(game_id, org)
    if not is_live_play_status(status):
        return None, None
    report = _open_report(game_id, org)
    generation = report_generation(game_id, org)
    if _stale(game_id, org, generation):
        return None, generation
    return report, generation


def _finish_outputs(game_id, org, report, info):
    return (
        _box_payload(report, game_id),
        _pbp_split_json(report),
        _lineup_payload(report),
        _matchup_payload(report, info),
        _rotation_payload(report, info),
        json.dumps(info, ensure_ascii=False),
    )


@callback(
    Output('bs_store', 'data', allow_duplicate=True),
    Output('pbp_store', 'data', allow_duplicate=True),
    Output('lineup_store', 'data', allow_duplicate=True),
    Output('matchup_store', 'data', allow_duplicate=True),
    Output('rotation_store', 'data', allow_duplicate=True),
    Output('match_info_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    Input('finished-snapshot-sentinel', 'data'),
    prevent_initial_call='initial_duplicate',
)
def publish_finished_snapshot(n, game_id, league='plg', _sentinel='finished'):
    hold = (no_update, no_update, no_update, no_update, no_update, no_update)
    if not game_id:
        return hold
    org = _organization(league)
    if org is None:
        return hold
    try:
        status = _fixture_status(game_id, org)
    except SynergyAuthError:
        log_auth.exception('finished game status failed game=%s', game_id)
        err = _error_store(game_id=game_id)
        return (err, err, err, err, err, err)
    except Exception:
        log_unexpected.exception('finished game status failed game=%s', game_id)
        return hold
    if is_live_play_status(status):
        return hold
    try:
        if _is_game_load(n, _triggered_id()) and is_finished_status(status):
            warmup_game_report(game_id, organization_id=org)
        report = _open_report(game_id, org)
        info = _info_dict(org, game_id)
    except SynergyAuthError:
        err = _error_store(game_id=game_id)
        return (err, err, err, err, err, err)
    except Exception:
        log_unexpected.exception('finished game load failed game=%s', game_id)
        if report_generation(game_id, org):
            return hold
        err = _error_store(game_id=game_id)
        return (err, err, err, err, err, err)
    if not info or is_live_play_status(info.get('status')):
        return hold
    try:
        return _finish_outputs(game_id, org, report, info)
    except Exception:
        log_payload.exception('finished game payload failed game=%s', game_id)
        return hold


@callback(
    Output('pbp_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    State('pbp_store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def update_pbp_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        report, generation = _live_report(game_id, org)
    except LiveBudgetWait:
        return _keep_or_wait(previous, game_id)
    except SynergyAuthError:
        return _error_store(game_id=game_id)
    except Exception:
        return _keep_previous(previous, game_id)
    if report is None:
        return no_update
    if _already_painted(previous, generation, game_id, org):
        return no_update
    try:
        payload = {'frame': _pbp_split_json(report)}
    except Exception:
        log_payload.exception('play-by-play payload failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if _stale(game_id, org, generation):
        return no_update
    return _with_generation(payload, generation, game_id, org)

@callback(
    Output('lineup_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    State('lineup_store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def update_lineup_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        report, generation = _live_report(game_id, org)
    except LiveBudgetWait:
        return _keep_or_wait(previous, game_id)
    except SynergyAuthError:
        return _error_store(game_id=game_id)
    except Exception:
        return _keep_previous(previous, game_id)
    if report is None:
        return no_update
    if _already_painted(previous, generation, game_id, org):
        return no_update
    try:
        payload = _lineup_dict(report)
    except Exception:
        log_payload.exception('lineup payload failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if _stale(game_id, org, generation):
        return no_update
    return _with_generation(payload, generation, game_id, org)

@callback(
    Output('matchup_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    State('matchup_store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def update_matchup_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        if not is_live_play_status(_fixture_status(game_id, org)):
            return no_update
        info = _info_dict(org, game_id) or {}
    except SynergyAuthError:
        log_auth.exception('matchups status failed game=%s', game_id)
        return _error_store(game_id=game_id)
    except Exception:
        log_unexpected.exception('matchups status failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if not info.get('home_team_id') or not info.get('away_team_id'):
        return json.dumps({})
    try:
        report, generation = _live_report(game_id, org)
    except LiveBudgetWait:
        return _keep_or_wait(previous, game_id)
    except SynergyAuthError:
        return _error_store(game_id=game_id)
    except Exception:
        return _keep_previous(previous, game_id)
    if report is None:
        return no_update
    if _already_painted(previous, generation, game_id, org):
        return no_update
    try:
        payload = _matchup_dict(report, info)
    except Exception:
        log_payload.exception('matchups payload failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if _stale(game_id, org, generation):
        return no_update
    return _with_generation(payload, generation, game_id, org)

@callback(
    Output('rotation_store', 'data', allow_duplicate=True),
    Input('interval-component', 'n_intervals'),
    Input('game_id', 'children'),
    Input('game_league', 'children'),
    State('rotation_store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def update_rotation_store(n, game_id, league='plg', previous=None):
    if not game_id:
        return json.dumps({})
    org = _organization(league)
    if org is None:
        return _error_store()
    try:
        info = _info_dict(org, game_id) or {}
    except SynergyAuthError:
        log_auth.exception('rotation status failed game=%s', game_id)
        return _error_store(game_id=game_id)
    except Exception:
        log_unexpected.exception('rotation status failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if not info.get('home_team_id') or not info.get('away_team_id'):
        return no_update
    try:
        report, generation = _live_report(game_id, org)
    except LiveBudgetWait:
        return _keep_or_wait(previous, game_id)
    except SynergyAuthError:
        return _error_store(game_id=game_id)
    except Exception:
        return _keep_previous(previous, game_id)
    if report is None:
        return no_update
    if _already_painted(previous, generation, game_id, org):
        return no_update
    try:
        payload = _rotation_dict(report, info)
    except Exception:
        log_payload.exception('rotation payload failed game=%s', game_id)
        return _keep_previous(previous, game_id)
    if _stale(game_id, org, generation):
        return no_update
    return _with_generation(payload, generation, game_id, org)

@callback(
    Output('bs-matrix', 'children'),
    Output('bs-detail', 'children'),
    Input('bs_store', 'data'),
    Input('tabs', 'value'),
    Input('bs-period', 'data'),
)
def update_pane_bs(bs_store, active_tab, period='all'):
    # The shell is mounted in the layout. sync_box_score patches the hosts.
    return no_update, no_update


@callback(
    Output('bs-skeleton', 'style'),
    Output('bs-matrix-body', 'style'),
    Output('bs-detail-body', 'style'),
    Output('bs-status', 'style'),
    Output('bs-status', 'children'),
    Output('bs-period-bar', 'style'),
    Output('bs-period-control', 'data'),
    Output('bs-last-update', 'children'),
    Output('bs-score-scroll', 'children'),
    Output('bs-fouls-scroll', 'children'),
    Output('bs-tout-scroll', 'children'),
    Output('bs-pace-scroll', 'children'),
    Output('bs-advanced-scroll', 'children'),
    Output('bs-key-scroll', 'children'),
    Output('bs-team-scroll', 'children'),
    Output('bs-player-title-0', 'children'),
    Output('bs-player-title-1', 'children'),
    Output('bs-player-block-0', 'style'),
    Output('bs-player-block-1', 'style'),
    Output('bs-player-grid-0', 'rowData'),
    Output('bs-player-grid-1', 'rowData'),
    Output('bs-player-grid-0', 'dashGridOptions'),
    Output('bs-player-grid-1', 'dashGridOptions'),
    Output('bs-player-grid-0', 'columnDefs'),
    Output('bs-player-grid-1', 'columnDefs'),
    Output('bs-player-columns', 'data'),
    Input('bs_store', 'data'),
    Input('bs-period', 'data'),
    Input('game_id', 'children'),
    Input('tabs', 'value'),
    State('match_info_store', 'data'),
    State('bs-player-columns', 'data'),
    State('game_league', 'children'),
)
def sync_box_score(bs_store, period, game_id, active_tab, match_info, column_state, league='plg'):
    return box_score_sync_values(
        bs_store,
        period,
        game_id,
        active_tab,
        column_state,
        ctx.triggered_id,
        _paint_info(match_info, game_id, league),
    )


clientside_callback(
    """
    function(gameId) {
        window.__bsScrollKeep = false;
        window.__bsScrollSaved = {};
        document.querySelectorAll(
            '#bs-matrix-body .braves-table-scroll, #bs-detail-body .braves-table-scroll, #bs-detail-body .braves-grid-wrap'
        ).forEach(function(el) {
            el.scrollLeft = 0;
            el.scrollTop = 0;
        });
        ['bs-player-grid-0', 'bs-player-grid-1'].forEach(function(id) {
            var api = null;
            try {
                api = window.dash_ag_grid && window.dash_ag_grid.getApi && window.dash_ag_grid.getApi(id);
            } catch (err) {
                api = null;
            }
            if (api && !(api.isDestroyed && api.isDestroyed()) && api.resetColumnState) {
                api.resetColumnState();
            }
            var root = document.getElementById(id);
            if (!root) {
                return;
            }
            root.querySelectorAll(
                '.ag-body-viewport, .ag-center-cols-viewport, .ag-body-horizontal-scroll-viewport'
            ).forEach(function(node) {
                node.scrollTop = 0;
                node.scrollLeft = 0;
            });
        });
        window.__bsScrollKeep = true;
        return window.dash_clientside.no_update;
    }
    """,
    Output('bs-view-reset', 'data'),
    Input('game_id', 'children'),
)


@callback(
    Output('bs-period', 'data'),
    Output('bs-period-control', 'value'),
    Input('bs-period-control', 'value'),
    Input('game_id', 'children'),
    prevent_initial_call=True,
)
def update_bs_period(control_value, game_id):
    period = resolve_bs_period(ctx.triggered_id, control_value)
    return period, period


@callback(
    Output('pane-rotation', 'children'),
    Input('rotation_store', 'data'),
    Input('tabs', 'value'),
)
def update_pane_rotation(rotation_store, active_tab, view_store=None, match_info_store=None):
    if active_tab != 'tab-rotation':
        return no_update
    return render_rotation_children(rotation_store, view_store, match_info_store)


@callback(
    Output('shot-chart-period', 'data'),
    Output('shot-chart-period-bar', 'style'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
)
def update_shot_chart_period_options(pbp_store, active_tab='tab-shot-chart'):
    if active_tab != 'tab-shot-chart':
        return no_update, no_update
    return shot_chart_period_state(pbp_store)


@callback(
    Output('shot-chart-player-away', 'data'),
    Output('shot-chart-player-home', 'data'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
    State('match_info_store', 'data'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_shot_chart_players(pbp_store, active_tab, match_info_store=None, game_id=None, league='plg'):
    if active_tab != 'tab-shot-chart':
        return no_update, no_update
    return shot_chart_player_state(pbp_store, _paint_info(match_info_store, game_id, league))


@callback(
    Output('shot-chart-period', 'value'),
    Output('shot-chart-player-away', 'value'),
    Output('shot-chart-player-home', 'value'),
    Input('game_id', 'children'),
    State('shot-chart-period', 'value'),
    State('shot-chart-player-away', 'value'),
    State('shot-chart-player-home', 'value'),
    prevent_initial_call=True,
)
def reset_shot_chart_filters(game_id, period, away_player, home_player):
    return resolve_shot_chart_filters(ctx.triggered_id, period, away_player, home_player)


@callback(
    Output('pane-shot-chart', 'children'),
    Output('pane-shot-chart', 'style'),
    Output('shot-chart-courts', 'style'),
    Output('shot-chart-name-away', 'children'),
    Output('shot-chart-name-home', 'children'),
    Output('shot-chart-court-away', 'children'),
    Output('shot-chart-court-home', 'children'),
    Input('pbp_store', 'data'),
    Input('shot-chart-period', 'value'),
    Input('shot-chart-player-away', 'value'),
    Input('shot-chart-player-home', 'value'),
    Input('tabs', 'value'),
    State('match_info_store', 'data'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_shot_chart(
    pbp_store, period, away_player, home_player, active_tab,
    match_info_store=None, game_id=None, league='plg',
):
    if active_tab != 'tab-shot-chart':
        return (no_update,) * 7
    return shot_chart_outputs(shot_chart_panel(
        pbp_store,
        _paint_info(match_info_store, game_id, league),
        period,
        away_player,
        home_player,
        fixture_id=game_id,
    ))


@callback(
    Output('rotation-graph', 'figure'),
    Output('rotation-graph', 'style'),
    Output('rotation-graph-paper', 'style'),
    Input('rotation_store', 'data'),
    Input('rotation_view_store', 'data'),
    Input('tabs', 'value'),
    State('match_info_store', 'data'),
)
def update_rotation_graph(rotation_store, view_store, active_tab, match_info_store=None):
    if active_tab != 'tab-rotation':
        return no_update, no_update, no_update
    payload = safe_loads(rotation_store)
    hidden_paper = {'overflow': 'hidden', 'display': 'none'}
    if payload.get('_ui') == 'error' or not payload or not payload.get('teams'):
        return {}, {'width': '100%', 'height': '520px'}, hidden_paper
    fig = _rotation_figure_from_view(payload, _rotation_view(view_store), match_info_store)
    return (
        fig,
        {'width': '100%', 'height': f"{fig.layout.height or 520}px"},
        {'overflow': 'hidden'},
    )


@callback(
    Output('rotation_view_store', 'data'),
    Output('rotation-show-dnp', 'checked'),
    Input('rotation-show-dnp', 'checked'),
    Input({'type': 'rotation-run', 'index': ALL}, 'n_clicks'),
    Input('rotation-live', 'n_clicks'),
    Input('rotation-click-t', 'data'),
    Input('rotation_store', 'data'),
    Input('game_id', 'children'),
    State('rotation_view_store', 'data'),
    Input('match_info_store', 'data'),
    prevent_initial_call=True,
)
def update_rotation_view(
    show_dnp,
    run_clicks,
    live_clicks,
    click_t,
    rotation_store,
    game_id,
    view_store,
    match_info_store,
):
    triggered_id = ctx.triggered_id
    if triggered_id == 'rotation-live' and not live_clicks:
        return no_update, no_update
    result = apply_rotation_view_event(
        triggered_id,
        show_dnp,
        run_clicks,
        click_t,
        rotation_store,
        game_id,
        view_store,
        match_info_store,
    )
    if result is no_update:
        return no_update, no_update
    if triggered_id == 'game_id':
        return result, False
    return result, no_update


clientside_callback(
    """
    function(n) {
        if (!n) { return window.dash_clientside.no_update; }
        if (typeof window._rotationClickT !== 'number') {
            return window.dash_clientside.no_update;
        }
        return window._rotationClickT;
    }
    """,
    Output('rotation-click-t', 'data'),
    Input('rotation-click-fire', 'n_clicks'),
    prevent_initial_call=True,
)


@callback(
    Output('rotation-live', 'style'),
    Output('rotation-live', 'variant'),
    Input('match_info_store', 'data'),
    Input('rotation_view_store', 'data'),
)
def update_rotation_live_chip(match_info_store, view_store):
    live = is_live_play_status(safe_loads(match_info_store).get('status'))
    if not live:
        return {'display': 'none'}, 'light'
    follow = _rotation_view(view_store).get('follow_live', True)
    return {}, ('filled' if follow else 'light')


@callback(
    Output('rotation-last-update', 'children'),
    Input('rotation_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_rotation_last_update(rotation_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-rotation':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('lineup-last-update', 'children'),
    Input('lineup_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_lineup_last_update(lineup_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-lineup':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('matchup-team', 'data'),
    Output('matchup-team', 'value'),
    Input('match_info_store', 'data'),
    Input('game_id', 'children'),
    State('matchup-team', 'value'),
)
def sync_matchup_team(match_info_store, _game_id, current):
    info = safe_loads(match_info_store)
    away_id = info.get('away_team_id')
    home_id = info.get('home_team_id')
    away_id = None if away_id in (None, '') else str(away_id)
    home_id = None if home_id in (None, '') else str(home_id)
    if not away_id and not home_id:
        return no_update, no_update
    options = []
    if away_id:
        options.append({'label': info.get('away_team') or 'Away', 'value': away_id})
    if home_id:
        options.append({'label': info.get('home_team') or 'Home', 'value': home_id})
    try:
        triggered = ctx.triggered_id
    except Exception as exc:
        log_data.debug('matchup triggered id unavailable: %s', exc)
        triggered = None
    return options, matchup_team_value(current, away_id, home_id, triggered)


@callback(
    Output('matchup-last-update', 'children'),
    Input('matchup_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_matchup_last_update(matchup_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-matchups':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('matchup-grid', 'rowData'),
    Output('matchup-status', 'children'),
    Output('matchup-grid-wrap', 'style'),
    Input('matchup_store', 'data'),
    Input('matchup-team', 'value'),
    Input('tabs', 'value'),
)
def update_matchup_rows(matchup_store, viewpoint, active_tab):
    if active_tab != 'tab-matchups':
        return no_update, no_update, no_update
    payload = safe_loads(matchup_store)
    hidden = {'display': 'none'}
    if not payload or payload.get('_ui') == 'waiting':
        return [], loading_skeleton('table'), hidden
    if payload.get('_ui') == 'error':
        return [], _error_view(payload), hidden
    pairs = payload.get('pairs')
    if not isinstance(pairs, list):
        return [], loading_skeleton('table'), hidden
    if not pairs:
        return [], empty_state(EMPTY_MATCHUPS, EMPTY_GAME_NEXT), hidden
    return matchup_grid_records(payload, viewpoint), [], {'display': 'block'}


@callback(
    Output('shot-chart-last-update', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_shot_chart_last_update(pbp_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-shot-chart':
        return no_update
    return _last_update_span(game_id, _organization(league))


@callback(
    Output('pane-pbp', 'children'),
    Input('pbp_store', 'data'),
    Input('tabs', 'value'),
    State('game_id', 'children'),
    State('game_league', 'children'),
)
def update_pane_pbp(pbp_store, active_tab, game_id=None, league='plg'):
    if active_tab != 'tab-pbp':
        return no_update
    return render_pbp_children(pbp_store, game_id, _organization(league))


@callback(
    Output('pane-lineup', 'children'),
    Input('lineup_size_dropdown', 'value'),
    Input('tabs', 'value'),
    Input('lineup_store', 'data'),
    State('game_id', 'children'),
    State('lineup-show-opp', 'checked'),
    State('game_league', 'children'),
    State('match_info_store', 'data'),
)
def update_pane_lineup(lineup_size='5', active_tab='tab-lineup', lineup_store=None, game_id=None, show_opp=False, league='plg', match_info=None):
    if active_tab != 'tab-lineup':
        return no_update
    try:
        size_int = int(lineup_size)
    except Exception as exc:
        log_data.debug('lineup size parse failed: %s', exc)
        size_int = 5
    show_opp = bool(show_opp)
    info = _paint_info(match_info, game_id, league)
    meta = safe_loads(lineup_store)
    if meta.get('_ui') in ('waiting', 'error'):
        return render_lineup_children(lineup_store, size_int, show_opp=show_opp, match_info=info)
    lineup_dict = lineup_tables_for_size(lineup_store, size_int)
    if not lineup_dict and game_id:
        try:
            report = _open_report(game_id, _organization(league))
            sized = report.get_all_lineup_stats_json_dict(sizes=(size_int,))
            custom_dict = sized.get(str(size_int)) if isinstance(sized, dict) else None
            if custom_dict:
                return render_lineup_children(
                    json.dumps({str(size_int): custom_dict}),
                    size_int,
                    show_opp=show_opp,
                    match_info=info,
                )
        except LiveBudgetWait:
            return [loading_skeleton('table')]
        except Exception:
            log_payload.exception('lineup size payload failed game=%s', game_id)
    return render_lineup_children(lineup_store, size_int, show_opp=show_opp, match_info=info)


@callback(
    Output('lineup-show-opp', 'checked'),
    Input('game_id', 'children'),
    prevent_initial_call=True,
)
def reset_lineup_show_opp(_game_id):
    return False


clientside_callback(
    """
    function(checked) {
        if (window.applyLineupShowOpp) {
            window.applyLineupShowOpp(!!checked);
        }
        return !!checked;
    }
    """,
    Output('lineup-show-opp-sync', 'data'),
    Input('lineup-show-opp', 'checked'),
    prevent_initial_call=True,
)


@callback(
    Output('pane-report', 'children'),
    Input('tabs', 'value'),
    Input('report-pane-ready', 'data'),
    State('bs_store', 'data'),
    State('lineup_store', 'data'),
    State('match_info_store', 'data'),
    State('game_id', 'children'),
)
def update_pane_report(
    active_tab,
    pane_ready='',
    bs_store=None,
    lineup_store=None,
    match_info_store=None,
    game_id=None,
):
    if active_tab != 'tab-report':
        return no_update
    if str(pane_ready or '') in ('1', 'true', 'True'):
        return no_update
    try:
        return render_report_children(
            bs_store,
            lineup_store,
            match_info_store,
            game_id=game_id,
        )
    except Exception:
        log_payload.exception('report render failed')
        return [_error_view({'_ui': 'error', 'message': ERROR_GAME})]


@callback(
    Output('report-papers', 'children'),
    Output('report-page-list', 'children'),
    Input('report-page-cmd', 'data'),
    State('match_info_store', 'data'),
    prevent_initial_call=True,
)
def sync_report_page_shells(cmd, match_info_store):
    return apply_page_cmd(cmd, safe_loads(match_info_store))


@callback(
    Output('report-dialog', 'opened'),
    Input('report-dialog-opened', 'data'),
    prevent_initial_call=True,
)
def sync_report_dialog(opened):
    return bool(opened)


clientside_callback(
    """
    function(active_tab) {
        const hide = {display: 'none'};
        const show = {display: 'block'};
        return [
            active_tab === 'tab-bs' ? show : hide,
            active_tab === 'tab-rotation' ? show : hide,
            active_tab === 'tab-shot-chart' ? show : hide,
            active_tab === 'tab-lineup' ? show : hide,
            active_tab === 'tab-matchups' ? show : hide,
            active_tab === 'tab-pbp' ? show : hide,
            active_tab === 'tab-report' ? show : hide
        ];
    }
    """,
    Output('wrap-bs', 'style'),
    Output('wrap-rotation', 'style'),
    Output('wrap-shot-chart', 'style'),
    Output('wrap-lineup', 'style'),
    Output('wrap-matchups', 'style'),
    Output('wrap-pbp', 'style'),
    Output('wrap-report', 'style'),
    Input('tabs', 'value'),
)

