import dash
from dash import Dash, Input, Output, clientside_callback, page_container
import dash_mantine_components as dmc
from asset_url import stamp_asset_urls
from navbar import create_navbar
from ui.tokens import MANTINE_THEME as _TOKENS_MANTINE_THEME

# Configure React 18 for DMC 2.8.0
dash._dash_renderer._set_react_version('18.2.0')

MANTINE_THEME = {
    **_TOKENS_MANTINE_THEME,
    "primaryColor": "bravesBlue",
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
stamp_asset_urls(app.css._resources)
stamp_asset_urls(app.scripts._resources)

# One pass after the parser has waited on the head stylesheets. A failed
# same-origin sheet has no CSSStyleSheet; clone it once and drop the failed node.
_STYLESHEET_RETRY = """<script>
(function () {
  var links = document.querySelectorAll('head link[rel="stylesheet"]');
  for (var i = 0; i < links.length; i++) {
    var link = links[i];
    if (link.getAttribute('data-retry')) {
      continue;
    }
    var loaded = false;
    try {
      loaded = !!link.sheet;
    } catch (err) {
      loaded = false;
    }
    if (loaded) {
      continue;
    }
    var next = link.cloneNode(false);
    next.setAttribute('data-retry', '1');
    if (!link.parentNode) {
      continue;
    }
    link.parentNode.insertBefore(next, link.nextSibling);
    link.parentNode.removeChild(link);
  }
})();
</script>"""

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        """ + _STYLESHEET_RETRY + """
    </head>
    <body>
        <!--[if IE]><script>
        alert("Dash v2.7+ does not support Internet Explorer. Please use a newer browser.");
        </script><![endif]-->
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""

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
        header={"height": 72},
        padding=0,
        className="app-shell",
        id="app-shell",
    )
)

clientside_callback(
    """
    function(pathname) {
        var api = window.dash_clientside && window.dash_clientside.page_nav;
        if (api && api.sync) {
            api.sync(pathname);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('app-page-nav-sync', 'data'),
    Input('_pages_location', 'pathname'),
)

# FastAPI runs this hook only for `/` and `/_dash-*`. A cold first GET of
# `/team-stats` or `/game/...` would otherwise render index() before assets
# are walked, so the HTML omits assets/report.css and assets/*.js. Setup
# clears the global callback list tests read. Copy it back. The flag stays
# set, so a later request does not register those callbacks twice.
import dash._callback as _dash_callback

app._setup_server()
_dash_callback.GLOBAL_CALLBACK_LIST.extend(app._callback_list)


if __name__ == '__main__':
    app.run(debug=True)
