import json
import unittest

import pandas as pd

from synergy_reporter.post_game_report import PostGameReport


def _team_row(entity_id, period_id, **overrides):
    row = {
        'entityId': entity_id,
        'periodId': period_id,
        'minutes': 'PT60M',
        'points': 0,
        'pointsAgainst': 0,
        'plusMinus': 0,
        'pointsTwoMade': 0,
        'pointsTwoAttempted': 0,
        'pointsTwoPercentage': None,
        'pointsThreeMade': 0,
        'pointsThreeAttempted': 0,
        'pointsThreePercentage': None,
        'freeThrowsMade': 0,
        'freeThrowsAttempted': 0,
        'freeThrowsPercentage': None,
        'reboundsOffensive': 0,
        'reboundsDefensive': 0,
        'rebounds': 0,
        'reboundsDefensiveAgainst': 0,
        'assists': 0,
        'turnovers': 0,
        'steals': 0,
        'blocks': 0,
        'foulsTotal': 0,
        'foulsDrawn': 0,
        'pointsInThePaintMade': 0,
        'pointsInThePaintAttempted': 0,
        'pointsInThePaint': 0,
        'pointsSecondChanceMade': 0,
        'pointsSecondChanceAttempted': 0,
        'pointsSecondChance': 0,
        'pointsFastBreak': 0,
        'pointsFromTurnover': 0,
        'pointsFromBench': 0,
        'fieldGoalsAttempted': 0,
        'fieldGoalsEffectivePercentage': None,
        'reboundsTeamOffensive': 0,
        'reboundsTeamDefensive': 0,
        'reboundsTeamTotal': 0,
        'turnoversTeam': 0,
        'foulsCoachTechnical': 0,
        'foulsBenchTechnical': 0,
        'foulsCoachDisqualifying': 0,
    }
    row.update(overrides)
    return row


def _player_game(person_id, entity_id, **overrides):
    row = {
        'personId': person_id,
        'entityId': entity_id,
        'starter': False,
        'participated': True,
        'minutes': 'PT20M0S',
        'plusMinus': 0,
        'points': 0,
    }
    row.update(overrides)
    return row


def _report(**kwargs):
    report = PostGameReport.__new__(PostGameReport)
    report.team_stats_df = kwargs.get('team_stats_df', pd.DataFrame([
        {'entityId': 'home', 'minutes': 'PT240M', 'points': 90},
        {'entityId': 'away', 'minutes': 'PT240M', 'points': 80},
    ]))
    report.team_stats_periods_df = kwargs.get('team_periods', pd.DataFrame())
    report.player_stats_df = kwargs.get('players', pd.DataFrame([
        _player_game('p1', 'home', starter=True),
    ]))
    report.player_stats_periods_df = kwargs.get('player_periods', pd.DataFrame())
    report.playbyplay_df = kwargs.get('pbp', pd.DataFrame())
    report.starter_dict = kwargs.get('starter_dict', {'home': ['p1'], 'away': []})
    report.id_table = kwargs.get('id_table', {
        'home': 'Braves',
        'away': 'Visitors',
        'p1': 'Lin',
        'p0': 'Zero',
        'dnp': 'Bench',
    })
    report.roster = kwargs.get('roster', [
        {'personId': 'p1', 'starter': True, 'shirtNumber': '7'},
        {'personId': 'p0', 'starter': False, 'shirtNumber': '12'},
        {'personId': 'dnp', 'starter': False, 'shirtNumber': '20'},
    ])
    return report


def _split_records(payload):
    parsed = json.loads(payload)
    return pd.DataFrame(parsed['data'], columns=parsed['columns'])


class BoxScoreChipTests(unittest.TestCase):
    def test_menu_is_only_all_when_player_periods_are_empty(self):
        report = _report(team_periods=pd.DataFrame([
            _team_row('home', 1),
            _team_row('home', 2),
            _team_row('away', 1),
            _team_row('away', 2),
        ]))
        self.assertEqual(
            report.box_score_period_chips(),
            [{'label': 'All', 'value': 'all'}],
        )
        self.assertEqual(report.box_score_slice_json(), {})

    def test_half_chip_requires_both_quarters_and_ot_follows(self):
        periods = [1, 2, 3, 11]
        player_rows = [
            {'personId': 'p1', 'entityId': 'home', 'periodId': period, 'points': 1}
            for period in periods
        ]
        team_rows = [_team_row('home', period) for period in periods]
        team_rows += [_team_row('away', period) for period in periods]
        report = _report(
            player_periods=pd.DataFrame(player_rows),
            team_periods=pd.DataFrame(team_rows),
        )
        self.assertEqual(
            [chip['label'] for chip in report.box_score_period_chips()],
            ['All', '1Q', '2Q', '1H', '3Q', 'OT'],
        )
        self.assertEqual(
            [chip['value'] for chip in report.box_score_period_chips()],
            ['all', '1', '2', 'h1', '3', '11'],
        )


