import datetime
import json

from dash import (
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
from dash.development.base_component import Component
import dash_mantine_components as dmc
import pandas as pd

from synergy_inbounder.communicator import SynergyAuthError
from synergy_inbounder.live_clock import forget_finished, recall, refresh_summaries
from synergy_inbounder.names import display_name
from synergy_inbounder.runtime_cache import (
    LIVE_CADENCE_SECONDS,
    id_refresh_state,
    season_refresh_state,
)
from synergy_inbounder.settings import (
    EASL_SEASON_ID,
    EASL_SEASONS,
    SYNERGY_EASL_ORGANIZATION_ID,
    SYNERGY_ORGANIZATION_ID,
    SYNERGY_SEASON_ID,
    SYNERGY_SEASONS,
)
from synergy_inbounder.parser import Parser
from synergy_inbounder.game_status import (
    format_score_display,
    score_is_clickable,
    status_bucket,
)
from ui_kit import (
    EMPTY_HOME,
    EMPTY_HOME_FILTER,
    EMPTY_HOME_FILTER_NEXT,
    EMPTY_HOME_NEXT,
    ERROR_HOME,
    REFRESH_DELAYED,
    empty_state,
    error_alert,
    filter_control,
    join_meta,
    loading_skeleton,
    matchup_line,
    matchup_score_parts,
    meta_cluster,
    status_badge,
)

register_page(
    __name__,
    name='Splashboard TFB | Home',
    top_nav=True,
    path='/'
)

SHOW_UPCOMING = 'upcoming'
SHOW_FINISHED = 'finished'
SHOW_ALL = 'all'
SHOW_OPTIONS = [
    {'label': 'Upcoming', 'value': SHOW_UPCOMING},
    {'label': 'Finished', 'value': SHOW_FINISHED},
    {'label': 'All', 'value': SHOW_ALL},
]
LEAGUE_PLG = 'PLG'
LEAGUE_EASL = 'EASL'
LEAGUE_OPTIONS = [
    {'label': LEAGUE_PLG, 'value': LEAGUE_PLG},
    {'label': LEAGUE_EASL, 'value': LEAGUE_EASL},
]
HOME_LAST_UPDATE_PENDING = 'Last Update: —'
_TAIPEI = datetime.timezone(datetime.timedelta(hours=8))


def default_season_id(league):
    if league == LEAGUE_EASL:
        return EASL_SEASON_ID
    return SYNERGY_SEASON_ID


def seasons_for(league):
    if league == LEAGUE_EASL:
        return EASL_SEASONS
    return SYNERGY_SEASONS


def initial_home_filters():
    return {
        'show': SHOW_UPCOMING,
        'game_type': None,
        'league': LEAGUE_PLG,
        'seasons': {
            LEAGUE_PLG: SYNERGY_SEASON_ID,
            LEAGUE_EASL: EASL_SEASON_ID,
        },
    }


def initial_home_scope():
    return {'league': LEAGUE_PLG, 'season_id': SYNERGY_SEASON_ID}


def layout():
    return html.Div([
        dcc.Interval(
            id='home-interval',
            interval=LIVE_CADENCE_SECONDS * 1000,
            n_intervals=0,
        ),
        dcc.Store(id='home-filter-store', data=initial_home_filters()),
        dcc.Store(id='home-scope-store', data=initial_home_scope()),
        html.Div(
            id='home-game-list',
            children=loading_skeleton(),
        ),
    ])


def _first_home_load(n_intervals):
    return not isinstance(n_intervals, int) or n_intervals == 0


def _home_filter_values(filters):
    if not isinstance(filters, dict):
        return SHOW_UPCOMING, None
    return filters.get('show') or SHOW_UPCOMING, filters.get('game_type')


def _triggered_id():
    try:
        return ctx.triggered_id
    except Exception:
        return None


def _scope_values(scope, filters):
    if isinstance(scope, dict) and scope.get('league') and scope.get('season_id'):
        return scope['league'], scope['season_id']
    filters = filters if isinstance(filters, dict) else {}
    league = filters.get('league') or LEAGUE_PLG
    if league not in (LEAGUE_PLG, LEAGUE_EASL):
        league = LEAGUE_PLG
    seasons = filters.get('seasons') if isinstance(filters.get('seasons'), dict) else {}
    return league, seasons.get(league) or default_season_id(league)


def _season_map(filters):
    raw = {}
    if isinstance(filters, dict) and isinstance(filters.get('seasons'), dict):
        raw = dict(filters['seasons'])
    raw.setdefault(LEAGUE_PLG, SYNERGY_SEASON_ID)
    raw.setdefault(LEAGUE_EASL, EASL_SEASON_ID)
    return raw


def apply_home_filters(show, game_type, league, season_id, filters, triggered, records=None):
    filters = filters if isinstance(filters, dict) else {}
    seasons = _season_map(filters)
    current = filters.get('league') or LEAGUE_PLG
    if current not in (LEAGUE_PLG, LEAGUE_EASL):
        current = LEAGUE_PLG
    next_show = filters.get('show') or SHOW_UPCOMING
    next_type = filters.get('game_type')
    scope = None
    if triggered == 'home-show':
        next_show = show or SHOW_UPCOMING
        next_type = game_type
        if isinstance(records, list):
            next_type = game_type_after_show_change(records, next_show, game_type)
    elif triggered == 'home-game-type':
        next_type = game_type
    elif triggered == 'home-league':
        current = league if league in (LEAGUE_PLG, LEAGUE_EASL) else LEAGUE_PLG
        next_type = None
        scope = {'league': current, 'season_id': seasons[current]}
    elif triggered == 'home-season':
        if season_id:
            seasons[current] = season_id
        next_type = None
        scope = {'league': current, 'season_id': seasons[current]}
    data = {
        'show': next_show,
        'game_type': next_type,
        'league': current,
        'seasons': seasons,
    }
    return data, scope


@callback(
    Output('home-game-list', 'children'),
    Output('home-filter-store', 'data', allow_duplicate=True),
    Input('home-interval', 'n_intervals'),
    Input('home-scope-store', 'data'),
    State('home-filter-store', 'data'),
    prevent_initial_call='initial_duplicate',
)
def load_home_game_list(n_intervals=0, scope=None, filters=None):
    first = _first_home_load(n_intervals)
    triggered = _triggered_id()
    scope_change = triggered == 'home-scope-store'
    show, game_type = _home_filter_values(filters)
    league, season_id = _scope_values(scope, filters)
    prefetch = bool(first or scope_change)
    try:
        df = df_data(prefetch=prefetch, league=league, season_id=season_id)
        org = _organization_for_home_league(league)
        season_key = season_id or default_season_id(league)
        refresh = season_refresh_state(org, season_key)
        names = id_refresh_state(org)
    except SynergyAuthError as exc:
        print(f"Error loading home game list: {exc}")
        return render_home_page(
            None,
            show=show,
            game_type=None,
            league=league,
            season_id=season_id,
            failed=True,
        ), no_update
    except Exception as exc:
        print(f"Error loading home game list: {exc}")
        if first or scope_change:
            return render_home_page(
                None,
                show=show,
                game_type=None,
                league=league,
                season_id=season_id,
                failed=True,
            ), no_update
        return no_update, no_update
    records = [] if df is None or df.empty else schedule_records(df, league=league)
    stamp = refresh.get('label')
    delayed = bool(refresh.get('delayed') or names.get('delayed'))
    if first or scope_change:
        show, game_type = entry_home_view(records)
    records = _apply_live_clocks(records, show, game_type, league)
    if first or scope_change:
        page = render_home_page(
            records,
            show=show,
            game_type=game_type,
            league=league,
            season_id=season_id,
            stamp=stamp,
            delayed=delayed,
        )
        return page, home_filters_after_default(
            filters, league, season_id, show, game_type,
        )
    page = render_home_page(
        records,
        show=show,
        game_type=game_type,
        league=league,
        season_id=season_id,
        stamp=stamp,
        delayed=delayed,
    )
    return page, no_update


@callback(
    Output('home-filter-store', 'data', allow_duplicate=True),
    Output('home-scope-store', 'data'),
    Output('home-game-type', 'value'),
    Input('home-show', 'value'),
    Input('home-game-type', 'value'),
    Input('home-league', 'value'),
    Input('home-season', 'value'),
    State('home-filter-store', 'data'),
    State('home-schedule-store', 'data'),
    prevent_initial_call=True,
)
def remember_home_filters(show, game_type, league, season_id, filters, records):
    data, scope = apply_home_filters(
        show, game_type, league, season_id, filters, ctx.triggered_id, records,
    )
    type_out = no_update
    if scope is None and data.get('game_type') != game_type:
        type_out = data.get('game_type')
    if scope is None:
        return data, no_update, type_out
    return data, scope, no_update


@callback(
    Output('home-schedule-list', 'children', allow_duplicate=True),
    Input('home-schedule-store', 'data'),
    Input('home-show', 'value'),
    Input('home-game-type', 'value'),
    prevent_initial_call=True,
)
def update_home_view(records, show, game_type):
    if isinstance(records, dict) and records.get('_ui') == 'error':
        return error_alert(ERROR_HOME)
    rows = records or []
    if _triggered_id() == 'home-show':
        game_type = game_type_after_show_change(rows, show, game_type)
    head = rows[0] if rows else None
    league = head.get('league') if isinstance(head, dict) and head.get('league') else LEAGUE_PLG
    rows = _apply_live_clocks(rows, show, game_type, league)
    return render_schedule_list(rows, show, game_type)


def _jsonable(node):
    if isinstance(node, Component):
        spec = node.to_plotly_json()
        spec['props'] = {
            key: _jsonable(value) for key, value in spec['props'].items()
        }
        return spec
    if isinstance(node, (list, tuple)):
        return [_jsonable(item) for item in node]
    if isinstance(node, dict):
        return {key: _jsonable(value) for key, value in node.items()}
    return node


clientside_callback(
    'function() { return %s; }' % json.dumps(_jsonable(loading_skeleton())),
    Output('home-schedule-list', 'children', allow_duplicate=True),
    Input('home-show', 'value'),
    Input('home-game-type', 'value'),
    Input('home-league', 'value'),
    Input('home-season', 'value'),
    prevent_initial_call=True,
)


def _plain(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _start_value(row):
    return row.get('startTimeLocal') or row.get('Time')


def _status_value(row):
    return row.get('status') if row.get('status') not in (None, '') else row.get('Status')


def _fixture_type_value(row):
    return row.get('fixtureType') if row.get('fixtureType') not in (None, '') else row.get('Game Type')


def _parse_start(value):
    if value is None or value == '':
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(value)
    except Exception:
        return None


def format_row_date(value):
    parsed = _parse_start(value)
    if parsed is not None:
        return parsed.strftime('%Y-%m-%d %a')
    text = str(value or '')
    if 'T' in text:
        return text.split('T', 1)[0]
    return text[:10] if text else ''


def format_row_time(value):
    parsed = _parse_start(value)
    if parsed is not None:
        return parsed.strftime('%H:%M')
    text = str(value or '')
    if 'T' in text:
        return text.split('T', 1)[1][:5]
    return text[:5] if text else ''


def _row_meta_time(record):
    if (
        isinstance(record, dict)
        and str(record.get('status') or '').strip() == 'IN_PROGRESS'
        and record.get('liveClock')
    ):
        return record['liveClock']
    start = record.get('startTimeLocal') if isinstance(record, dict) else None
    return format_row_time(start)


def _apply_live_clocks(records, show, game_type, league):
    rows = list(records or [])
    dict_rows = [row for row in rows if isinstance(row, dict)]
    org = _organization_for_home_league(league)
    forget_finished(org, dict_rows)
    visible = _by_start([
        row for row in filter_schedule_records(dict_rows, show, game_type)
        if str(row.get('status') or '').strip() == 'IN_PROGRESS' and row.get('fixtureId')
    ])
    refresh_summaries(org, visible)
    for row in dict_rows:
        if str(row.get('status') or '').strip() != 'IN_PROGRESS':
            row.pop('liveClock', None)
            continue
        label = recall(org, row.get('fixtureId'))
        if label:
            row['liveClock'] = label
        else:
            row.pop('liveClock', None)
    return rows


def _score_text(value):
    plain = _plain(value)
    if plain is None:
        return '—'
    text = str(plain).strip()
    if not text or text.lower() in ('nan', 'none'):
        return '—'
    return text


def schedule_records(df, league=LEAGUE_PLG):
    records = []
    for row in df.to_dict('records'):
        status = _plain(_status_value(row)) or ''
        start = _plain(_start_value(row))
        home_score = _plain(row.get('teamScoreHome'))
        away_score = _plain(row.get('teamScoreAway'))
        clickable = bool(score_is_clickable(status))
        records.append({
            'league': league,
            'fixtureId': str(_plain(row.get('fixtureId')) or ''),
            'status': str(status).strip(),
            'fixtureType': str(_plain(_fixture_type_value(row)) or ''),
            'venue': _plain(row.get('Venue')) or '',
            'homeTeam': _plain(row.get('Home Team')) or '',
            'awayTeam': _plain(row.get('Away Team')) or '',
            'score': format_score_display(status, home_score, away_score),
            'startTimeLocal': '' if start is None else str(start),
            'homeScore': home_score,
            'awayScore': away_score,
            'statusBucket': status_bucket(status),
            'scoreClickable': clickable,
        })
    records.sort(key=lambda item: _parse_start(item['startTimeLocal']) or pd.Timestamp.max)
    return records


def game_type_options(records):
    options = []
    seen = set()
    for record in records:
        value = record.get('fixtureType') or ''
        if not value or value in seen:
            continue
        seen.add(value)
        options.append({'label': str(value).title(), 'value': value})
    return options


def _stage(record):
    value = _fixture_type_value(record)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_if_needed(record):
    return str(_status_value(record) or '').strip() == 'IF_NEEDED'


def _bucket(record):
    return status_bucket(_status_value(record))


def _by_start(records):
    return sorted(
        records,
        key=lambda record: (
            _parse_start(record.get('startTimeLocal')) is None,
            _parse_start(record.get('startTimeLocal')) or pd.Timestamp.max,
        ),
    )


def _earliest(records):
    ordered = _by_start(records)
    dated = [
        record for record in ordered
        if _parse_start(record.get('startTimeLocal')) is not None
    ]
    pool = dated or ordered
    return pool[0] if pool else None


def _latest(records):
    ordered = _by_start(records)
    dated = [
        record for record in ordered
        if _parse_start(record.get('startTimeLocal')) is not None
    ]
    pool = dated or ordered
    return pool[-1] if pool else None


def _matching(records, predicate):
    return [record for record in records or [] if predicate(record)]


def entry_home_view(records):
    records = list(records or [])
    live = _matching(records, lambda record: _bucket(record) == 'live')
    real = _matching(
        records,
        lambda record: _bucket(record) == 'unplayed' and not _is_if_needed(record),
    )
    if live:
        return SHOW_UPCOMING, _stage(_earliest(live))
    if real:
        return SHOW_UPCOMING, _stage(_earliest(real))
    finished = _matching(records, lambda record: _bucket(record) == 'finished')
    if finished:
        return SHOW_FINISHED, _stage(_latest(finished))
    needed = _matching(records, _is_if_needed)
    if needed:
        return SHOW_UPCOMING, _stage(_earliest(needed))
    if records:
        return SHOW_UPCOMING, _stage(_earliest(records))
    return SHOW_UPCOMING, None


def _in_show(record, show):
    bucket = _bucket(record)
    if show == SHOW_UPCOMING:
        return bucket in ('live', 'unplayed')
    if show == SHOW_FINISHED:
        return bucket == 'finished'
    return True


def stage_has_games(records, show, game_type):
    stage = _stage({'fixtureType': game_type})
    if not stage:
        return False
    return any(
        _stage(record) == stage and _in_show(record, show)
        for record in records or []
    )


def default_stage_for_show(records, show):
    records = list(records or [])
    if show == SHOW_FINISHED:
        finished = _matching(records, lambda record: _bucket(record) == 'finished')
        return _stage(_latest(finished)) if finished else None
    if show == SHOW_ALL:
        _picked_show, stage = entry_home_view(records)
        if stage and stage_has_games(records, SHOW_ALL, stage):
            return stage
        return None
    live = _matching(records, lambda record: _bucket(record) == 'live')
    if live:
        return _stage(_earliest(live))
    real = _matching(
        records,
        lambda record: _bucket(record) == 'unplayed' and not _is_if_needed(record),
    )
    if real:
        return _stage(_earliest(real))
    needed = _matching(records, _is_if_needed)
    if needed:
        return _stage(_earliest(needed))
    return None


def game_type_after_show_change(records, show, game_type):
    records = list(records or [])
    show = show or SHOW_UPCOMING
    if stage_has_games(records, show, game_type):
        return game_type
    fallback = default_stage_for_show(records, show)
    if fallback:
        return fallback
    if show == SHOW_UPCOMING and _matching(
        records, lambda record: _bucket(record) in ('live', 'unplayed'),
    ):
        return None
    if show == SHOW_ALL and records:
        return None
    return game_type


def home_filters_after_default(filters, league, season_id, show, game_type):
    seasons = _season_map(filters)
    if league not in (LEAGUE_PLG, LEAGUE_EASL):
        league = LEAGUE_PLG
    seasons[league] = season_id or seasons.get(league) or default_season_id(league)
    return {
        'show': show,
        'game_type': game_type,
        'league': league,
        'seasons': seasons,
    }


def filter_schedule_records(records, show, game_type):
    rows = list(records or [])
    if game_type:
        rows = [row for row in rows if row.get('fixtureType') == game_type]
    if show == SHOW_UPCOMING:
        rows = [
            row for row in rows
            if status_bucket(row.get('status')) in ('live', 'unplayed')
        ]
        rows.sort(key=lambda item: _parse_start(item.get('startTimeLocal')) or pd.Timestamp.max)
    elif show == SHOW_FINISHED:
        rows = [
            row for row in rows
            if status_bucket(row.get('status')) == 'finished'
        ]
        rows.sort(key=lambda item: _parse_start(item.get('startTimeLocal')) or pd.Timestamp.min, reverse=True)
    else:
        rows.sort(key=lambda item: _parse_start(item.get('startTimeLocal')) or pd.Timestamp.min, reverse=True)
    return rows


def grouped_by_date(records):
    groups = []
    index = {}
    for record in records:
        date_key = format_row_date(record.get('startTimeLocal'))
        if date_key not in index:
            index[date_key] = []
            groups.append((date_key, index[date_key]))
        index[date_key].append(record)
    return groups


def _last_update_stamp():
    when = datetime.datetime.now(tz=_TAIPEI)
    return f'Last Update: {when}'


def _last_update_line(text, delayed=False):
    children = [
        dmc.Text(
            text,
            size='sm',
            c='dimmed',
            mb=0 if delayed else 8,
            className='no-print',
        ),
    ]
    if delayed:
        children.append(dmc.Text(
            REFRESH_DELAYED,
            size='sm',
            c='dimmed',
            mb=8,
            className='no-print',
        ))
    return html.Div(children, id='home-last-update')


def _compact_row(record):
    away_team = record.get('awayTeam') or ''
    home_team = record.get('homeTeam') or ''
    status = record.get('status') or ''
    away_display, home_display = matchup_score_parts(
        status,
        record.get('homeScore'),
        record.get('awayScore'),
    )
    inner = dmc.Stack(
        [
            matchup_line(away_team, home_team, away_display, home_display),
            meta_cluster(
                join_meta(
                    _row_meta_time(record),
                    record.get('venue') or '',
                ),
                status_badge(status, 'xs'),
            ),
        ],
        gap=4,
        px='md',
        py='sm',
    )
    fixture_id = record.get('fixtureId') or ''
    if 'scoreClickable' in record:
        clickable = bool(record.get('scoreClickable'))
    else:
        clickable = score_is_clickable(record.get('status'))
    if clickable:
        league = record.get('league') or LEAGUE_PLG
        slug = 'easl' if league == LEAGUE_EASL else 'plg'
        return html.A(
            inner,
            href=f'/game/{slug}/{fixture_id}',
            className='home-schedule-row home-schedule-row-clickable',
            style={'display': 'block', 'textDecoration': 'none', 'color': 'inherit'},
        )
    return dmc.Box(inner, className='home-schedule-row home-schedule-row-static')


def render_schedule_list(records, show, game_type):
    source = list(records or [])
    if not source:
        body = empty_state(EMPTY_HOME, EMPTY_HOME_NEXT)
    else:
        filtered = filter_schedule_records(source, show, game_type)
        if not filtered:
            body = empty_state(EMPTY_HOME_FILTER, EMPTY_HOME_FILTER_NEXT)
        else:
            children = []
            for date_key, group in grouped_by_date(filtered):
                children.append(
                    dmc.Text(
                        date_key,
                        size='xs',
                        fw=700,
                        c='dimmed',
                        px='md',
                        pt='sm',
                        pb=4,
                    )
                )
                children.extend(_compact_row(row) for row in group)
            body = dmc.Stack(children, gap=0)
    return dmc.Paper(
        body,
        withBorder=True,
        radius='md',
        shadow='xs',
        className='braves-card-wrapper home-schedule-list',
        style={'overflow': 'hidden'},
    )


def _season_select_data(league):
    return [
        {'label': label, 'value': season_id}
        for label, season_id in seasons_for(league)
    ]


def render_home_page(
    records,
    show=SHOW_UPCOMING,
    game_type=None,
    league=LEAGUE_PLG,
    season_id=None,
    failed=False,
    stamp=None,
    delayed=False,
):
    if league not in (LEAGUE_PLG, LEAGUE_EASL):
        league = LEAGUE_PLG
    if not season_id:
        season_id = default_season_id(league)
    rows = [] if failed else list(records or [])
    options = game_type_options(rows)
    selected_type = game_type or None
    league_control = dmc.SegmentedControl(
        id='home-league',
        data=LEAGUE_OPTIONS,
        value=league,
        radius='md',
        size='xs',
    )
    season_control = dmc.Select(
        id='home-season',
        data=_season_select_data(league),
        value=season_id,
        allowDeselect=False,
        clearable=False,
        searchable=False,
        size='xs',
        radius='md',
        w=132,
        comboboxProps={'withinPortal': True},
    )
    type_control = dmc.SegmentedControl(
        id='home-game-type',
        data=options,
        value=selected_type,
        radius='md',
        size='xs',
    )
    show_control = dmc.SegmentedControl(
        id='home-show',
        data=SHOW_OPTIONS,
        value=show or SHOW_UPCOMING,
        radius='md',
        size='xs',
    )
    if failed:
        stamp = HOME_LAST_UPDATE_PENDING
        delayed = False
        store_data = {'_ui': 'error'}
        list_body = error_alert(ERROR_HOME)
    else:
        if not stamp:
            stamp = _last_update_stamp()
        store_data = rows
        list_body = render_schedule_list(rows, show, game_type)
    return dmc.Stack(
        [
            dcc.Store(id='home-schedule-store', data=store_data),
            _last_update_line(stamp, delayed=delayed),
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            filter_control('', league_control, wrap_id='home-league-wrap'),
                            filter_control('', season_control, wrap_id='home-season-wrap'),
                            filter_control(
                                '',
                                type_control,
                                wrap_id='home-game-type-wrap',
                                visible=len(options) > 1,
                            ),
                            filter_control('', show_control),
                        ],
                        gap='sm',
                        align='center',
                        wrap='wrap',
                    ),
                    html.Div(list_body, id='home-schedule-list'),
                ],
                gap='md',
            ),
        ],
        gap=0,
    )


