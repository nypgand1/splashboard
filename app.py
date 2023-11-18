from dash import Dash, html, dcc, callback, Output, Input, dash_table
import dash_bootstrap_components as dbc

import plotly.express as px
import pandas as pd

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser

game_list_df = Parser.parse_season_game_list_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)
id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)



app = Dash(external_stylesheets=[dbc.themes.LITERA])

app.layout = html.Div([
    html.H1(children='Splashboard', style={'textAlign':'center'}),
    dash_table.DataTable(
        data=game_list_df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in game_list_df.columns])
])

if __name__ == '__main__':
    app.run(debug=True)
