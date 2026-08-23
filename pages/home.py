from dash import html, dcc, callback, Input, Output, register_page, clientside_callback
import dash_ag_grid as dag

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser

register_page(
    __name__,
    name='Splashboard TFB | Home',
    top_nav=True,
    path='/'
)

def layout():
    return html.Div([
        dcc.Location(id='home-url-redirect', refresh=True),
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
    
    column_defs = [
        {"field": "Time", "sortable": True, "filter": True, "minWidth": 150},
        {
            "field": "Status",
            "sortable": True,
            "filter": True,
            "minWidth": 130,
            "cellRenderer": "ScheduleStatusBadge",
        },
        {"field": "Game Type", "sortable": True, "filter": True, "minWidth": 120},
        {"field": "Venue", "sortable": True, "filter": True, "minWidth": 140},
        {"field": "Home Team", "sortable": True, "filter": True, "minWidth": 150},
        {
            "field": "Score",
            "sortable": True,
            "filter": True,
            "minWidth": 120,
            "cellRenderer": "ScheduleScoreLink",
        },
        {"field": "Away Team", "sortable": True, "filter": True, "minWidth": 150},
    ]

    return dag.AgGrid(
        id='home-schedule-grid',
        rowData=df.to_dict('records'),
        columnDefs=column_defs,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            "domLayout": "autoHeight",
            "rowSelection": "single",
        },
        columnSize="autoSize",
        className="ag-theme-alpine braves-clean-ag-grid",
        style={'width': '100%'}
    )


# Clientside callback to navigate to /game/<fixtureId> when any cell is clicked
clientside_callback(
    """
    function(cellClicked) {
        if (cellClicked && cellClicked.data && cellClicked.data.fixtureId) {
            window.location.href = '/game/' + cellClicked.data.fixtureId;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('home-url-redirect', 'href'),
    Input('home-schedule-grid', 'cellClicked'),
    prevent_initial_call=True,
)


def _format_score_text(row):
    status = str(row.get('status', '')).strip()
    if status in ('FINISHED', 'CONFIRMED', 'IN_PROGRESS'):
        return f"{row['teamScoreHome']} : {row['teamScoreAway']}"
    if status == 'PENDING':
        return "- : -"
    return str(status or '-')


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
    df['Status'] = df['status'].astype(str).str.strip()
    df['rawStatus'] = df['Status']
    df['Game Type'] = df['fixtureType']
    df['Venue'] = df.apply(lambda x: id_table.get(x['venueId'], x['venueId']), axis=1)
    df['Home Team'] = df.apply(lambda x: id_table.get(x['teamIdHome'], x['teamIdHome']), axis=1)
    df['Away Team'] = df.apply(lambda x: id_table.get(x['teamIdAway'], x['teamIdAway']), axis=1)
    df['Score'] = df.apply(_format_score_text, axis=1)
    
    return df[['Time', 'Status', 'rawStatus', 'Game Type', 'Venue', 'Home Team', 'Score', 'Away Team', 'fixtureId']]