def _decorate_schedule(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    df['Time'] = df['startTimeLocal']
    df['Status'] = df['status'].astype(str).str.strip()
    df['rawStatus'] = df['Status']
    df['Game Type'] = df['fixtureType']
    df['Score'] = df.apply(
        lambda x: format_score_display(x.get('status'), x.get('teamScoreHome'), x.get('teamScoreAway')),
        axis=1,
    )
    df['statusBucket'] = df['status'].apply(status_bucket)
    df['scoreClickable'] = df['status'].apply(score_is_clickable)
    return df[[
        'Time', 'Status', 'rawStatus', 'Game Type', 'Venue',
        'Home Team', 'Score', 'Away Team', 'fixtureId',
        'statusBucket', 'scoreClickable',
        'startTimeLocal', 'fixtureType', 'status',
        'teamScoreHome', 'teamScoreAway',
    ]]


def _organization_for_home_league(league):
    if league == LEAGUE_EASL:
        return SYNERGY_EASL_ORGANIZATION_ID
    return SYNERGY_ORGANIZATION_ID


def df_data(prefetch=True, league=LEAGUE_PLG, season_id=None):
    org = _organization_for_home_league(league)
    default_season = EASL_SEASON_ID if league == LEAGUE_EASL else SYNERGY_SEASON_ID
    game_list_df = Parser.parse_season_game_list_df(org, season_id or default_season)
    id_table = Parser.parse_id_tables(org)

    if prefetch:
        try:
            from synergy_inbounder.runtime_cache import prefetch_latest_games
            prefetch_latest_games(
                game_list_df,
                max_games=2,
                organization_id=org,
            )
        except Exception as e:
            print(f"Failed to start home prefetch: {e}")

    df = game_list_df.copy()
    df['Venue'] = df.apply(lambda x: display_name(id_table, x.get('venueId')), axis=1)
    df['Home Team'] = df.apply(lambda x: display_name(id_table, x.get('teamIdHome')), axis=1)
    df['Away Team'] = df.apply(lambda x: display_name(id_table, x.get('teamIdAway')), axis=1)
    return _decorate_schedule(df)
