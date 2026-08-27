import dash_mantine_components as dmc
from dash_iconify import DashIconify

from synergy_inbounder.game_status import BADGE_STYLES, badge_label, status_bucket

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
        return dmc.Skeleton(height=360, radius='md')
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
    return dmc.Group(
        [
            dmc.Text(
                label,
                size='xs',
                fw=700,
                c='dimmed',
                style={'letterSpacing': '0.05em'},
            ),
            control,
        ],
        **props,
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
    bucket = status_bucket(status)
    badge_style = {
        'fontWeight': 700,
        **BADGE_STYLES[bucket],
    }
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Group(
                        [
                            dmc.Text(away_team, fw=800, fz='16px'),
                            dmc.Text(str(away_score), fw=900, fz='22px', c='#0077b6'),
                            dmc.Text('vs', fw=700, fz='13px', c='dimmed'),
                            dmc.Text(str(home_score), fw=900, fz='22px', c='#0077b6'),
                            dmc.Text(home_team, fw=800, fz='16px'),
                        ],
                        gap='sm',
                        align='center',
                    ),
                    dmc.Badge(
                        badge_label(status),
                        variant='light',
                        size='md',
                        radius='sm',
                        style=badge_style,
                    ),
                ],
                justify='space-between',
                align='center',
                wrap='wrap',
                gap='sm',
                mb=4,
            ),
            dmc.Text(
                ' • '.join(part for part in (date, time, venue) if part),
                size='xs',
                c='dimmed',
                fw=500,
            ),
        ],
        withBorder=True,
        radius='md',
        p='md',
        mb=mb,
        shadow='xs',
        className='braves-card-wrapper game-info-banner',
    )
