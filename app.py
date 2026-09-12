import dash
from dash import Dash, page_container
import dash_mantine_components as dmc
from navbar import create_navbar

# Configure React 18 for DMC 2.8.0
dash._dash_renderer._set_react_version('18.2.0')

MANTINE_THEME = {
    "primaryColor": "cyan",
    "fontFamily": '-apple-system, "PingFang TC", "Noto Sans TC", "Segoe UI", Roboto, sans-serif',
    "defaultRadius": "md",
    "colors": {
        "cyan": [
            "#e0f7fa",
            "#b2ebf2",
            "#80deea",
            "#4dd0e1",
            "#26c6da",
            "#00b4d8",
            "#0096c7",
            "#0077b6",
            "#023e8a",
            "#03045e",
        ],
        "bravesBlue": [
            "#e8f4f8",
            "#cce9f2",
            "#99d4e5",
            "#66bed8",
            "#33a9cb",
            "#00b4d8",
            "#0077b6",
            "#005f92",
            "#00476d",
            "#002f49",
        ]
    }
}

app = Dash(
    __name__,
    assets_ignore=r'gridstack.*|jspdf\.umd\.min\.js',
    external_stylesheets=[],
    external_scripts=[],
    title='Splashboard TFB',
    use_pages=True,
    suppress_callback_exceptions=True,
    backend="fastapi"
)
server = app.server

NAVBAR = create_navbar()
app.layout = dmc.MantineProvider(
    theme=MANTINE_THEME,
    forceColorScheme="light",
    children=dmc.AppShell(
        [
            dmc.AppShellHeader(
                NAVBAR,
                className="app-navbar no-print",
                px=0,
            ),
            dmc.AppShellMain(page_container, className="app-main-content"),
        ],
        header={"height": 56},
        padding=0,
        className="app-shell",
        id="app-shell",
    )
)

if __name__ == '__main__':
    app.run(debug=True)
