from dash import Dash, html, dcc, page_container
import dash_bootstrap_components as dbc
from navbar import create_navbar

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.LITERA],
    title='Splashboard TFB',
    use_pages=True,
)
server = app.server

NAVBAR = create_navbar()
app.layout = dcc.Loading(
    id='loading_page_content',
    children=[
        html.Div(
            [
                NAVBAR,
                page_container
            ]
        )
    ],
    color='primary',
    fullscreen=True
)

if __name__ == '__main__':
    app.run(debug=True)
