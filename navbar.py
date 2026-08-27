import dash_mantine_components as dmc

from ui_kit import icon


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
                    rightSection=icon("tabler:chevron-down", width=14),
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
                        leftSection=icon("tabler:home", width=14, color="#0077b6"),
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

    return dmc.Group(
        [brand, menu],
        justify="space-between",
        align="center",
        h="100%",
        px="md",
    )
