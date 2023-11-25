from dash import html
import dash_bootstrap_components as dbc

def create_navbar():
    navbar = dbc.NavbarSimple(
        children=[
            dbc.DropdownMenu(
                nav=True,
                in_navbar=True,
                label='Menu',
                align_end=True,
                children=[  # Add as many menu items as you need
                    dbc.DropdownMenuItem('Home', href='/'),
                    dbc.DropdownMenuItem(divider=True),
                ],
            ),
        ],
        brand='Splashboard TFB',
        brand_href='/',
        sticky='top',  # Uncomment if you want the navbar to always appear at the top on scroll.
        color='#008CCA',  # Change this to change color of the navbar e.g. "primary", "secondary" etc.
        dark=True,  # Change this to change color of text within the navbar (False for dark text)
    )

    return navbar
