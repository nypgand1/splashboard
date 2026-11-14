from dash import dcc, html
import dash_mantine_components as dmc

from ui_kit import icon


PAGE_LINKS = (
    {'label': 'Schedule', 'href': '/', 'section': 'schedule'},
    {'label': 'Team Stats', 'href': '/team-stats', 'section': 'team-stats'},
)


def _page_anchor(page):
    return dmc.Anchor(
        page['label'],
        href=page['href'],
        underline='never',
        className='app-page-link app-section-' + page['section'],
    )


def _page_menu_item(page):
    return dmc.MenuItem(
        page['label'],
        href=page['href'],
        className='app-page-menu-item app-section-' + page['section'],
    )


def create_navbar():
    brand = dmc.Anchor(
        dmc.Group(
            [
                dmc.Text('Splashboard', fw=800, fz='17px', c='#0f172a', style={'letterSpacing': '0.3px'}),
                dmc.Badge(
                    'TFB',
                    variant='gradient',
                    gradient={'from': '#0077b6', 'to': '#00b4d8', 'deg': 135},
                    size='sm',
                    radius='sm',
                    style={'fontWeight': 800, 'letterSpacing': '0.5px', 'color': '#ffffff'},
                ),
            ],
            gap=8,
            align='center',
            wrap='nowrap',
        ),
        href='/',
        underline='never',
        className='app-navbar-brand-link',
    )
    credit = dmc.Text(
        'Designed by Wei-Hao Lin',
        className='app-navbar-credit',
        span=True,
    )
    links = dmc.Group(
        [_page_anchor(page) for page in PAGE_LINKS],
        className='app-page-links',
        gap=0,
        align='center',
        wrap='nowrap',
    )
    menu = dmc.Box(
        dmc.Menu(
            [
                dmc.MenuTarget(
                    dmc.UnstyledButton(
                        dmc.Group(
                            [
                                'Menu',
                                icon('tabler:chevron-down', width=14, color='#1e293b'),
                            ],
                            gap=4,
                            align='center',
                            wrap='nowrap',
                        ),
                        className='app-navbar-menu-button',
                    )
                ),
                dmc.MenuDropdown(
                    [_page_menu_item(page) for page in PAGE_LINKS],
                    style={
                        'backgroundColor': 'rgba(255, 255, 255, 0.95)',
                        'backdropFilter': 'blur(20px)',
                        'border': '1px solid #e2e8f0',
                        'boxShadow': '0 10px 30px rgba(0, 0, 0, 0.08)',
                        'borderRadius': '10px',
                    },
                ),
            ],
            position='bottom-end',
            transitionProps={'transition': 'pop-top-right', 'duration': 150},
        ),
        className='app-navbar-menu',
    )
    return html.Div(
        [
            dmc.Box(
                [
                    brand,
                    html.Nav(
                        [links, menu],
                        id='app-page-nav',
                        className='app-page-nav',
                        **{'aria-label': 'Pages', 'data-mode': 'links'},
                    ),
                    credit,
                ],
                className='app-navbar-bar',
            ),
            dcc.Store(id='app-page-nav-sync'),
        ],
        className='app-navbar-frame',
    )