class BoxScoreSliceTests(unittest.TestCase):
    def _player_report(self):
        players = pd.DataFrame([
            _player_game('p1', 'home', starter=True, plusMinus=4, points=12, usageRate=18),
            _player_game('p0', 'home', starter=False, minutes='PT5M0S', plusMinus=1, points=2),
            _player_game('dnp', 'home', starter=False, participated=False, minutes=None, points=0),
        ])
        player_periods = pd.DataFrame([
            {
                'personId': 'p1',
                'entityId': 'home',
                'periodId': 1,
                'minutes': 'PT8M0S',
                'starter': False,
                'participated': True,
                'plusMinus': 3,
                'pointsTwoMade': 1,
                'pointsTwoAttempted': 4,
                'pointsTwoPercentage': 10.0,
                'pointsThreeMade': 0,
                'pointsThreeAttempted': 0,
                'freeThrowsMade': 0,
                'freeThrowsAttempted': 0,
                'points': 2,
                'usageRate': 22.5,
                'plus': 6,
                'minus': 3,
                'reboundsOffensive': 0,
                'reboundsDefensive': 1,
                'rebounds': 1,
                'assists': 0,
                'turnovers': 0,
                'steals': 0,
                'blocks': 0,
                'foulsTotal': 1,
                'foulsDrawn': 0,
                'fieldGoalsEffectivePercentage': 10.0,
            },
            {
                'personId': 'p1',
                'entityId': 'home',
                'periodId': 2,
                'minutes': 'PT6M0S',
                'starter': False,
                'participated': True,
                'plusMinus': 1,
                'pointsTwoMade': 1,
                'pointsTwoAttempted': 2,
                'pointsTwoPercentage': 80.0,
                'pointsThreeMade': 0,
                'pointsThreeAttempted': 0,
                'freeThrowsMade': 0,
                'freeThrowsAttempted': 0,
                'points': 2,
                'usageRate': 11.0,
                'plus': 4,
                'minus': 3,
                'reboundsOffensive': 0,
                'reboundsDefensive': 0,
                'rebounds': 0,
                'assists': 1,
                'turnovers': 0,
                'steals': 0,
                'blocks': 0,
                'foulsTotal': 0,
                'foulsDrawn': 0,
                'fieldGoalsEffectivePercentage': 80.0,
            },
        ])
        team_periods = pd.DataFrame([
            _team_row(
                'home', 1,
                minutes='PT10M',
                points=20,
                pointsTwoMade=1,
                pointsTwoAttempted=4,
                pointsTwoPercentage=10.0,
                fieldGoalsAttempted=4,
                fieldGoalsEffectivePercentage=99.0,
                pointsFromBench=5,
                foulsCoachTechnical=1,
            ),
            _team_row(
                'home', 2,
                minutes='PT8M',
                points=22,
                pointsTwoMade=1,
                pointsTwoAttempted=2,
                pointsTwoPercentage=80.0,
                fieldGoalsAttempted=2,
                fieldGoalsEffectivePercentage=1.0,
                pointsFromBench=7,
                foulsBenchTechnical=1,
            ),
            _team_row('away', 1, minutes='PT10M', points=18),
            _team_row('away', 2, minutes='PT8M', points=16),
        ])
        return _report(
            players=players,
            player_periods=player_periods,
            team_periods=team_periods,
            team_stats_df=pd.DataFrame([
                {'entityId': 'home', 'minutes': 'PT240M', 'points': 90},
                {'entityId': 'away', 'minutes': 'PT240M', 'points': 80},
            ]),
        )

    def test_quarter_keeps_api_percentages_and_usage(self):
        slices = self._player_report().box_score_slice_json()
        players = _split_records(slices['1']['p_df_dict']['Braves'])
        lin = players[players['Player'] == 'Lin'].iloc[0]
        self.assertEqual(lin['Min'], '8:00')
        self.assertEqual(lin['2FG%'], '10.0%')
        self.assertEqual(lin['USG%'], '22.5%')
        self.assertEqual(lin['S'], '○')
        team = _split_records(slices['1']['t_df'])
        braves = team[team['Team'] == 'Braves'].iloc[0]
        self.assertEqual(braves['2FG%'], '10.0%')
        self.assertEqual(braves['PTS'], 20)
        advance = _split_records(slices['1']['t_adv_df'])
        self.assertEqual(advance[advance['Team'] == 'Braves'].iloc[0]['eFG%'], '99.0%')

    def test_half_recomputes_rates_and_blanks_usage(self):
        slices = self._player_report().box_score_slice_json()
        players = _split_records(slices['h1']['p_df_dict']['Braves'])
        lin = players[players['Player'] == 'Lin'].iloc[0]
        self.assertEqual(lin['2M'], 2)
        self.assertEqual(lin['2A'], 6)
        self.assertEqual(lin['2FG%'], '33.3%')
        self.assertEqual(lin['USG%'], '')
        self.assertEqual(lin['Min'], '14:00')
        names = list(players['Player'])
        self.assertEqual(names[-1], 'Bench')
        self.assertEqual(players[players['Player'] == 'Bench'].iloc[0]['Min'], 'DNP')
        zero = players[players['Player'] == 'Zero'].iloc[0]
        self.assertEqual(zero['Min'], '0:00')
        self.assertEqual(zero['USG%'], '')
        self.assertLess(names.index('Lin'), names.index('Zero'))
        team = _split_records(slices['h1']['t_df'])
        braves = team[team['Team'] == 'Braves'].iloc[0]
        self.assertEqual(braves['PTS'], 42)
        self.assertEqual(braves['2FG%'], '33.3%')
        self.assertEqual(braves['Min'], '18:00')
        keys = _split_records(slices['h1']['k_df'])
        self.assertEqual(keys[keys['Team'] == 'Braves'].iloc[0]['BP'], 12)
        advance = _split_records(slices['h1']['t_adv_df'])
        self.assertEqual(advance[advance['Team'] == 'Braves'].iloc[0]['eFG%'], '33.3%')
        summary = slices['h1']['p_summary_dict']['Braves']
        coaches, total = summary
        self.assertEqual(coaches['PF'], 2)
        self.assertEqual(total['PTS'], 42)
        self.assertEqual(total['2FG%'], '33.3%')

    def test_slice_pace_uses_that_periods_possessions(self):
        pbp = pd.DataFrame([
            {
                'eventType': '2pt', 'subType': 'layup', 'entityId': 'home',
                'periodId': 1, 'clock': 'PT10M0S', 'success': 1, 'sequence': 1,
            },
            {
                'eventType': '2pt', 'subType': 'layup', 'entityId': 'away',
                'periodId': 2, 'clock': 'PT10M0S', 'success': 1, 'sequence': 2,
            },
        ])
        team_periods = pd.DataFrame([
            _team_row('home', 1, minutes='PT60M', points=10, fieldGoalsAttempted=10),
            _team_row('away', 1, minutes='PT60M', points=8, fieldGoalsAttempted=10),
            _team_row('home', 2, minutes='PT60M', points=12, fieldGoalsAttempted=10),
            _team_row('away', 2, minutes='PT60M', points=14, fieldGoalsAttempted=10),
        ])
        report = _report(
            pbp=pbp,
            team_periods=team_periods,
            player_periods=pd.DataFrame([
                {'personId': 'p1', 'entityId': 'home', 'periodId': 1, 'points': 2},
                {'personId': 'p1', 'entityId': 'home', 'periodId': 2, 'points': 2},
            ]),
            team_stats_df=pd.DataFrame([
                _team_row('home', None, minutes='PT240M', points=22, fieldGoalsAttempted=20),
                _team_row('away', None, minutes='PT240M', points=22, fieldGoalsAttempted=20),
            ]).drop(columns=['periodId']),
        )
        quarter = _split_records(report.box_score_slice_json()['1']['t_adv_df'])
        self.assertEqual(set(quarter['Pace']), {'2.0'})
        home = quarter[quarter['Team'] == 'Braves'].iloc[0]
        away = quarter[quarter['Team'] == 'Visitors'].iloc[0]
        self.assertEqual(home['PPP'], '10.00')
        self.assertEqual(away['PPP'], '')
        full = report.get_team_advance_stats_df()
        self.assertEqual(set(full['Pace']), {'1.0'})

    def test_missing_play_by_play_uses_the_box_estimate(self):
        team_periods = pd.DataFrame([
            _team_row('home', 1, minutes='PT60M', fieldGoalsAttempted=10, points=20),
            _team_row(
                'away', 1, minutes='PT60M', fieldGoalsAttempted=20, points=16,
            ),
        ])
        report = _report(
            pbp=pd.DataFrame(),
            team_periods=team_periods,
            player_periods=pd.DataFrame([
                {'personId': 'p1', 'entityId': 'home', 'periodId': 1, 'points': 2},
            ]),
        )
        advance = _split_records(report.box_score_slice_json()['1']['t_adv_df'])
        self.assertEqual(set(advance['Pace']), {'60.0'})

    def test_play_by_play_with_no_ends_counts_zero(self):
        pbp = pd.DataFrame([
            {
                'eventType': 'foul', 'subType': 'personal', 'entityId': 'home',
                'periodId': 1, 'clock': 'PT10M0S', 'success': None, 'sequence': 1,
            },
        ])
        team_periods = pd.DataFrame([
            _team_row('home', 1, minutes='PT60M', fieldGoalsAttempted=10, points=10, turnovers=4),
            _team_row('away', 1, minutes='PT60M', fieldGoalsAttempted=10, points=8, turnovers=4),
        ])
        report = _report(
            pbp=pbp,
            team_periods=team_periods,
            player_periods=pd.DataFrame([
                {'personId': 'p1', 'entityId': 'home', 'periodId': 1, 'points': 2},
            ]),
        )
        advance = _split_records(report.box_score_slice_json()['1']['t_adv_df'])
        self.assertEqual(set(advance['Pace']), {'0.0'})
        self.assertEqual(set(advance['PPP']), {''})
        self.assertEqual(set(advance['TOV%']), {''})
