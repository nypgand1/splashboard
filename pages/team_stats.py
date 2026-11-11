# -*- coding: utf-8 -*-
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
from dash.exceptions import PreventUpdate
from dash.development.base_component import Component
import dash_mantine_components as dmc

from synergy_inbounder.logs import data as log_data
from synergy_inbounder.logs import unexpected as log_unexpected
from synergy_inbounder.names import TEAM_TBD, display_name
from synergy_inbounder.settings import (
    EASL_SEASON_ID,
    SYNERGY_SEASON_ID,
    selectable_seasons,
)
from synergy_reporter.rotation import period_label
from synergy_reporter.shot_chart import COURT_IMAGE_STYLE, court_data_uri, season_zones
from synergy_reporter.team_rotation import (
    ROTATION_EMPTY,
    ROTATION_SELECT,
    ROTATION_SELECT_NEXT,
    build_team_rotation_figure,
    season_aggregate,
)
from synergy_reporter.team_season import (
    EMPTY_TEAM_STATS,
    EMPTY_TEAM_STATS_NEXT,
    OPPONENT_ALL,
    OPPONENT_ALL_LABEL,
    SITE_ALL,
    SITE_OPTIONS,
    STADIUM_ALL,
    STADIUM_ALL_LABEL,
    TEAM_ALL,
    TEAM_ALL_LABEL,
    rotation_games,
    schedule_chrome,
    team_stats_payload,
)
from ui_kit import (
    ERROR_GAME,
    empty_state,
    error_alert,
    filter_control,
    icon,
    loading_skeleton,
    shot_chart_paper,
    shot_court_column,
    team_name_lines,
)

register_page(
    __name__,
    name='Splashboard TFB | Team Stats',
    top_nav=True,
    path='/team-stats',
)

LEAGUE_OPTIONS = [
    {'label': 'PLG', 'value': 'PLG'},
    {'label': 'EASL', 'value': 'EASL'},
]
_KEY_GROUPS = (
    ('Points in the Paint', (('PIPM', 'M'), ('PIPA', 'A'), ('PIP', 'PT'))),
    ('Second Chance Points', (
        ('SCP2M', '2M'), ('SCP2A', '2A'), ('SCP3M', '3M'), ('SCP3A', '3A'), ('SCP', 'PT'),
    )),
    ('Fast Break Points', (
        ('FBP2M', '2M'), ('FBP2A', '2A'), ('FBP3M', '3M'), ('FBP3A', '3A'), ('FBP', 'PT'),
    )),
    ('Points off Turnovers', (
        ('POT2M', '2M'), ('POT2A', '2A'), ('POT3M', '3M'), ('POT3A', '3A'), ('POT', 'PT'),
    )),
)
_SHOT_GROUPS = (
    ('2PT', ('2M', '2A', '2FG%'), ('M', 'A', '%')),
    ('3PT', ('3M', '3A', '3FG%'), ('M', 'A', '%')),
    ('FT', ('FTM', 'FTA', 'FT%'), ('M', 'A', '%')),
    ('REB', ('OR', 'DR', 'REB'), ('O', 'D', 'T')),
)
_COUNT_TAILS = ('AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS')
_TAIL_LABEL = {'AST': 'AS', 'PTS': 'PT'}


def _cluster(kind, children, cluster_id=None, style=None):
    props = {
        'className': 'filter-cluster filter-cluster-{0}'.format(kind),
    }
    if cluster_id:
        props['id'] = cluster_id
    if style:
        props['style'] = style
    return dmc.Box(
        dmc.Box(children, className='filter-cluster-inner'),
        **props,
    )


def _sized_select(select_id, probe_id, label, data, value):
    return html.Div(
        [
            html.Div(
                html.Span(
                    label,
                    className='home-team-sizer-probe',
                    **{'aria-hidden': 'true'},
                ),
                id=probe_id,
                className='ts-sizer-probes',
            ),
            dmc.Select(
                id=select_id,
                data=data,
                value=value,
                allowDeselect=False,
                clearable=False,
                searchable=False,
                size='xs',
                radius='md',
                comboboxProps={'withinPortal': True},
                rightSectionWidth=28,
                className='home-team-sizer-control',
                styles={
                    'wrapper': {'width': '100%'},
                    'input': {
                        'width': '100%',
                        'paddingInlineStart': '12px',
                        'paddingInlineEnd': '40px',
                    },
                },
            ),
        ],
        className='home-team-sizer',
    )


def _default_season(league):
    if str(league or '').strip().upper() == 'EASL':
        return EASL_SEASON_ID
    return SYNERGY_SEASON_ID


def _season_data(league):
    return [
        {'label': label, 'value': season_id}
        for label, season_id in selectable_seasons(league)
    ]


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


def _loading_body():
    return dmc.Stack(
        [
            dmc.SimpleGrid(
                cols={'base': 1, 'lg': 2},
                spacing='12px',
                children=[dmc.Skeleton(height=160, radius='md') for _ in range(2)],
            ),
            dmc.Skeleton(height=180, radius='md'),
            dmc.Skeleton(height=220, radius='md'),
        ],
        gap='sm',
    )


def _stamp(text):
    return dmc.Text(text or 'Last Update: —', size='sm', c='dimmed', mb=8, className='no-print')


def _th(label, kind, span=None, cols=None, edge=False):
    table_props = {}
    if span:
        table_props['rowSpan'] = span
    if cols:
        table_props['colSpan'] = cols
    class_name = kind
    props = {'className': class_name}
    if table_props:
        props['tableProps'] = table_props
    return dmc.TableTh(label, **props)


