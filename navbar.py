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


def _account_control(user):
    if user is None:
        return dmc.Anchor(
            'Log in',
            href='/login',
            underline='never',
            className='app-account-menu app-account-login',
        )
    items = [
        dmc.Text(user.email, className='app-account-email'),
        html.Hr(className='app-account-divider'),
    ]
    if getattr(user, 'role', None) == 'admin':
        items.append(
            dmc.Anchor(
                [
                    html.Span(
                        icon('tabler:settings', width=16, height=16),
                        className='app-account-item-icon',
                        **{'aria-hidden': 'true'},
                    ),
                    html.Span('Admin', className='app-account-item-label'),
                ],
                href='/admin',
                underline='never',
                className='app-account-admin',
            )
        )
    items.append(
        html.Form(
            html.Button(
                [
                    html.Span(
                        icon('tabler:logout', width=16, height=16),
                        className='app-account-item-icon',
                        **{'aria-hidden': 'true'},
                    ),
                    html.Span('Logout', className='app-account-item-label'),
                ],
                className='app-account-logout',
            ),
            method='post',
            action='/logout',
            className='app-account-logout-form',
        )
    )
    return dmc.Box(
        dmc.Menu(
            [
                dmc.MenuTarget(
                    dmc.UnstyledButton(
                        html.Span(
                            icon(
                                'tabler:user-circle',
                                width=20,
                                height=20,
                            ),
                            className='app-account-icon',
                            **{'aria-hidden': 'true'},
                        ),
                        className='app-account-button',
                        **{'aria-label': 'Account'},
                    )
                ),
                dmc.MenuDropdown(items, className='app-account-dropdown'),
            ],
            position='bottom-end',
            transitionProps={'transition': 'pop-top-right', 'duration': 150},
        ),
        className='app-account-menu',
    )


def create_navbar(user=None):
    brand_link = dmc.Anchor(
        dmc.Group(
            [
                dmc.Text(
                    'Splashboard',
                    fw=800,
                    fz='17px',
                    c='#0f172a',
                    className='app-navbar-wordmark',
                    style={'letterSpacing': '0.3px'},
                ),
                dmc.Badge(
                    'TFB',
                    variant='gradient',
                    gradient={'from': '#0077b6', 'to': '#00b4d8', 'deg': 135},
                    size='sm',
                    radius='sm',
                    className='app-navbar-badge',
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
    brand = dmc.Box(
        [brand_link, credit],
        className='app-navbar-brand',
    )
    links = dmc.Group(
        [_page_anchor(page) for page in PAGE_LINKS],
        className='app-page-links',
        gap=6,
        align='center',
        wrap='nowrap',
    )
    return html.Div(
        [
            dmc.Box(
                [
                    brand,
                    html.Nav(
                        [links],
                        id='app-page-nav',
                        className='app-page-nav',
                        **{'aria-label': 'Pages'},
                    ),
                    _account_control(user),
                ],
                className='app-navbar-bar',
            ),
            dcc.Store(id='app-page-nav-sync'),
        ],
        className='app-navbar-frame',
    )
