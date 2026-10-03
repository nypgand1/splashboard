import datetime

from dash import html, dcc, callback, Input, Output, State, ctx, no_update, register_page
import dash_mantine_components as dmc
import pandas as pd

from easl_inbounder.settings import EASL_SEASON_ID, EASL_SEASONS
from synergy_inbounder.runtime_cache import LIVE_CADENCE_SECONDS
from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID, SYNERGY_SEASONS
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
        dcc.Loading(
            delay_show=1000,
            custom_spinner=loading_skeleton(),
            children=html.Div(
                id='home-game-list',
                children=loading_skeleton(),
            ),
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


def apply_home_filters(show, game_type, league, season_id, filters, triggered):
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
    Input('home-interval', 'n_intervals'),
    Input('home-scope-store', 'data'),
    State('home-filter-store', 'data'),
)
def load_home_game_list(n_intervals=0, scope=None, filters=None):
    first = _first_home_load(n_intervals)
    triggered = _triggered_id()
    scope_change = triggered == 'home-scope-store'
    show, game_type = _home_filter_values(filters)
    if scope_change:
        game_type = None
    league, season_id = _scope_values(scope, filters)
    prefetch = league == LEAGUE_PLG and (first or scope_change)
    try:
        df = df_data(prefetch=prefetch, league=league, season_id=season_id)
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
            )
        return no_update
    if df is None or df.empty:
        return render_home_page(
            [],
            show=show,
            game_type=game_type,
            league=league,
            season_id=season_id,
        )
    records = schedule_records(df, league=league)
    return render_home_page(
        records,
        show=show,
        game_type=game_type,
        league=league,
        season_id=season_id,
    )


@callback(
    Output('home-filter-store', 'data'),
    Output('home-scope-store', 'data'),
    Input('home-show', 'value'),
    Input('home-game-type', 'value'),
    Input('home-league', 'value'),
    Input('home-season', 'value'),
    State('home-filter-store', 'data'),
    prevent_initial_call=True,
)
def remember_home_filters(show, game_type, league, season_id, filters):
    data, scope = apply_home_filters(
        show, game_type, league, season_id, filters, ctx.triggered_id,
    )
    if scope is None:
        return data, no_update
    return data, scope


@callback(
    Output('home-schedule-list', 'children'),
    Input('home-schedule-store', 'data'),
    Input('home-show', 'value'),
    Input('home-game-type', 'value'),
    prevent_initial_call=True,
)
def update_home_view(records, show, game_type):
    if isinstance(records, dict) and records.get('_ui') == 'error':
        return no_update
    return render_schedule_list(records or [], show, game_type)


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
        clickable = bool(score_is_clickable(status)) and league != LEAGUE_EASL
        records.append({
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


def default_game_type(records):
    for record in records:
        if status_bucket(record.get('status')) == 'live':
            return record.get('fixtureType') or None
    for record in records:
        if status_bucket(record.get('status')) == 'unplayed':
            return record.get('fixtureType') or None
    finished = [
        record for record in records
        if status_bucket(record.get('status')) == 'finished'
    ]
    if finished:
        return finished[-1].get('fixtureType') or None
    return (records[0].get('fixtureType') or None) if records else None


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
        # Finished games: newest completed first (descending)
        rows.sort(key=lambda item: _parse_start(item.get('startTimeLocal')) or pd.Timestamp.min, reverse=True)
    else:
        # All: chronological order
        rows.sort(key=lambda item: _parse_start(item.get('startTimeLocal')) or pd.Timestamp.max)
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


def _last_update_line(text):
    return html.Div(
        dmc.Text(
            text,
            size='sm',
            c='dimmed',
            mb=8,
            className='no-print',
        ),
        id='home-last-update',
    )


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
                    format_row_time(record.get('startTimeLocal')),
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
        return html.A(
            inner,
            href=f'/game/{fixture_id}',
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
):
    if league not in (LEAGUE_PLG, LEAGUE_EASL):
        league = LEAGUE_PLG
    if not season_id:
        season_id = default_season_id(league)
    rows = [] if failed else list(records or [])
    options = game_type_options(rows)
    selected_type = game_type if game_type is not None else default_game_type(rows)
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
        store_data = {'_ui': 'error'}
        list_body = error_alert(ERROR_HOME)
    else:
        stamp = _last_update_stamp()
        store_data = rows
        list_body = render_schedule_list(rows, show, game_type)
    return dmc.Stack(
        [
            dcc.Store(id='home-schedule-store', data=store_data),
            _last_update_line(stamp),
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


def df_data(prefetch=True, league=LEAGUE_PLG, season_id=None):
    if league == LEAGUE_EASL:
        from easl_inbounder.parser import Parser as EaslParser
        frame = EaslParser.parse_season_game_list_df(season_id or EASL_SEASON_ID)
        return _decorate_schedule(frame)

    game_list_df = Parser.parse_season_game_list_df(
        SYNERGY_ORGANIZATION_ID,
        season_id or SYNERGY_SEASON_ID,
    )
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    if prefetch:
        try:
            from synergy_inbounder.runtime_cache import prefetch_latest_games
            prefetch_latest_games(game_list_df, max_games=2)
        except Exception as e:
            print(f"Failed to start home prefetch: {e}")

    df = game_list_df.copy()
    df['Venue'] = df.apply(lambda x: id_table.get(x['venueId'], x['venueId']), axis=1)
    df['Home Team'] = df.apply(lambda x: id_table.get(x['teamIdHome'], x['teamIdHome']), axis=1)
    df['Away Team'] = df.apply(lambda x: id_table.get(x['teamIdAway'], x['teamIdAway']), axis=1)
    return _decorate_schedule(df)