def _segments(card_id, columns):
    present = set(columns)
    if card_id == 'advanced':
        return [('single', (column,)) for column in columns]
    segments = []
    if card_id == 'team':
        for name in ('Team', 'GP', 'Min'):
            if name in present:
                segments.append(('single', (name,)))
        for _title, members, _leaves in _SHOT_GROUPS:
            cols = tuple(column for column in members if column in present)
            if cols:
                segments.append(('group', cols))
        for column in _COUNT_TAILS:
            if column in present:
                segments.append(('single', (column,)))
        return segments
    if card_id == 'key':
        for name in ('Team', 'GP'):
            if name in present:
                segments.append(('single', (name,)))
        for _name, pairs in _KEY_GROUPS:
            cols = tuple(column for column, _label in pairs if column in present)
            if cols:
                segments.append(('group', cols))
        if 'BP' in present:
            segments.append(('single', ('BP',)))
        return segments
    for name in ('Team', 'GP', 'Pace'):
        if name in present:
            segments.append(('single', (name,)))
    factors = tuple(column for column in ('eFG%', 'TO%', 'ORB%', 'FT-R') if column in present)
    if factors:
        segments.append(('group', factors))
    return segments


def _edge_columns(card_id, columns):
    segments = _segments(card_id, columns)
    ends = set()
    for index, (kind, cols) in enumerate(segments):
        if not cols:
            continue
        if index + 1 >= len(segments):
            if kind == 'group':
                ends.add(cols[-1])
            continue
        if kind == 'group' or segments[index + 1][0] == 'group':
            ends.add(cols[-1])
    return ends


def _span_labels(columns, names, edges):
    present = set(columns)
    nodes = []
    for name in names:
        if name not in present:
            continue
        if name == 'Team':
            label = 'TEAM'
        elif name == 'GP':
            label = 'GP'
        else:
            label = name.upper()
        nodes.append(_th(label, 'braves-th-span', span=2, edge=name in edges))
    return nodes


def _header_rows(card_id, columns):
    present = set(columns)
    edges = _edge_columns(card_id, columns)
    if card_id == 'advanced':
        labels = []
        for column in columns:
            if column == 'Team':
                labels.append('TEAM')
            elif column == 'GP':
                labels.append('GP')
            else:
                labels.append(column)
        return [dmc.TableTr([
            _th(label, 'braves-th-single') for label in labels
        ])]

    top = []
    sub = []
    if card_id == 'team':
        top.extend(_span_labels(columns, ('Team', 'GP', 'Min'), edges))
        for title, members, leaves in _SHOT_GROUPS:
            if not any(column in present for column in members):
                continue
            top.append(_th(
                title, 'braves-th-group', cols=len(leaves), edge=members[-1] in edges,
            ))
            sub.extend(
                _th(leaf, 'braves-th-sub', edge=column in edges)
                for column, leaf in zip(members, leaves)
            )
        for column in _COUNT_TAILS:
            if column in present:
                top.append(_th(
                    _TAIL_LABEL.get(column, column),
                    'braves-th-span-tight',
                    span=2,
                    edge=column in edges,
                ))
    elif card_id == 'key':
        top.extend(_span_labels(columns, ('Team', 'GP'), edges))
        for name, pairs in _KEY_GROUPS:
            found = [(column, label) for column, label in pairs if column in present]
            if not found:
                continue
            top.append(_th(
                name, 'braves-th-group', cols=len(found), edge=found[-1][0] in edges,
            ))
            sub.extend(
                _th(label, 'braves-th-sub', edge=column in edges)
                for column, label in found
            )
        if 'BP' in present:
            top.append(_th('BP', 'braves-th-span', span=2, edge='BP' in edges))
    else:
        top.extend(_span_labels(columns, ('Team', 'GP', 'Pace'), edges))
        factors = [column for column in ('eFG%', 'TO%', 'ORB%', 'FT-R') if column in present]
        if factors:
            top.append(_th(
                'FOUR FACTORS', 'braves-th-group', cols=len(factors),
                edge=factors[-1] in edges,
            ))
            sub.extend(
                _th(column, 'braves-th-sub', edge=column in edges) for column in factors
            )
    rows = [dmc.TableTr(top)]
    if sub:
        rows.append(dmc.TableTr(sub))
    return rows


def _team_label(text, keep_vs=False):
    raw = '' if text is None else str(text)
    name = raw[:-3] if keep_vs and raw.endswith(' vs') else raw
    first, second = team_name_lines(name)
    if not second:
        return raw
    suffix = ' vs' if keep_vs else ''
    return html.Span(
        [
            html.Span(name + suffix, className='ts-team-full'),
            html.Span(first + suffix, className='ts-team-line1'),
            html.Span(second, className='ts-team-line2'),
        ],
        className='ts-team-label is-split',
    )


def _body_rows(card):
    columns = card.get('columns') or []
    edges = _edge_columns(card.get('id'), columns)
    records = []
    for index, record in enumerate(card.get('rows') or []):
        records.append(record)
        opp_rows = card.get('opp_rows') or []
        if index < len(opp_rows):
            records.append(opp_rows[index])
    rows = []
    for record in records:
        opp = bool(isinstance(record, dict) and record.get('opp'))
        cells = []
        for column in columns:
            cell = record.get(column) if isinstance(record, dict) else None
            text = ''
            style = None
            if isinstance(cell, dict):
                text = '' if cell.get('text') is None else str(cell.get('text'))
                if opp and cell.get('opp_best'):
                    style = {'color': '#e63946', 'fontWeight': 700}
                elif cell.get('winner'):
                    style = {'color': '#0077b6', 'fontWeight': 700}
            classes = []
            if column in edges:
                classes.append('braves-group-end')
            if opp and column == 'Team':
                classes.append('braves-opp-label')
            kwargs = {}
            if style:
                kwargs['style'] = style
            if classes:
                kwargs['className'] = ' '.join(classes)
            content = text
            if column == 'Team':
                content = _team_label(
                    text,
                    keep_vs=(
                        not opp
                        and not (isinstance(record, dict) and record.get('summary'))
                        and text.endswith(' vs')
                    ),
                )
            cells.append(dmc.TableTd(content, **kwargs))
        class_name = 'braves-clean-row braves-opp-row' if opp else 'braves-clean-row'
        if isinstance(record, dict) and record.get('summary'):
            class_name += ' braves-summary-end' if opp else ' braves-summary-row'
        rows.append(dmc.TableTr(cells, className=class_name))
    return rows


