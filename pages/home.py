from dash import html, dcc, callback, Input, Output, register_page
import dash_ag_grid as dag

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID, SYNERGY_SEASON_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.game_status import (
    format_score_display,
    score_is_clickable,
    status_bucket,
)
from ui_kit import (
    EMPTY_HOME,
    EMPTY_HOME_NEXT,
    ERROR_HOME,
    empty_state,
    error_alert,
    loading_skeleton,
)

register_page(
    __name__,
    name='Splashboard TFB | Home',
    top_nav=True,
    path='/'
)

_CENTER = {
    "cellStyle": {"textAlign": "center"},
    "cellClass": "ag-cell-align-center",
    "headerClass": "ag-header-align-center",
}


def layout():
    return html.Div([
        dcc.Loading(
            custom_spinner=loading_skeleton(),
            children=html.Div(
                id='home-game-list',
                children=loading_skeleton(),
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
        return error_alert(ERROR_HOME)
    if df is None or df.empty:
        return empty_state(EMPTY_HOME, EMPTY_HOME_NEXT)

    column_defs = [
        {"field": "Time", "sortable": True, "filter": True, "minWidth": 150, **_CENTER},
        {
            "field": "Status",
            "sortable": True,
            "filter": True,
            "minWidth": 130,
            "cellRenderer": "ScheduleStatusBadge",
            **_CENTER,
        },
        {"field": "Game Type", "sortable": True, "filter": True, "minWidth": 120, **_CENTER},
        {"field": "Venue", "sortable": True, "filter": True, "minWidth": 140, **_CENTER},
        {"field": "Home Team", "sortable": True, "filter": True, "minWidth": 150, **_CENTER},
        {
            "field": "Score",
            "sortable": True,
            "filter": True,
            "minWidth": 120,
            "cellRenderer": "ScheduleScoreLink",
            **_CENTER,
        },
        {"field": "Away Team", "sortable": True, "filter": True, "minWidth": 150, **_CENTER},
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
    df['Score'] = df.apply(
        lambda x: format_score_display(x.get('status'), x.get('teamScoreHome'), x.get('teamScoreAway')),
        axis=1,
    )
    df['statusBucket'] = df['status'].apply(status_bucket)
    df['scoreClickable'] = df['status'].apply(score_is_clickable)

    return df[[
        'Time', 'Status', 'rawStatus', 'Game Type', 'Venue',
        'Home Team', 'Score', 'Away Team', 'fixtureId',
        'statusBucket', 'scoreClickable',
    ]]
