from dash import html, dcc, callback, Input, Output, register_page
import dash_mantine_components as dmc
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
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
    game_banner,
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


def layout():
    return html.Div([
        dcc.Loading(
            custom_spinner=loading_skeleton(),
            children=html.Div(
                id='home-game-list',
                children=loading_skeleton(),
            ),
        ),
    ])


@callback(
    Output('home-game-list', 'children'),
    Input('home-game-list', 'id'),
)
def load_home_game_list(_id):
    try:
        df = df_data()
    except Exception as exc:
        print(f"Error loading home game list: {exc}")
        return error_alert(ERROR_HOME)
    if df is None or df.empty:
        return empty_state(EMPTY_HOME, EMPTY_HOME_NEXT)
    records = schedule_records(df)
    return render_home_page(
        records,
        show=SHOW_UPCOMING,
        game_type=default_game_type(records),
    )


@callback(
    Output('home-hero', 'children'),
    Output('home-schedule-list', 'children'),
    Input('home-schedule-store', 'data'),
    Input('home-show', 'value'),
    Input('home-game-type', 'value'),
    prevent_initial_call=True,
)
def update_home_view(records, show, game_type):
    rows = records or []
    return render_hero(rows), render_schedule_list(rows, show, game_type)


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


def schedule_records(df):
    records = []
    for row in df.to_dict('records'):
        status = _plain(_status_value(row)) or ''
        start = _plain(_start_value(row))
        home_score = _plain(row.get('teamScoreHome'))
        away_score = _plain(row.get('teamScoreAway'))
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
            'scoreClickable': bool(score_is_clickable(status)),
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


def pick_hero_record(records):
    for record in records:
        if status_bucket(record.get('status')) == 'live':
            return record
    for record in records:
        if status_bucket(record.get('status')) == 'unplayed':
            return record
    return None


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


def render_hero(records):
    hero = pick_hero_record(records)
    if not hero:
        return html.Div()
    start = hero.get('startTimeLocal')
    return game_banner(
        home_team=hero.get('homeTeam') or 'Home',
        away_team=hero.get('awayTeam') or 'Away',
        home_score=_score_text(hero.get('homeScore')),
        away_score=_score_text(hero.get('awayScore')),
        status=hero.get('status') or '',
        date=format_row_date(start),
        time=format_row_time(start),
        venue=hero.get('venue') or '',
        mb=0,
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
    if score_is_clickable(record.get('status')):
        return html.A(
            inner,
            href=f'/game/{fixture_id}',
            className='home-schedule-row home-schedule-row-clickable',
            style={'display': 'block', 'textDecoration': 'none', 'color': 'inherit'},
        )
    return dmc.Box(inner, className='home-schedule-row home-schedule-row-static')


def render_schedule_list(records, show, game_type):
    filtered = filter_schedule_records(records, show, game_type)
    if not filtered:
        body = empty_state(EMPTY_HOME_FILTER, EMPTY_HOME_FILTER_NEXT)
    else:
        children = []
        for date_key, rows in grouped_by_date(filtered):
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
            children.extend(_compact_row(row) for row in rows)
        body = dmc.Stack(children, gap=0)
    return dmc.Paper(
        body,
        withBorder=True,
        radius='md',
        shadow='xs',
        className='braves-card-wrapper home-schedule-list',
        style={'overflow': 'hidden'},
    )


def render_home_page(records, show=SHOW_UPCOMING, game_type=None):
    options = game_type_options(records)
    selected_type = game_type if game_type is not None else default_game_type(records)
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
    return dmc.Stack(
        [
            dcc.Store(id='home-schedule-store', data=records),
            html.Div(render_hero(records), id='home-hero'),
            filter_control(
                '',
                type_control,
                wrap_id='home-game-type-wrap',
                visible=len(options) > 1,
            ),
            filter_control('', show_control),
            html.Div(
                render_schedule_list(records, show, game_type),
                id='home-schedule-list',
            ),
        ],
        gap='md',
    )


def df_data():
    game_list_df = Parser.parse_season_game_list_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)

    try:
        from synergy_inbounder.runtime_cache import prefetch_latest_games
        prefetch_latest_games(game_list_df, max_games=2)
    except Exception as e:
        print(f"Failed to start home prefetch: {e}")

    df = game_list_df
    df['Time'] = df['startTimeLocal']
    df['Status'] = df['status'].astype(str).str.strip()
    df['rawStatus'] = df['Status']
    df['Game Type'] = df['fixtureType']
    df['Venue'] = df.apply(lambda x: id_table.get(x['venueId'], x['venueId']), axis=1)
    df['Home Team'] = df.apply(lambda x: id_table.get(x['teamIdHome'], x['teamIdHome']), axis=1)
    df['Away Team'] = df.apply(lambda x: id_table.get(x['teamIdAway'], x['teamIdAway']), axis=1)
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
