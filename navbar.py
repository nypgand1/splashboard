import dash_mantine_components as dmc
from dash import html

def create_navbar():
    brand = dmc.Anchor(
        dmc.Group(
            [
                dmc.Text("Splashboard", fw=800, fz="17px", c="#0f172a", style={"letterSpacing": "0.3px"}),
                dmc.Badge(
                    "TFB",
                    variant="gradient",
                    gradient={"from": "#0077b6", "to": "#00b4d8", "deg": 135},
                    size="sm",
                    radius="sm",
                    style={"fontWeight": 800, "letterSpacing": "0.5px", "color": "#ffffff"}
                ),
            ],
            gap=8,
            align="center",
        ),
        href="/",
        underline="never",
        style={"display": "flex", "alignItems": "center"}
    )
    
    menu = dmc.Menu(
        [
            dmc.MenuTarget(
                dmc.Button(
                    "Menu",
                    variant="subtle",
                    size="sm",
                    c="#1e293b",
                    rightSection=html.I(className="bi bi-chevron-down", style={"fontSize": "11px"}),
                    style={
                        "backgroundColor": "#f1f5f9",
                        "border": "1px solid #e2e8f0",
                        "borderRadius": "8px",
                        "fontWeight": 600,
                    }
                )
            ),
            dmc.MenuDropdown(
                [
                    dmc.MenuItem(
                        "Home",
                        href="/",
                        leftSection=html.I(className="bi bi-house", style={"fontSize": "13px", "color": "#0077b6"}),
                        style={"fontWeight": 600, "color": "#1e293b"}
                    ),
                ],
                style={
                    "backgroundColor": "rgba(255, 255, 255, 0.95)",
                    "backdropFilter": "blur(20px)",
                    "border": "1px solid #e2e8f0",
                    "boxShadow": "0 10px 30px rgba(0, 0, 0, 0.08)",
                    "borderRadius": "10px",
                }
            ),
        ],
        position="bottom-end",
        transitionProps={"transition": "pop-top-right", "duration": 150},
    )
    
    return html.Div(
        dmc.Group(
            [brand, menu],
            justify="space-between",
            align="center",
            h="100%",
            style={"padding": "0 20px"},
        ),
        className="app-navbar no-print",
        style={
            "height": "56px",
            "width": "100%",
            "zIndex": 100,
            "backgroundColor": "rgba(255, 255, 255, 0.95)",
            "backdropFilter": "blur(16px)",
            "WebkitBackdropFilter": "blur(16px)",
            "borderBottom": "2px solid #00b4d8",
            "boxShadow": "0 2px 12px rgba(0, 0, 0, 0.04)",
        }
    )

