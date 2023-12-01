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
app.layout = html.Div([
        NAVBAR,
        page_container
    ])

if __name__ == '__main__':
    app.run(debug=True)
