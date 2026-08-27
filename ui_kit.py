import dash_mantine_components as dmc
from dash_iconify import DashIconify

ERROR_HOME = 'Failed to load games. Please try again later.'
ERROR_GAME = 'Failed to load this view. Please try again later.'
EMPTY_HOME = 'No games available.'
EMPTY_HOME_NEXT = 'Check back when the season schedule is published.'
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
