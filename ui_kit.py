import dash_mantine_components as dmc
from dash_iconify import DashIconify

from synergy_inbounder.game_status import (
    BADGE_STYLES,
    SCORE_AT,
    badge_label,
    format_score_display,
    status_bucket,
)

SCORE_COLOR = '#0077b6'
SCORE_FZ = '22px'
SCORE_SLOT_STYLE = {
    'fontVariantNumeric': 'tabular-nums',
    'flexShrink': 0,
}

ERROR_HOME = 'Failed to load games. Please try again later.'
ERROR_GAME = 'Failed to load this view. Please try again later.'
EMPTY_HOME = 'No games available.'
EMPTY_HOME_NEXT = 'Check back when the season schedule is published.'
EMPTY_HOME_FILTER = 'No games in this view.'
EMPTY_HOME_FILTER_NEXT = 'Switch Game Type or Show.'
EMPTY_GAME = 'No data available.'
EMPTY_GAME_NEXT = 'Open another game from Home.'


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


def matchup_score_parts(status, home_score, away_score):
    display = format_score_display(status, home_score, away_score)
    if display == SCORE_AT:
        return None, None
    away_text, home_text = display.split(' : ', 1)
    return away_text, home_text


def team_name_text(name, ta):
    return dmc.Text(
        name,
        fw=800,
        fz='16px',
        ta=ta,
        truncate=True,
        flex=1,
        miw=0,
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
