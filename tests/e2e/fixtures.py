import pandas as pd

HOME = 'Taipei Fubon Braves'
AWAY = 'Formosa Dreamers'
HOME_ID = 'home-id'
AWAY_ID = 'away-id'
VENUE_ID = 'venue-id'
VENUE = 'Taipei Arena'

LIVE_ID = 'live-regular'
UPCOMING_ID = 'up-playoff'
FINISHED_ID = 'fin-regular'
ABANDONED_ID = 'abd-regular'
CANCELLED_ID = 'can-regular'
FINISHED_PLAYOFF_ID = 'fin-playoff'

PLAYER_COLS = [
    '#', 'Player', 'S', 'Min', '+/-',
    '2M', '2A', '2FG%', '3M', '3A', '3FG%',
    'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB',
    'AST', 'TO', 'ST', 'BL', 'PF', 'FD', 'PTS',
    'eFG%', 'USG%', 'PM',
]


def id_table():
    return {
        HOME_ID: HOME,
        AWAY_ID: AWAY,
        VENUE_ID: VENUE,
        'p-home': 'Lin',
        'p-away': 'Chen',
    }


def status_for(game_id):
    return {
        LIVE_ID: 'IN_PROGRESS',
        UPCOMING_ID: 'SCHEDULED',
        FINISHED_ID: 'FINISHED',
        ABANDONED_ID: 'ABANDONED',
        CANCELLED_ID: 'CANCELLED',
        FINISHED_PLAYOFF_ID: 'CONFIRMED',
    }.get(game_id, 'FINISHED')


def season_df():
    rows = [
        {
            'startTimeLocal': '2026-03-01T19:00:00',
            'fixtureId': LIVE_ID,
            'fixtureType': 'REGULAR',
            'venueId': VENUE_ID,
            'status': 'IN_PROGRESS',
            'teamIdHome': HOME_ID,
            'teamScoreHome': 40,
            'teamIdAway': AWAY_ID,
            'teamScoreAway': 38,
        },
        {
            'startTimeLocal': '2026-05-30T17:00:00',
            'fixtureId': UPCOMING_ID,
            'fixtureType': 'PLAYOFF',
            'venueId': VENUE_ID,
            'status': 'SCHEDULED',
            'teamIdHome': HOME_ID,
            'teamScoreHome': None,
            'teamIdAway': AWAY_ID,
            'teamScoreAway': None,
        },
        {
            'startTimeLocal': '2026-01-15T19:00:00',
            'fixtureId': FINISHED_ID,
            'fixtureType': 'REGULAR',
            'venueId': VENUE_ID,
            'status': 'FINISHED',
            'teamIdHome': HOME_ID,
            'teamScoreHome': 88,
            'teamIdAway': AWAY_ID,
            'teamScoreAway': 79,
        },
        {
            'startTimeLocal': '2026-01-20T19:00:00',
            'fixtureId': ABANDONED_ID,
            'fixtureType': 'REGULAR',
            'venueId': VENUE_ID,
            'status': 'ABANDONED',
            'teamIdHome': HOME_ID,
            'teamScoreHome': 12,
            'teamScoreAway': 10,
            'teamIdAway': AWAY_ID,
        },
        {
            'startTimeLocal': '2026-01-10T19:00:00',
            'fixtureId': CANCELLED_ID,
            'fixtureType': 'REGULAR',
            'venueId': VENUE_ID,
            'status': 'CANCELLED',
            'teamIdHome': HOME_ID,
            'teamScoreHome': None,
            'teamIdAway': AWAY_ID,
            'teamScoreAway': None,
        },
        {
            'startTimeLocal': '2026-02-01T19:00:00',
            'fixtureId': FINISHED_PLAYOFF_ID,
            'fixtureType': 'PLAYOFF',
            'venueId': VENUE_ID,
            'status': 'CONFIRMED',
            'teamIdHome': HOME_ID,
            'teamScoreHome': 90,
            'teamIdAway': AWAY_ID,
            'teamScoreAway': 85,
        },
    ]
    return pd.DataFrame(rows)


def _split(frame):
    return frame.to_json(orient='split')


