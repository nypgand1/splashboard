# -*- coding: utf-8 -*-
import re

from dash import html
from dash.development.base_component import Component
from dash_iconify import DashIconify
import dash_mantine_components as dmc

from synergy_inbounder.game_status import (
    BADGE_STYLES,
    SCORE_AT,
    badge_label,
    format_score_display,
    status_bucket,
)
from synergy_inbounder.names import contains_cjk
from ui.tokens import (
    BRAND_PRIMARY,
    COURT_CARD_STYLE,
    COURT_COLUMN_STYLE,
    SCORE_FZ,
    SCORE_SLOT_STYLE,
)

SCORE_COLOR = BRAND_PRIMARY

ERROR_HOME = 'Failed to load games. Please try again later.'
ERROR_GAME = 'Failed to load this view. Please try again later.'
REFRESH_DELAYED = 'Refresh delayed. Showing the last update.'
EMPTY_HOME = 'No games available.'
EMPTY_HOME_NEXT = 'Check back when the season schedule is published.'
EMPTY_HOME_FILTER = 'No games in this view.'
EMPTY_HOME_FILTER_NEXT = 'Switch Game Type or Show.'
EMPTY_HOME_FILTER_TEAM_NEXT = 'Switch Game Type, Show, or Team.'
EMPTY_GAME = 'No data available.'
EMPTY_GAME_NEXT = 'Open another game from Home.'
EMPTY_MATCHUPS = 'No 5-player matchups for this game.'


def to_jsonable(node):
    if isinstance(node, Component):
        spec = node.to_plotly_json()
        spec['props'] = {
            key: to_jsonable(value) for key, value in spec['props'].items()
        }
        return spec
    if isinstance(node, (list, tuple)):
        return [to_jsonable(item) for item in node]
    if isinstance(node, dict):
        return {key: to_jsonable(value) for key, value in node.items()}
    return node


def icon(name, width=16, color=None, **kwargs):
    props = {'icon': name, 'width': width}
    if color:
        props['color'] = color
    props.update(kwargs)
    return DashIconify(**props)


def loading_skeleton(kind='table'):
    if kind == 'cards':
        return dmc.SimpleGrid(
            cols={'base': 1, 'sm': 3},
            spacing='12px',
            children=[dmc.Skeleton(height=140, radius='md') for _ in range(3)],
        )
    if kind == 'chart':
        return dmc.Stack(
            [
                dmc.Skeleton(height=28, radius='sm'),
                dmc.Skeleton(height=520, radius='md'),
            ],
            gap=8,
        )
    return dmc.Stack(
        [dmc.Skeleton(h=28, radius='sm') for _ in range(8)],
        gap=8,
    )


def error_alert(message):
    return dmc.Alert(message, title='Error', color='red')


def empty_state(message, next_step):
    return dmc.Stack(
        [
            dmc.Text(message, ta='center'),
            dmc.Text(next_step, ta='center', c='dimmed', size='sm'),
        ],
        gap=6,
        py='md',
    )


def last_update_line(label=None, delayed=False):
    text = label or 'Last Update: —'
    line = dmc.Text(
        text,
        size='sm',
        c='dimmed',
        mb=0 if delayed else 8,
        className='no-print',
    )
    if not delayed:
        return line
    return [
        line,
        dmc.Text(
            REFRESH_DELAYED,
            size='sm',
            c='dimmed',
            mb=8,
            className='no-print',
        ),
    ]


def shot_court_column(children):
    return dmc.Stack(
        children,
        gap='xs',
        align='center',
        style=dict(COURT_COLUMN_STYLE),
    )


def shot_chart_paper(children, card_id=None):
    props = {
        'withBorder': True,
        'radius': 'md',
        'shadow': 'xs',
        'p': 'md',
        'className': 'braves-card-wrapper',
        'style': dict(COURT_CARD_STYLE),
    }
    if card_id is not None:
        props['id'] = card_id
    return dmc.Paper(children, **props)


def filter_control(label, control, wrap_id=None, visible=True):
    props = {
        'gap': '10px',
        'align': 'center',
        'style': None if visible else {'display': 'none'},
    }
    if wrap_id is not None:
        props['id'] = wrap_id
    children = []
    if label:
        children.append(
            dmc.Text(
                label,
                size='xs',
                fw=700,
                c='dimmed',
                style={'letterSpacing': '0.05em'},
            )
        )
    children.append(control)
    return dmc.Group(
        children,
        **props,
    )


def filter_cluster(kind, children, cluster_id=None, style=None):
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


def filter_pack(pack_id, clusters):
    """Measured filter rows. ``clusters`` are ``(kind, children)`` for league, team, and type."""
    nodes = [filter_cluster(kind, children) for kind, children in clusters]
    return dmc.Box(nodes, id=pack_id, className='filter-pack')


