from dash import html, dcc, callback, Input, Output, register_page
import dash_bootstrap_components as dbc

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser

LINKABLE_STATUSES = frozenset({'PENDING', 'IN_PROGRESS', 'FINISHED', 'CONFIRMED'})

register_page(
    __name__,
    name='Splashboard TFB | Home',
    top_nav=True,
    path='/'
)

def layout():
    return html.Div([
        dcc.Loading(
            type='circle',
            children=html.Div(
                id='home-game-list',
                children=html.Div('Loading...', className='p-4 text-center text-muted'),
            ),
        ),
    ])

@callback(
    Output('home-game-list', 'children'),
    Input('home-game-list', 'id'),
)
def load_home_game_list(_id):
    try:
        df = df_data()
    except Exception as exc:
        print(f"Error loading home game list: {exc}")
        return html.Div(
            'Failed to load games. Please try again later.',
            className='p-4 text-center text-danger',
        )
    if df is None or df.empty:
        return html.Div('No games available.', className='p-4 text-center text-muted')
    return dbc.Table.from_dataframe(df, striped=True, bordered=True, hover=True)

def df_data():
    game_list_df = Parser.parse_season_game_list_df(SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID)
    id_table = Parser.parse_id_tables(SYNERGY_ORGANIZATION_ID)
    
    try:
        from synergy_inbounder.runtime_cache import prefetch_latest_games
        prefetch_latest_games(game_list_df, max_games=2)
    except Exception as e:
        print(f"Failed to start home prefetch: {e}")
    
    df = game_list_df
    df['Time'] = df['startTimeLocal']
    df['Game Type'] = df['fixtureType']
    df['Venue'] = df.apply(lambda x: id_table.get(x['venueId'], x['venueId']), axis=1)
    df['Home Team'] = df.apply(lambda x: id_table.get(x['teamIdHome'], x['teamIdHome']), axis=1)
    df['Away Team'] = df.apply(lambda x: id_table.get(x['teamIdAway'], x['teamIdAway']), axis=1)
    df['Score'] = df.apply(lambda x: html.A(html.P('{h} : {a}'.format(h=x['teamScoreHome'], a=x['teamScoreAway'])), 
        href='/game/{url}'.format(url=x['fixtureId']))
            if str(x['status']).strip() in LINKABLE_STATUSES else x['status'], axis=1)
    
    return df[['Time', 'Game Type','Venue', 'Home Team', 'Score', 'Away Team']]

