from dash import Dash, html, dcc, page_container
import dash_bootstrap_components as dbc
from navbar import create_navbar

app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.LITERA,
        dbc.icons.BOOTSTRAP,
        'https://cdn.jsdelivr.net/npm/gridstack@10.3.1/dist/gridstack.min.css',
        '/assets/report.css',
    ],
    external_scripts=[
        'https://cdn.jsdelivr.net/npm/gridstack@10.3.1/dist/gridstack-all.js',
        'https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js',
        '/assets/report_canvas.js',
    ],
    title='Splashboard TFB',
    use_pages=True,
    suppress_callback_exceptions=True,
    backend="fastapi"
)
server = app.server

NAVBAR = create_navbar()
app.layout = html.Div([
    html.Div(NAVBAR, className="no-print"),
    page_container
])

if __name__ == '__main__':
    app.run(debug=True)