def sized_select(select_id, probe_id, label, data, value, probe_class='ts-sizer-probes'):
    probe_spans = (
        [
            html.Span(
                item,
                className='home-team-sizer-probe',
                **{'aria-hidden': 'true'},
            )
            for item in label
        ]
        if isinstance(label, (list, tuple))
        else html.Span(
            label,
            className='home-team-sizer-probe',
            **{'aria-hidden': 'true'},
        )
    )
    probe_props = {'children': probe_spans}
    if probe_id is not None:
        probe_props['id'] = probe_id
    if probe_class is not None:
        probe_props['className'] = probe_class
    return html.Div(
        [
            html.Div(**probe_props) if probe_id is not None else html.Div(probe_spans),
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


def matchup_score_parts(status, home_score, away_score):
    display = format_score_display(status, home_score, away_score)
    if display == SCORE_AT:
        return None, None
    away_text, home_text = display.split(' : ', 1)
    return away_text, home_text


_LATIN = re.compile(r'[A-Za-z]')
TEAM_NAME_PHONE_LIMIT = 12


def team_name_lines(name, limit=TEAM_NAME_PHONE_LIMIT):
    """Phone split for a long Latin team name.

    Three words whose first two fit in the limit: those two, then the last
    word. The space counts. Otherwise line 2 is the last two words.
    """
    text = '' if name is None else str(name).strip()
    if (
        not text
        or contains_cjk(text)
        or not _LATIN.search(text)
        or len(text) <= limit
        or ' ' not in text
    ):
        return (text, None)
    words = text.split()
    if len(words) == 3 and len(words[0]) + 1 + len(words[1]) <= limit:
        return (f'{words[0]} {words[1]}', words[2])
    if len(words) == 2:
        return (words[0], words[1])
    return (' '.join(words[:-2]), ' '.join(words[-2:]))


def team_name_text(name, ta):
    shown = '' if name is None else name
    props = dict(fw=800, fz='16px', ta=ta, truncate=True, flex=1, miw=0)
    first, second = team_name_lines(shown)
    if second is None:
        return dmc.Text(shown, **props)
    wide = dmc.Text(shown, className='team-name-wide', **props)
    narrow = dmc.Stack(
        [
            dmc.Text(
                first,
                fw=800,
                fz='16px',
                ta=ta,
                truncate=True,
                style={'lineHeight': '1.15', 'whiteSpace': 'nowrap'},
            ),
            dmc.Text(
                second,
                fw=800,
                fz='16px',
                ta=ta,
                truncate=False,
                style={'lineHeight': '1.15', 'whiteSpace': 'nowrap'},
            ),
        ],
        gap=0,
        className='team-name-narrow',
        w='100%',
    )
    return dmc.Box(
        [wide, narrow],
        flex=1,
        miw=0,
        style={'minWidth': 0, 'overflow': 'hidden'},
    )


def score_well(away_display, home_display):
    if away_display is None:
        children = [
            dmc.Box(miw='3ch', style={'flexShrink': 0}),
            dmc.Text('@', fw=800, fz=SCORE_FZ, c=SCORE_COLOR, ta='center'),
            dmc.Box(miw='3ch', style={'flexShrink': 0}),
        ]
    else:
        children = [
            dmc.Text(
                away_display,
                fw=900,
                fz=SCORE_FZ,
                c=SCORE_COLOR,
                ta='right',
                miw='3ch',
                style=SCORE_SLOT_STYLE,
            ),
            dmc.Text(':', fw=700, fz='16px', c='dimmed'),
            dmc.Text(
                home_display,
                fw=900,
                fz=SCORE_FZ,
                c=SCORE_COLOR,
                ta='left',
                miw='3ch',
                style=SCORE_SLOT_STYLE,
            ),
        ]
    return dmc.Group(
        children,
        gap=4,
        align='center',
        justify='center',
        wrap='nowrap',
        className='home-score-well',
        style={'flexShrink': 0},
    )


def matchup_line(away_team, home_team, away_display, home_display):
    return dmc.Group(
        [
            team_name_text(away_team, 'right'),
            score_well(away_display, home_display),
            team_name_text(home_team, 'left'),
        ],
        gap=8,
        align='center',
        wrap='nowrap',
        className='home-schedule-score-line',
        style={'width': '100%', 'minWidth': 0},
    )


def join_meta(*parts):
    return ' | '.join(part for part in parts if part)


def status_badge(status, size):
    bucket = status_bucket(status)
    return dmc.Badge(
        badge_label(status),
        variant='light',
        size=size,
        radius='sm',
        style={'fontWeight': 700, 'flexShrink': 0, **BADGE_STYLES[bucket]},
    )


def meta_cluster(meta_text, badge):
    return dmc.Group(
        [
            dmc.Group(
                [
                    dmc.Text(
                        meta_text,
                        size='xs',
                        c='dimmed',
                        truncate=True,
                        miw=0,
                    ),
                    badge,
                ],
                gap='sm',
                align='center',
                wrap='nowrap',
                className='home-schedule-meta-cluster',
                miw=0,
                maw='100%',
            ),
        ],
        justify='center',
        wrap='nowrap',
        className='home-schedule-meta-line',
        style={'width': '100%', 'minWidth': 0},
    )


def game_banner(
    home_team,
    away_team,
    home_score,
    away_score,
    status,
    date='',
    time='',
    venue='',
    mb='md',
):
    away_display, home_display = matchup_score_parts(status, home_score, away_score)
    return dmc.Paper(
        dmc.Stack(
            [
                matchup_line(away_team, home_team, away_display, home_display),
                meta_cluster(
                    join_meta(date, time, venue),
                    status_badge(status, 'md'),
                ),
            ],
            gap=4,
        ),
        withBorder=True,
        radius='md',
        p='md',
        mb=mb,
        shadow='xs',
        className='braves-card-wrapper game-info-banner',
    )
