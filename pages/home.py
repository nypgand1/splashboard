from dash import html, dash_table, register_page

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser

register_page(
    __name__,
    name='Splashboard TFB | Home',
    top_nav=True,
    path='/'
)

def layout():
    df = df_data()
    layout = html.Div([
        dash_table.DataTable(
            data=df.to_dict('records'),
            columns=[{'name': i, 'id': i} for i in df.columns])
    ])
    return layout

def df_data():
    game_list_df = Parser.parse_season_game_list_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)
    
    df = game_list_df
    df['Time'] = df['startTimeLocal']
    df['Venue'] = df.apply(lambda x: id_table.get(x['venueId'], x['venueId']), axis=1)
    df['Home Team'] = df.apply(lambda x: id_table.get(x['teamIdHome'], x['teamIdHome']), axis=1)
    df['Away Team'] = df.apply(lambda x: id_table.get(x['teamIdAway'], x['teamIdAway']), axis=1)
    df['Score'] = df.apply(lambda x: '{h}:{a}'.format(h=x['teamScoreHome'], a=x['teamScoreAway']), axis=1)
    
    return df[['Time', 'Venue', 'Home Team', 'Score', 'Away Team', 'fixtureId']]

