import dash
from dash import Dash, page_container
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
        header={"height": 56},
        padding=0,
        className="app-shell",
        id="app-shell",
    )
)

if __name__ == '__main__':
    app.run(debug=True)