def _player_frame(name, starter, plus_minus):
    row = {col: 0 for col in PLAYER_COLS}
    row.update({
        '#': 1,
        'Player': name,
        'S': '1' if starter else '',
        'Min': '20:00',
        '+/-': plus_minus,
        'PTS': 10,
        '2M': 3,
        '2A': 5,
        '2FG%': '60%',
        '3M': 1,
        '3A': 3,
        '3FG%': '33%',
        'FTM': 2,
        'FTA': 2,
        'FT%': '100%',
        'OR': 1,
        'DR': 2,
        'REB': 3,
        'AST': 2,
        'TO': 1,
        'ST': 1,
        'BL': 0,
        'PF': 2,
        'FD': 1,
        'eFG%': '50%',
        'USG%': '20%',
        'PM': plus_minus,
    })
    return pd.DataFrame([row])


class FakeReport:
    def get_period_team_pts_df(self):
        return pd.DataFrame({'Team': [HOME, AWAY], '1Q': [20, 18], '2Q': [22, 19]})

    def get_period_team_fouls_df(self):
        return pd.DataFrame({'Team': [HOME, AWAY], '1Q': [2, 3]})

    def get_period_team_timeout_df(self):
        return pd.DataFrame({'Team': [HOME, AWAY], '1Q': [1, 0]})

    def get_team_advance_stats_df(self):
        return pd.DataFrame({'Team': [HOME, AWAY], 'Pace': [70.0, 68.0], 'PPP': [1.1, 1.0]})

    def get_team_stats_df(self):
        data = {'Team': [HOME, AWAY], 'PTS': [88, 79], 'Min': ['40:00', '40:00']}
        for index in range(18):
            data[f'S{index}'] = [index, index + 1]
        return pd.DataFrame(data)

    def get_team_key_stats_df(self):
        return pd.DataFrame({'Team': [HOME, AWAY], 'PIP': [20, 18]})

    def get_player_stats_json_dict(self):
        return {
            HOME: _split(_player_frame('Lin', True, 5)),
            AWAY: _split(_player_frame('Chen', True, -3)),
        }

    def get_player_box_score_summary_json_dict(self):
        return {}

    def get_play_by_play_df(self):
        return pd.DataFrame([
            {
                'timestamp': '2026-01-15T19:00:01',
                'sequence': 1,
                'periodId': 1,
                'clock': '9:59',
                'Team': HOME,
                'Player': 'Lin',
                'eventType': 'shot',
                'subType': '2pt',
                'success': True,
                'scores': '2-0',
            },
        ])

    def get_all_lineup_stats_json_dict(self, sizes=(5,)):
        lineup = pd.DataFrame({'Lineup': ['Lin-A'], 'PTS': [10], 'Min': ['8:21']})
        payload = {}
        for size in sizes:
            payload[str(size)] = {
                HOME: _split(lineup),
                AWAY: _split(pd.DataFrame({'Lineup': ['Chen-B'], 'PTS': [8], 'Min': ['7:10']})),
            }
        return payload

    def get_rotation_payload(self, home_team_id=None, away_team_id=None):
        return {
            'periods': [{'id': 1, 'label': '1Q', 'seconds': 120, 'start': 0.0, 'end': 120.0}],
            'buckets': [
                {'periodId': 1, 'period_label': '1Q', 'minute': 0, 'label': '1Q', 'start': 0.0, 'end': 60.0},
                {'periodId': 1, 'period_label': '1Q', 'minute': 1, 'label': '1Q', 'start': 60.0, 'end': 120.0},
            ],
            'teams': [
                {
                    'team_id': home_team_id or HOME_ID,
                    'team_name': HOME,
                    'side': 'home',
                    'players': [{'label': 'Lin', 'cells': [1, None]}],
                },
                {
                    'team_id': away_team_id or AWAY_ID,
                    'team_name': AWAY,
                    'side': 'away',
                    'players': [{'label': 'Chen', 'cells': [None, 1]}],
                },
            ],
            'margin': [{'t': 0.0, 'margin': 0}, {'t': 120.0, 'margin': 4}],
            'scoring': {'home': [1, 12], 'away': [None, 2]},
        }