def _paper(card):
    table = dmc.Table(
        [
            dmc.TableThead(_header_rows(card.get('id'), card.get('columns') or [])),
            dmc.TableTbody(_body_rows(card)),
        ],
        withTableBorder=False,
        withColumnBorders=False,
        className='braves-clean-table',
        style={'width': '100%'},
    )
    children = [dmc.Box(table, className='braves-table-scroll')]
    title = card.get('title')
    if title:
        children.insert(0, dmc.Text(
            str(title).upper(),
            size='xs',
            fw=700,
            c='dimmed',
            mb=6,
            style={'letterSpacing': '0.05em'},
        ))
    return dmc.Paper(
        children,
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def _cards_view(cards):
    return dmc.Stack(
        [
            dmc.SimpleGrid(
                cols={'base': 1, 'lg': 2},
                spacing='12px',
                children=[_paper(cards['pace']), _paper(cards['advanced'])],
            ),
            _paper(cards['key']),
            _paper(cards['team']),
        ],
        gap='sm',
    )


def _view(payload):
    if not payload or not payload.get('ok'):
        return error_alert((payload or {}).get('message') or ERROR_GAME)
    if payload.get('empty') or not payload.get('cards'):
        return empty_state(payload.get('message') or '', payload.get('next_step') or '')
    return _cards_view(payload['cards'])


def _rotation_pane():
    return html.Div(id='ts-rotation', style={'display': 'none'})


def _shot_pane():
    return html.Div(
        shot_chart_paper(
            [
                dmc.Box(
                    dmc.SegmentedControl(
                        id='ts-shot-period',
                        data=[{'label': 'All', 'value': 'all'}],
                        value='all',
                        radius='md',
                        size='xs',
                    ),
                    id='ts-shot-period-bar',
                    mb='sm',
                    style={'display': 'none'},
                ),
                html.Div(id='ts-shot-body'),
            ],
            card_id='ts-shot-card',
        ),
        id='ts-shot',
        style={'display': 'none'},
    )


def _opp_chart_name(opponent, id_table):
    if not opponent or opponent == OPPONENT_ALL:
        return 'Opp'
    bare = display_name(id_table, opponent)
    if bare == TEAM_TBD:
        return 'Opp'
    return bare


def _shot_column(name, zones):
    return shot_court_column([
        dmc.Text(name, fw=700, ta='center', size='sm'),
        html.Img(
            src=court_data_uri(zones),
            alt='{0} shot chart'.format(name),
            style=dict(COURT_IMAGE_STYLE),
        ),
    ])


def _shot_courts(team_name, team_zones, opp_name, opp_zones):
    return dmc.SimpleGrid(
        cols={'base': 1, 'sm': 2},
        spacing='16px',
        children=[
            _shot_column(team_name, team_zones),
            _shot_column(opp_name, opp_zones),
        ],
    )


def _shot_skeleton_column():
    return shot_court_column([
        dmc.Skeleton(height=14, width=160, radius='sm'),
        dmc.Skeleton(
            radius='md',
            style={'width': '100%', 'aspectRatio': '380.05 / 400.51'},
        ),
    ])


def shot_chart_skeleton():
    return dmc.SimpleGrid(
        cols={'base': 1, 'sm': 2},
        spacing='16px',
        children=[_shot_skeleton_column(), _shot_skeleton_column()],
    )


def layout():
    league = 'PLG'
    season_id = _default_season(league)
    league_control = dmc.SegmentedControl(
        id='ts-league',
        data=LEAGUE_OPTIONS,
        value=league,
        radius='md',
        size='xs',
    )
    season_control = dmc.Select(
        id='ts-season',
        data=_season_data(league),
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
        id='ts-game-type',
        data=[{'label': 'Regular', 'value': 'REGULAR'}],
        value='REGULAR',
        radius='md',
        size='xs',
    )
    team_control = _sized_select(
        'ts-team',
        'ts-team-probes',
        TEAM_ALL_LABEL,
        [{'label': TEAM_ALL_LABEL, 'value': TEAM_ALL}],
        TEAM_ALL,
    )
    opponent_control = _sized_select(
        'ts-opponent',
        'ts-opponent-probes',
        OPPONENT_ALL_LABEL,
        [{'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL}],
        OPPONENT_ALL,
    )
    stadium_control = _sized_select(
        'ts-stadium',
        'ts-stadium-probes',
        STADIUM_ALL_LABEL,
        [{'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL}],
        STADIUM_ALL,
    )
    site_control = dmc.SegmentedControl(
        id='ts-site',
        data=list(SITE_OPTIONS),
        value=SITE_ALL,
        radius='md',
        size='xs',
    )
    return dmc.Stack(
        [
            dcc.Store(id='ts-filter-pack-sync'),
            dcc.Store(id='ts-sizer-sync'),
            dcc.Store(id='ts-show-opp-memory'),
            dcc.Store(id='ts-opponent-width', data=[OPPONENT_ALL_LABEL]),
            dcc.Store(
                id='ts-applied',
                data={'league': league, 'season': season_id, 'game_type': 'REGULAR'},
            ),
            dcc.Store(id='ts-intent'),
            dcc.Store(id='ts-job'),
            dcc.Store(
                id='ts-slice',
                data={
                    'team': TEAM_ALL,
                    'opponent': OPPONENT_ALL,
                    'stadium': STADIUM_ALL,
                    'site': SITE_ALL,
                },
            ),
            dmc.Tabs(
                dmc.TabsList([
                    dmc.TabsTab(
                        'Box Score',
                        value='tab-bs',
                        leftSection=icon('tabler:table', width=14),
                    ),
                    dmc.TabsTab(
                        'Rotation',
                        value='tab-rotation',
                        leftSection=icon('tabler:chart-bar', width=14),
                    ),
                    dmc.TabsTab(
                        'Shot Chart',
                        value='tab-shot-chart',
                        leftSection=icon('tabler:ball-basketball', width=14),
                    ),
                ]),
                id='ts-tabs',
                value='tab-bs',
                variant='default',
                className='braves-clean-tabs',
                style={'margin': '0 0 16px 0', 'padding': '0', 'borderBottom': 'none'},
            ),
            html.Div(_stamp('Last Update: —'), id='ts-stamp'),
            dmc.Box(
                [
                    _cluster('league', [
                        filter_control('', league_control, wrap_id='ts-league-wrap'),
                        filter_control('', season_control, wrap_id='ts-season-wrap'),
                    ]),
                    _cluster('type', [
                        filter_control(
                            '',
                            type_control,
                            wrap_id='ts-game-type-wrap',
                            visible=False,
                        ),
                    ]),
                ],
                id='ts-filter-pack',
                className='filter-pack filter-pack-scope',
            ),
            dmc.Box(
                [
                    _cluster(
                        'team',
                        [filter_control('', team_control)],
                        cluster_id='ts-team-cluster',
                        style={'display': 'none'},
                    ),
                    _cluster(
                        'opp',
                        [filter_control('', opponent_control)],
                        cluster_id='ts-opponent-cluster',
                        style={'display': 'none'},
                    ),
                ],
                id='ts-match-pack',
                className='filter-pack filter-pack-match',
            ),
            dmc.Box(
                [
                    _cluster(
                        'stadium',
                        [filter_control('', stadium_control)],
                        cluster_id='ts-stadium-cluster',
                        style={'display': 'none'},
                    ),
                    _cluster('site', [
                        filter_control('', site_control, wrap_id='ts-site-wrap'),
                    ]),
                ],
                id='ts-place-pack',
                className='filter-pack filter-pack-place',
            ),
            dmc.Group(
                [
                    html.Div(
                        dmc.SegmentedControl(
                            id='ts-period',
                            data=[{'label': 'All', 'value': 'all'}],
                            value='all',
                            radius='md',
                            size='xs',
                        ),
                        id='ts-period-wrap',
                        style={'display': 'none'},
                    ),
                    dmc.Switch(
                        id='ts-show-opp',
                        label='Show Opp',
                        checked=False,
                        size='sm',
                        color='gray',
                        ms='auto',
                    ),
                ],
                id='ts-period-bar',
                justify='flex-start',
                align='center',
                wrap='wrap',
                gap='sm',
                w='100%',
            ),
            html.Div(_loading_body(), id='ts-body'),
            _rotation_pane(),
            _shot_pane(),
        ],
        gap='md',
    )


_LOADING_BODY = json.dumps(_jsonable(_loading_body()))
_CHART_LOADING = json.dumps(_jsonable(loading_skeleton('chart')))
_SHOT_LOADING = json.dumps(_jsonable(shot_chart_skeleton()))
_ROTATION_PICK = json.dumps(_jsonable(empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)))

clientside_callback(
    """
    function(checked) {
        return checked ? 'ts-show-opp' : '';
    }
    """,
    Output('ts-body', 'className'),
    Input('ts-show-opp', 'checked'),
)

clientside_callback(
    """
    function(league, season, gameType, applied) {
        var current = applied || {};
        var leagueValue = league == null ? null : league;
        var seasonValue = season == null ? null : season;
        var typeValue = gameType == null ? null : gameType;
        var sameLeague = leagueValue == (current.league == null ? null : current.league);
        var sameSeason = seasonValue == (current.season == null ? null : current.season);
        var sameType = typeValue == (current.game_type == null ? null : current.game_type);
        if (sameLeague && sameSeason && sameType) {
            return window.dash_clientside.no_update;
        }
        var scope = !sameLeague || !sameSeason;
        return {
            league: leagueValue,
            season: sameLeague ? seasonValue : null,
            game_type: scope ? null : typeValue,
            skeleton: scope,
            nonce: Date.now()
        };
    }
    """,
    Output('ts-intent', 'data'),
    Input('ts-league', 'value'),
    Input('ts-season', 'value'),
    Input('ts-game-type', 'value'),
    State('ts-applied', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(intent) {
        if (!intent || !intent.skeleton) {
            return window.dash_clientside.no_update;
        }
        return __LOADING_BODY__;
    }
    """.replace('__LOADING_BODY__', _LOADING_BODY),
    Output('ts-body', 'children', allow_duplicate=True),
    Input('ts-intent', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(intent) {
        var skip = window.dash_clientside.no_update;
        if (!intent || intent.nonce == null) {
            return [skip, skip];
        }
        return [__CHART_LOADING__, __SHOT_LOADING__];
    }
    """.replace('__CHART_LOADING__', _CHART_LOADING).replace(
        '__SHOT_LOADING__', _SHOT_LOADING,
    ),
    Output('ts-rotation', 'children', allow_duplicate=True),
    Output('ts-shot-body', 'children', allow_duplicate=True),
    Input('ts-intent', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(team, opponent, stadium, site, painted) {
        var current = painted || {};
        function same(left, right) {
            var a = left == null ? null : left;
            var b = right == null ? null : right;
            return a == b;
        }
        var skip = window.dash_clientside.no_update;
        if (
            same(team, current.team)
            && same(opponent, current.opponent)
            && same(stadium, current.stadium)
            && same(site, current.site)
        ) {
            return [skip, skip, skip];
        }
        var cards = skip;
        if (current.team && current.team !== 'all' && (team === 'all' || team == null)) {
            cards = __LOADING_BODY__;
        }
        var chart = __CHART_LOADING__;
        var shot = skip;
        if (team === 'all' || team == null) {
            chart = __ROTATION_PICK__;
            shot = __ROTATION_PICK__;
        } else if (!same(team, current.team)) {
            shot = __SHOT_LOADING__;
        }
        return [cards, chart, shot];
    }
    """.replace('__LOADING_BODY__', _LOADING_BODY).replace(
        '__CHART_LOADING__', _CHART_LOADING,
    ).replace('__SHOT_LOADING__', _SHOT_LOADING).replace(
        '__ROTATION_PICK__', _ROTATION_PICK,
    ),
    Output('ts-body', 'children', allow_duplicate=True),
    Output('ts-rotation', 'children', allow_duplicate=True),
    Output('ts-shot-body', 'children', allow_duplicate=True),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    State('ts-slice', 'data'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function() {
        var api = window.dash_clientside && window.dash_clientside.filter_pack;
        if (api && api.sync) {
            api.sync();
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('ts-filter-pack-sync', 'data'),
    Input('ts-body', 'children'),
    Input('ts-game-type', 'data'),
    Input('ts-team', 'data'),
    Input('ts-opponent', 'data'),
    Input('ts-stadium', 'data'),
)


clientside_callback(
    """
    function(teamOptions, opponentLabels, stadiumOptions) {
        function fill(id, options, fallback) {
            var host = document.getElementById(id);
            if (!host) {
                return;
            }
            var labels = [];
            (options || []).forEach(function (item) {
                if (item && item.label) {
                    labels.push(String(item.label));
                } else if (typeof item === 'string' && item) {
                    labels.push(item);
                }
            });
            if (!labels.length) {
                labels.push(fallback);
            }
            while (host.firstChild) {
                host.removeChild(host.firstChild);
            }
            labels.forEach(function (label) {
                var span = document.createElement('span');
                span.className = 'home-team-sizer-probe';
                span.setAttribute('aria-hidden', 'true');
                span.textContent = label;
                host.appendChild(span);
            });
        }
        fill('ts-team-probes', teamOptions, 'All Teams');
        fill('ts-opponent-probes', opponentLabels, 'vs All Teams');
        fill('ts-stadium-probes', stadiumOptions, 'All Stadiums');
        var api = window.dash_clientside && window.dash_clientside.filter_pack;
        if (api && api.sync) {
            api.sync();
            window.setTimeout(api.sync, 0);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('ts-sizer-sync', 'data'),
    Input('ts-team', 'data'),
    Input('ts-opponent-width', 'data'),
    Input('ts-stadium', 'data'),
)


clientside_callback(
    """
    function(tab) {
        var hidden = {display: 'none'};
        var rotation = tab === 'tab-rotation';
        var shot = tab === 'tab-shot-chart';
        if (rotation) {
            return [hidden, hidden, null, hidden, null];
        }
        if (shot) {
            return [hidden, hidden, hidden, null, hidden];
        }
        return [null, null, hidden, hidden, null];
    }
    """,
    Output('ts-period-bar', 'style'),
    Output('ts-body', 'style'),
    Output('ts-rotation', 'style'),
    Output('ts-shot', 'style'),
    Output('ts-show-opp', 'style'),
    Input('ts-tabs', 'value'),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(period, shotPeriod) {
        var context = window.dash_clientside.callback_context || {};
        var triggered = (context.triggered && context.triggered[0]) || {};
        var prop = triggered.prop_id || '';
        var skip = window.dash_clientside.no_update;
        if (prop.indexOf('ts-shot-period') === 0) {
            if (shotPeriod == null || shotPeriod === '' || shotPeriod == period) {
                return [skip, skip];
            }
            return [shotPeriod, skip];
        }
        if (period == null || period === '' || period == shotPeriod) {
            return [skip, skip];
        }
        return [skip, period];
    }
    """,
    Output('ts-period', 'value', allow_duplicate=True),
    Output('ts-shot-period', 'value', allow_duplicate=True),
    Input('ts-period', 'value'),
    Input('ts-shot-period', 'value'),
    prevent_initial_call=True,
)


def _same(left, right):
    return left == right


def _triggered_id():
    try:
        return ctx.triggered_id
    except Exception as exc:
        log_data.debug('team stats triggered id unavailable: %s', exc)
        return None


def _menu_value(payload, key, options, fallback):
    selected = payload.get(key) or fallback
    if not any(item.get('value') == selected for item in options):
        return fallback
    return selected


def _load(
    league, season_id, game_type, period, reason,
    opponent=OPPONENT_ALL, stadium=STADIUM_ALL, site=SITE_ALL, team=TEAM_ALL,
):
    try:
        return team_stats_payload(
            league or 'PLG',
            season_id=season_id,
            game_type=game_type,
            period=period,
            reason=reason,
            opponent=opponent,
            stadium=stadium,
            site=site,
            team=team,
        )
    except Exception:
        log_unexpected.exception('team stats page load failed')
        return {
            'ok': False,
            'message': ERROR_GAME,
            'stamp': 'Last Update: —',
            'season_id': season_id,
            'seasons': _season_data(league or 'PLG'),
            'game_type': game_type,
            'game_types': [],
            'game_type_visible': False,
            'period': 'all',
            'period_chips': [],
            'period_visible': False,
            'opponent': OPPONENT_ALL,
            'opponent_options': [{'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL}],
            'opponent_visible': False,
            'stadium': STADIUM_ALL,
            'stadium_options': [{'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL}],
            'stadium_visible': False,
            'site': SITE_ALL,
        }


def _paint(payload, league, season_id, game_type, period, opponent, stadium, site, team=TEAM_ALL):
    seasons = payload.get('seasons') or _season_data(league or 'PLG')
    selected_season = payload.get('season_id') or season_id
    types = payload.get('game_types') or []
    selected_type = payload.get('game_type')
    if not types:
        types = [{'label': 'Regular', 'value': 'REGULAR'}]
    chips = payload.get('period_chips') or [{'label': 'All', 'value': 'all'}]
    selected_period = payload.get('period') or 'all'
    if not any(item.get('value') == selected_period for item in chips):
        selected_period = 'all'
    opponent_options = payload.get('opponent_options') or [
        {'label': OPPONENT_ALL_LABEL, 'value': OPPONENT_ALL},
    ]
    stadium_options = payload.get('stadium_options') or [
        {'label': STADIUM_ALL_LABEL, 'value': STADIUM_ALL},
    ]
    selected_opponent = _menu_value(payload, 'opponent', opponent_options, OPPONENT_ALL)
    selected_stadium = _menu_value(payload, 'stadium', stadium_options, STADIUM_ALL)
    selected_site = payload.get('site') or SITE_ALL
    if selected_site not in ('all', 'away', 'home'):
        selected_site = SITE_ALL
    team_options = payload.get('team_options') or [
        {'label': TEAM_ALL_LABEL, 'value': TEAM_ALL},
    ]
    selected_team = _menu_value(payload, 'team', team_options, TEAM_ALL)
    width_labels = payload.get('opponent_width_labels') or [
        item.get('label') for item in opponent_options if item.get('label')
    ]
    type_style = None if payload.get('game_type_visible') else {'display': 'none'}
    period_style = None if payload.get('period_visible') else {'display': 'none'}
    opponent_style = None if payload.get('opponent_visible') else {'display': 'none'}
    stadium_style = None if payload.get('stadium_visible') else {'display': 'none'}
    team_style = None if payload.get('team_visible') else {'display': 'none'}
    season_out = no_update if _same(selected_season, season_id) else selected_season
    type_out = no_update if _same(selected_type, game_type) else selected_type
    period_out = no_update if _same(selected_period, period) else selected_period
    opponent_out = no_update if _same(selected_opponent, opponent) else selected_opponent
    stadium_out = no_update if _same(selected_stadium, stadium) else selected_stadium
    site_out = no_update if _same(selected_site, site) else selected_site
    team_out = no_update if _same(selected_team, team) else selected_team
    # Same response as any select correction, so the bridge's applied State
    # already matches and that echo does not fetch again.
    applied = {
        'league': league or 'PLG',
        'season': season_id if season_out is no_update else selected_season,
        'game_type': game_type if type_out is no_update else selected_type,
        'ok': payload.get('ok') is not False,
    }
    return (
        _view(payload),
        _stamp(payload.get('stamp')),
        seasons,
        season_out,
        types,
        type_out,
        type_style,
        chips,
        period_out,
        period_style,
        applied,
        opponent_options,
        opponent_out,
        opponent_style,
        stadium_options,
        stadium_out,
        stadium_style,
        site_out,
        team_options,
        team_out,
        team_style,
        width_labels,
        {
            'team': selected_team,
            'opponent': selected_opponent,
            'stadium': selected_stadium,
            'site': selected_site,
        },
        chips,
        period_out,
        period_style,
    )


def _view_outputs():
    return (
        Output('ts-body', 'children', allow_duplicate=True),
        Output('ts-stamp', 'children', allow_duplicate=True),
        Output('ts-season', 'data', allow_duplicate=True),
        Output('ts-season', 'value', allow_duplicate=True),
        Output('ts-game-type', 'data', allow_duplicate=True),
        Output('ts-game-type', 'value', allow_duplicate=True),
        Output('ts-game-type-wrap', 'style', allow_duplicate=True),
        Output('ts-period', 'data', allow_duplicate=True),
        Output('ts-period', 'value', allow_duplicate=True),
        Output('ts-period-wrap', 'style', allow_duplicate=True),
        Output('ts-applied', 'data', allow_duplicate=True),
        Output('ts-opponent', 'data', allow_duplicate=True),
        Output('ts-opponent', 'value', allow_duplicate=True),
        Output('ts-opponent-cluster', 'style', allow_duplicate=True),
        Output('ts-stadium', 'data', allow_duplicate=True),
        Output('ts-stadium', 'value', allow_duplicate=True),
        Output('ts-stadium-cluster', 'style', allow_duplicate=True),
        Output('ts-site', 'value', allow_duplicate=True),
        Output('ts-team', 'data', allow_duplicate=True),
        Output('ts-team', 'value', allow_duplicate=True),
        Output('ts-team-cluster', 'style', allow_duplicate=True),
        Output('ts-opponent-width', 'data', allow_duplicate=True),
        Output('ts-slice', 'data', allow_duplicate=True),
        Output('ts-shot-period', 'data', allow_duplicate=True),
        Output('ts-shot-period', 'value', allow_duplicate=True),
        Output('ts-shot-period-bar', 'style', allow_duplicate=True),
    )


def _local_paint(payload, league, season_id, game_type, period, opponent, stadium, site, team=TEAM_ALL):
    painted = _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    )
    # applied stays. The slice outputs follow it. The job slot is the caller's.
    return painted[:10] + (no_update,) + painted[11:]


def _menu_hold(payload, league, season_id, game_type, period, opponent, stadium, site, team, job):
    """Schedule paint: menus and applied move, cards stay on the skeleton."""
    painted = _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    )
    return (_loading_body(), no_update) + painted[2:] + (job,)


def _card_job(intent, league, season_id, game_type, team, opponent, stadium, site):
    nonce = intent.get('nonce') if isinstance(intent, dict) else None
    return {
        'league': league,
        'season': season_id,
        'game_type': game_type,
        'team': team,
        'opponent': opponent,
        'stadium': stadium,
        'site': site,
        'skeleton': False,
        'phase': 'cards',
        'nonce': nonce,
    }


def _paint_from_chrome(
    reason, intent, league, season_id, game_type, period,
    opponent, stadium, site, team,
):
    reset = reason == 'scope'
    requested = None if reset else (
        intent.get('game_type') if isinstance(intent, dict) else game_type
    )
    try:
        chrome = schedule_chrome(
            league,
            season_id=season_id,
            game_type=requested,
            reset=reset,
            team=TEAM_ALL if reset else team,
            opponent=OPPONENT_ALL if reset else opponent,
            stadium=STADIUM_ALL if reset else stadium,
            site=SITE_ALL if reset else site,
        )
    except Exception:
        log_unexpected.exception('team stats schedule chrome failed')
        chrome = {
            'ok': False,
            'needs_cards': False,
            'message': ERROR_GAME,
            'stamp': 'Last Update: —',
            'season_id': season_id,
            'seasons': _season_data(league or 'PLG'),
            'game_types': [],
            'game_type': None,
            'game_type_visible': False,
            'period': 'all',
            'period_visible': False,
        }
    if chrome.get('ok') is False:
        return _paint(
            chrome, league, season_id, game_type, period, opponent, stadium, site, team,
        ) + (no_update,)
    resolved_season = chrome.get('season_id') or season_id
    if chrome.get('needs_cards'):
        job = _card_job(
            intent, league, resolved_season, chrome.get('game_type'),
            chrome.get('team', TEAM_ALL),
            chrome.get('opponent', OPPONENT_ALL),
            chrome.get('stadium', STADIUM_ALL),
            chrome.get('site', SITE_ALL),
        )
        return _menu_hold(
            chrome, league, season_id, game_type, period, opponent, stadium, site, team, job,
        )
    if reason == 'scope':
        payload = _load(
            league, resolved_season, None, 'all', 'scope',
            OPPONENT_ALL, STADIUM_ALL, SITE_ALL, TEAM_ALL,
        )
    else:
        chosen_type = chrome.get('game_type') if chrome.get('game_type') is not None else requested
        payload = _load(
            league, resolved_season, chosen_type, 'all', 'type',
            opponent, stadium, site, team,
        )
    return _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    ) + (no_update,)


@callback(
    *_view_outputs(),
    Output('ts-job', 'data'),
    Input('ts-intent', 'data'),
    Input('ts-period', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    Input('ts-team', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    prevent_initial_call='initial_duplicate',
)
def render_team_stats(intent, period, opponent, stadium, site, team, league, season_id, game_type):
    triggered = _triggered_id()
    # The click lives on ts-intent. Control State can still be the previous
    # value when this callback runs, so a league, season, or game-type click
    # loads from the store.
    clicked = triggered == 'ts-intent' and isinstance(intent, dict)
    if clicked:
        if intent.get('league'):
            league = intent.get('league')
        if intent.get('season') is not None:
            season_id = intent.get('season')
    if triggered == 'ts-period':
        reason = 'chip'
    elif triggered in ('ts-opponent', 'ts-stadium', 'ts-site', 'ts-team'):
        reason = 'slice'
    elif isinstance(intent, dict) and not intent.get('skeleton'):
        reason = 'type'
    else:
        reason = 'scope'
    if reason == 'type' or (reason == 'scope' and clicked):
        return _paint_from_chrome(
            reason, intent, league, season_id, game_type, period,
            opponent, stadium, site, team,
        )
    if reason in ('chip', 'slice'):
        payload = _load(
            league, season_id, game_type, period or 'all', reason,
            opponent, stadium, site, team,
        )
        return _local_paint(
            payload, league, season_id, game_type, period, opponent, stadium, site, team,
        ) + (no_update,)
    payload = _load(
        league, season_id, None, 'all', 'scope',
        OPPONENT_ALL, STADIUM_ALL, SITE_ALL, TEAM_ALL,
    )
    return _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    ) + (no_update,)


@callback(
    *_view_outputs(),
    Input('ts-job', 'data'),
    State('ts-intent', 'data'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-period', 'value'),
    State('ts-opponent', 'value'),
    State('ts-stadium', 'value'),
    State('ts-site', 'value'),
    State('ts-team', 'value'),
    prevent_initial_call=True,
)
def render_team_stats_download(
    job, intent, league, season_id, game_type, period,
    opponent=OPPONENT_ALL, stadium=STADIUM_ALL, site=SITE_ALL, team=TEAM_ALL,
):
    if not isinstance(job, dict) or not isinstance(intent, dict):
        raise PreventUpdate
    if job.get('nonce') != intent.get('nonce'):
        raise PreventUpdate
    league = job.get('league') or league or 'PLG'
    if job.get('season') is not None:
        season_id = job.get('season')
    requested_type = job.get('game_type') if isinstance(job, dict) else game_type
    load_opponent, load_stadium, load_site, load_team = opponent, stadium, site, team
    if job.get('phase') == 'cards':
        load_opponent = job.get('opponent', opponent)
        load_stadium = job.get('stadium', stadium)
        load_site = job.get('site', site)
        load_team = job.get('team', team)
    payload = _load(
        league, season_id, requested_type, 'all', 'type',
        load_opponent, load_stadium, load_site, load_team,
    )
    return _paint(
        payload, league, season_id, game_type, period, opponent, stadium, site, team,
    )


@callback(
    Output('ts-show-opp', 'checked'),
    Output('ts-show-opp', 'disabled'),
    Output('ts-show-opp-memory', 'data'),
    Input('ts-team', 'value'),
    State('ts-show-opp', 'checked'),
    State('ts-show-opp', 'disabled'),
    State('ts-show-opp-memory', 'data'),
    prevent_initial_call=True,
)
def lock_show_opp(team, checked, disabled, memory):
    """A single team forces Show Opp on and restores the All Teams choice."""
    single = bool(team) and team != TEAM_ALL
    if single:
        if disabled:
            return no_update, no_update, no_update
        return True, True, bool(checked)
    restored = False if memory is None else bool(memory)
    if bool(checked) == restored and not disabled:
        return no_update, no_update, no_update
    return restored, False, no_update


def _rotation_caption(aggregate):
    parts = ['{0} games'.format(int(aggregate.get('n') or 0))]
    seen = set()
    for column, sample in zip(aggregate.get('columns') or [], aggregate.get('counts') or []):
        period = column.get('period')
        if period in (1, 2, 3, 4) or period in seen or column.get('minute') != 0:
            continue
        seen.add(period)
        parts.append('{0} {1}'.format(period_label(period), sample))
    return ' · '.join(parts)


def _rotation_chart(figure, aggregate):
    height = int(getattr(figure.layout, 'height', None) or 520)
    return dmc.Paper(
        [
            dmc.Text(_rotation_caption(aggregate), size='sm', c='dimmed', mb=8),
            dcc.Graph(
                id='ts-rotation-graph',
                figure=figure,
                config={
                    'displayModeBar': False,
                    'responsive': True,
                    'scrollZoom': False,
                    'doubleClick': False,
                },
                style={'width': '100%', 'height': '{0}px'.format(height)},
            ),
        ],
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def _season_on_menu(league, season):
    """A season id from another league becomes that league's first season."""
    options = selectable_seasons(league) if league else []
    ids = [value for _label, value in options]
    if season in ids:
        return season
    if ids:
        return ids[0]
    return season


def _scope_pending(intent, applied):
    """True while a league, season, or game-type click has not painted yet."""
    if not isinstance(intent, dict):
        return False
    applied = applied if isinstance(applied, dict) else {}
    league = intent.get('league')
    if league and league != applied.get('league'):
        return True
    season = intent.get('season')
    if season is not None and _season_on_menu(league or applied.get('league'), season) != applied.get('season'):
        return True
    game_type = intent.get('game_type')
    if game_type and game_type != applied.get('game_type'):
        return True
    return False


@callback(
    Output('ts-rotation', 'children'),
    Input('ts-tabs', 'value'),
    Input('ts-applied', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-intent', 'data'),
    prevent_initial_call=True,
)
def render_team_rotation(
    tab, applied, team, opponent, stadium, site, league, season_id, game_type,
    intent=None,
):
    if tab != 'tab-rotation':
        raise PreventUpdate
    applied = applied if isinstance(applied, dict) else {}
    if _scope_pending(intent, applied):
        return loading_skeleton('chart')
    if applied.get('ok') is False:
        return error_alert(ERROR_GAME)
    league = applied.get('league') or league or 'PLG'
    if applied.get('season') is not None:
        season_id = applied.get('season')
    if applied.get('game_type') is not None:
        game_type = applied.get('game_type')
    if not team or team == TEAM_ALL:
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    try:
        source = rotation_games(
            league, season_id, game_type, opponent, stadium, site, team,
        )
    except Exception:
        log_unexpected.exception('team rotation page load failed')
        return error_alert(ERROR_GAME)
    if not source.get('ok'):
        return error_alert(source.get('message') or ERROR_GAME)
    if source.get('select_team'):
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    if source.get('empty') or not source.get('games'):
        return empty_state(EMPTY_TEAM_STATS, EMPTY_TEAM_STATS_NEXT)
    try:
        aggregate = season_aggregate(source)
    except Exception:
        log_unexpected.exception('team rotation aggregate failed')
        return error_alert(ERROR_GAME)
    if not aggregate.get('n') or not aggregate.get('players'):
        return empty_state(ROTATION_EMPTY, EMPTY_TEAM_STATS_NEXT)
    names = source.get('id_table') or {}
    opponent_id = aggregate.get('opponent')
    opponent_name = display_name(names, opponent_id) if opponent_id else None
    figure = build_team_rotation_figure(
        aggregate, display_name(names, source.get('team')), opponent_name,
    )
    return _rotation_chart(figure, aggregate)


@callback(
    Output('ts-shot-body', 'children'),
    Input('ts-tabs', 'value'),
    Input('ts-applied', 'data'),
    Input('ts-team', 'value'),
    Input('ts-opponent', 'value'),
    Input('ts-stadium', 'value'),
    Input('ts-site', 'value'),
    Input('ts-period', 'value'),
    State('ts-league', 'value'),
    State('ts-season', 'value'),
    State('ts-game-type', 'value'),
    State('ts-intent', 'data'),
    prevent_initial_call=True,
)
def render_team_shot_chart(
    tab, applied, team, opponent, stadium, site, period, league, season_id, game_type,
    intent=None,
):
    if tab != 'tab-shot-chart':
        raise PreventUpdate
    applied = applied if isinstance(applied, dict) else {}
    if _scope_pending(intent, applied):
        return shot_chart_skeleton()
    if applied.get('ok') is False:
        return error_alert(ERROR_GAME)
    league = applied.get('league') or league or 'PLG'
    if applied.get('season') is not None:
        season_id = applied.get('season')
    if applied.get('game_type') is not None:
        game_type = applied.get('game_type')
    if not team or team == TEAM_ALL:
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    try:
        source = rotation_games(
            league, season_id, game_type, opponent, stadium, site, team,
        )
    except Exception:
        log_unexpected.exception('team shot chart page load failed')
        return error_alert(ERROR_GAME)
    if not source.get('ok'):
        return error_alert(source.get('message') or ERROR_GAME)
    if source.get('select_team'):
        return empty_state(ROTATION_SELECT, ROTATION_SELECT_NEXT)
    if source.get('empty') or not source.get('games'):
        return empty_state(EMPTY_TEAM_STATS, EMPTY_TEAM_STATS_NEXT)
    names = source.get('id_table') or {}
    team_zones, opp_zones = season_zones(source.get('games'), source.get('team') or team, period or 'all')
    return _shot_courts(
        display_name(names, source.get('team') or team),
        team_zones,
        _opp_chart_name(source.get('opponent'), names),
        opp_zones,
    )
