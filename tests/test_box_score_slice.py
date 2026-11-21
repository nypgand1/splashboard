import json
import unittest

import numpy as np
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
        self.assertEqual(lin['2FG%'], '.100')
        self.assertEqual(lin['USG%'], '22.5%')
        self.assertEqual(lin['S'], '○')
        team = _split_records(slices['1']['t_df'])
        braves = team[team['Team'] == 'Braves'].iloc[0]
        self.assertEqual(braves['2FG%'], '.100')
        self.assertEqual(braves['PTS'], 20)
        self.assertIn('BS', team.columns)
        self.assertNotIn('BL', team.columns)
        self.assertEqual(braves['BS'], 0)
        advance = _split_records(slices['1']['t_adv_df'])
        self.assertEqual(advance[advance['Team'] == 'Braves'].iloc[0]['eFG%'], '99.0%')

    def test_half_recomputes_rates_and_blanks_usage(self):
        slices = self._player_report().box_score_slice_json()
        players = _split_records(slices['h1']['p_df_dict']['Braves'])
        lin = players[players['Player'] == 'Lin'].iloc[0]
        self.assertEqual(lin['2M'], 2)
        self.assertEqual(lin['2A'], 6)
        self.assertEqual(lin['2FG%'], '.333')
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
        self.assertEqual(braves['2FG%'], '.333')
        self.assertEqual(braves['Min'], '18:00')
        keys = _split_records(slices['h1']['k_df'])
        self.assertEqual(keys[keys['Team'] == 'Braves'].iloc[0]['BP'], 12)
        advance = _split_records(slices['h1']['t_adv_df'])
        self.assertEqual(advance[advance['Team'] == 'Braves'].iloc[0]['eFG%'], '33.3%')
        summary = slices['h1']['p_summary_dict']['Braves']
        coaches, total = summary
        self.assertEqual(coaches['PF'], 2)
        self.assertEqual(total['PTS'], 42)
        self.assertEqual(total['2FG%'], '.333')

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
        slices = report.box_score_slice_json()
        quarter = _split_records(slices['1']['t_adv_df'])
        advanced = _split_records(slices['1']['adv_df'])
        self.assertEqual(set(quarter['Pace']), {'2.0'})
        self.assertNotIn('PPP', quarter.columns)
        home = advanced[advanced['Team'] == 'Braves'].iloc[0]
        away = advanced[advanced['Team'] == 'Visitors'].iloc[0]
        self.assertEqual(home['PPP'], '10.00')
        self.assertEqual(away['PPP'], '')
        full = report.get_team_advance_stats_df()
        self.assertEqual(set(full['Pace']), {'1.0'})
        self.assertNotIn('PPP', full.columns)

    def test_assist_ratio_and_three_rate_follow_the_period_chip(self):
        team_periods = pd.DataFrame([
            _team_row(
                'home', 1, assists=4, turnovers=2, points=10, freeThrowsAttempted=4,
                pointsTwoMade=2, pointsThreeMade=2, fieldGoalsMade=4,
                pointsTwoAttempted=4, pointsThreeAttempted=6, fieldGoalsAttempted=10,
            ),
            _team_row(
                'home', 2, assists=6, turnovers=2, points=14, freeThrowsAttempted=6,
                pointsTwoMade=3, pointsThreeMade=3, fieldGoalsMade=6,
                pointsTwoAttempted=6, pointsThreeAttempted=4, fieldGoalsAttempted=10,
            ),
            _team_row(
                'away', 1, assists=0, turnovers=0, points=0, freeThrowsAttempted=0,
                pointsTwoMade=0, pointsThreeMade=0, fieldGoalsMade=0,
                pointsTwoAttempted=0, pointsThreeAttempted=0, fieldGoalsAttempted=0,
            ),
            _team_row(
                'away', 2, assists=1, turnovers=4, points=8, freeThrowsAttempted=5,
                pointsTwoMade=2, pointsThreeMade=2, fieldGoalsMade=4,
                pointsTwoAttempted=8, pointsThreeAttempted=2, fieldGoalsAttempted=10,
            ),
        ])
        report = _report(
            team_periods=team_periods,
            player_periods=pd.DataFrame([
                {'personId': 'p1', 'entityId': 'home', 'periodId': 1, 'points': 2},
                {'personId': 'p1', 'entityId': 'home', 'periodId': 2, 'points': 2},
            ]),
        )
        slices = report.box_score_slice_json()
        pace = _split_records(slices['h1']['t_adv_df'])
        half = _split_records(slices['h1']['adv_df'])
        home = half[half['Team'] == 'Braves'].iloc[0]
        away = half[half['Team'] == 'Visitors'].iloc[0]
        self.assertEqual(home['PPP'], '0.86')
        self.assertEqual(home['AS/TO'], '2.50')
        self.assertEqual(home['AST%'], '100.0%')
        self.assertEqual(home['3P-R'], '50.0%')
        self.assertEqual(home['TS%'], '49.2%')
        self.assertEqual(away['PPP'], '0.50')
        self.assertEqual(away['AS/TO'], '0.25')
        self.assertEqual(away['AST%'], '25.0%')
        self.assertEqual(away['3P-R'], '20.0%')
        self.assertEqual(away['TS%'], '32.8%')
        self.assertNotIn('3Pr', half.columns)
        quarter = _split_records(slices['1']['adv_df'])
        q_home = quarter[quarter['Team'] == 'Braves'].iloc[0]
        q_away = quarter[quarter['Team'] == 'Visitors'].iloc[0]
        self.assertEqual(q_home['PPP'], '0.74')
        self.assertEqual(q_home['AST%'], '100.0%')
        self.assertEqual(q_home['3P-R'], '60.0%')
        self.assertEqual(q_away['PPP'], '')
        self.assertEqual(q_away['AST%'], '')
        self.assertEqual(q_away['3P-R'], '')
        self.assertNotIn('PPP', pace.columns)
        self.assertNotIn('AS/TO', pace.columns)
        self.assertNotIn('AST%', pace.columns)
        self.assertNotIn('3Pr', pace.columns)
        self.assertNotIn('3P-R', pace.columns)
        zero_to = report.get_team_advanced_df(pd.DataFrame([
            _team_row(
                'home', None, minutes='PT200M', assists=5, turnovers=0, points=0,
                pointsTwoAttempted=10, pointsThreeAttempted=0, fieldGoalsAttempted=10,
                freeThrowsAttempted=0,
            ),
        ]).drop(columns=['periodId']))
        self.assertEqual(zero_to['PPP'].iloc[0], '0.00')
        self.assertEqual(zero_to['AS/TO'].iloc[0], '')
        self.assertEqual(zero_to['AST%'].iloc[0], '')
        self.assertEqual(zero_to['3P-R'].iloc[0], '0.0%')
        self.assertEqual(zero_to['TS%'].iloc[0], '0.0%')
        zero_ast = report.get_team_advanced_df(pd.DataFrame([
            _team_row(
                'home', None, minutes='PT200M', assists=0, turnovers=2, points=4,
                fieldGoalsMade=4,
                pointsTwoAttempted=4, pointsThreeAttempted=0, fieldGoalsAttempted=4,
                freeThrowsAttempted=0,
            ),
        ]).drop(columns=['periodId']))
        self.assertEqual(zero_ast['AS/TO'].iloc[0], '0.00')
        self.assertEqual(zero_ast['AST%'].iloc[0], '0.0%')
        self.assertEqual(list(pace.columns), ['Team', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R'])
        self.assertEqual(list(half.columns), ['Team', 'PPP', 'AS/TO', 'AST%', '3P-R', 'TS%'])

    def test_key_stat_splits_follow_flags_and_the_period_chip(self):
        def shot(entity, period, event, success, sequence, **flags):
            return {
                'eventType': event,
                'entityId': entity,
                'periodId': period,
                'success': success,
                'sequence': sequence,
                'options': flags,
                'clock': 'PT10M0S',
            }

        pbp = pd.DataFrame([
            shot('home', 1, '2pt', True, 1, secondChance=True),
            shot('home', 1, '2pt', False, 2, secondChance=True),
            shot('home', 1, '3pt', True, 3, secondChance=True, fromTurnover=True),
            shot('home', 1, '2pt', True, 4, fastBreak=True),
            shot('home', 1, '3pt', False, 5, fastBreak=True),
            shot('home', 1, 'freeThrow', True, 6, secondChance=True),
            shot('home', 1, '2pt', False, 7),
            shot('home', 2, '2pt', True, 8, secondChance=True),
            shot('away', 1, '2pt', False, 9),
        ])
        team_periods = pd.DataFrame([
            _team_row(
                'home', 1,
                pointsSecondChance=5, pointsFastBreak=4, pointsFromTurnover=3,
                pointsInThePaintMade=2, pointsInThePaintAttempted=4, pointsInThePaint=4,
                pointsFromBench=6,
            ),
            _team_row(
                'home', 2,
                pointsSecondChance=2, pointsFastBreak=0, pointsFromTurnover=0,
                pointsInThePaintMade=1, pointsInThePaintAttempted=1, pointsInThePaint=2,
                pointsFromBench=1,
            ),
            _team_row('away', 1, pointsSecondChance=1, pointsFromBench=0),
            _team_row('away', 2, pointsSecondChance=0, pointsFromBench=0),
        ])
        players = pd.DataFrame([
            {'personId': 'p1', 'entityId': 'home', 'periodId': 1, 'points': 2},
            {'personId': 'p1', 'entityId': 'home', 'periodId': 2, 'points': 2},
        ])
        report = _report(
            pbp=pbp,
            team_periods=team_periods,
            player_periods=players,
            team_stats_df=pd.DataFrame([
                _team_row('home', None, pointsSecondChance=99, pointsFromBench=11),
                _team_row('away', None, pointsSecondChance=1, pointsFromBench=0),
            ]).drop(columns=['periodId']),
        )
        quarter = _split_records(report.box_score_slice_json()['1']['k_df'])
        home = quarter[quarter['Team'] == 'Braves'].iloc[0]
        away = quarter[quarter['Team'] == 'Visitors'].iloc[0]
        self.assertEqual(home['SCP2M'], 1)
        self.assertEqual(home['SCP2A'], 2)
        self.assertEqual(home['SCP3M'], 1)
        self.assertEqual(home['SCP3A'], 1)
        self.assertEqual(home['SCP'], 5)
        self.assertEqual(home['FBP2M'], 1)
        self.assertEqual(home['FBP2A'], 1)
        self.assertEqual(home['FBP3M'], 0)
        self.assertEqual(home['FBP3A'], 1)
        self.assertEqual(home['FBP'], 4)
        self.assertEqual(home['POT2M'], 0)
        self.assertEqual(home['POT2A'], 0)
        self.assertEqual(home['POT3M'], 1)
        self.assertEqual(home['POT3A'], 1)
        self.assertEqual(home['POT'], 3)
        self.assertEqual(home['PIPM'], 2)
        self.assertEqual(home['BP'], 6)
        self.assertEqual(away['SCP2M'], 0)
        self.assertEqual(away['SCP2A'], 0)
        self.assertEqual(away['SCP'], 1)
        half = _split_records(report.box_score_slice_json()['h1']['k_df'])
        home_half = half[half['Team'] == 'Braves'].iloc[0]
        self.assertEqual(home_half['SCP2M'], 2)
        self.assertEqual(home_half['SCP'], 7)
        self.assertEqual(home_half['PIPM'], 3)
        self.assertEqual(home_half['BP'], 7)
        full = report.get_team_key_stats_df()
        full_home = full[full['Team'] == 'Braves'].iloc[0]
        self.assertEqual(full_home['SCP'], 99)
        self.assertEqual(full_home['SCP2M'], 2)
        self.assertEqual(full_home['BP'], 11)
        blank = _report(pbp=pd.DataFrame(), team_periods=team_periods, player_periods=players)
        blank_q = _split_records(blank.box_score_slice_json()['1']['k_df'])
        blank_home = blank_q[blank_q['Team'] == 'Braves'].iloc[0]
        self.assertEqual(blank_home['SCP2M'], '')
        self.assertEqual(blank_home['FBP3A'], '')
        self.assertEqual(blank_home['POT3M'], '')
        self.assertEqual(blank_home['SCP'], 5)

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
        slices = report.box_score_slice_json()
        advance = _split_records(slices['1']['t_adv_df'])
        advanced = _split_records(slices['1']['adv_df'])
        self.assertEqual(set(advance['Pace']), {'0.0'})
        self.assertNotIn('PPP', advance.columns)
        self.assertEqual(set(advanced['PPP']), {''})
        self.assertEqual(set(advance['TO%']), {''})


def _home_table(report):
    return report._get_player_stats_df_dict()['Braves']


class BoxScoreMinutesTests(unittest.TestCase):
    def _players(self, rows):
        names = {'home': 'Braves', 'away': 'Visitors'}
        roster = []
        starters = []
        built = []
        for index, (person_id, name, overrides) in enumerate(rows):
            names[person_id] = name
            row = _player_game(person_id, 'home', **overrides)
            built.append(row)
            roster.append({
                'personId': person_id,
                'starter': bool(overrides.get('starter')),
                'shirtNumber': str(index + 1),
            })
            if overrides.get('starter'):
                starters.append(person_id)
        frame = pd.DataFrame(built).astype({'participated': object, 'minutes': object})
        report = _report(
            players=frame,
            id_table=names,
            roster=roster,
            starter_dict={'home': starters, 'away': []},
        )
        return _home_table(report)

    def test_only_explicit_did_not_play_is_dnp_and_missing_clocks_stay_blank(self):
        table = self._players([
            ('scratch', 'Scratch', {
                'starter': True, 'participated': False, 'minutes': None, 'points': 9, 'plusMinus': 99,
            }),
            ('npfalse', 'NpFalse', {
                'participated': np.False_, 'minutes': 'PT3M', 'points': 1,
            }),
            ('pyfalse', 'PyFalse', {
                'participated': False, 'minutes': 'PT4M', 'points': 1,
            }),
            ('blank', 'Blank', {
                'starter': False, 'participated': True, 'minutes': None,
                'points': 6, 'plusMinus': 8, 'usageRate': 15,
            }),
            ('empty', 'Empty', {
                'participated': True, 'minutes': '', 'usageRate': 9, 'plusMinus': 2, 'points': 1,
            }),
            ('nulls', 'NullText', {'participated': True, 'minutes': 'null', 'usageRate': 4}),
            ('nuls', 'NulText', {'participated': True, 'minutes': ' nul '}),
            ('nones', 'NoneText', {'participated': True, 'minutes': 'NONE'}),
            ('nano', 'Nano', {'participated': True, 'minutes': np.nan, 'usageRate': None}),
            ('zero', 'ZeroClock', {
                'participated': True, 'minutes': 'PT0S', 'usageRate': None, 'points': 0, 'plusMinus': 0,
            }),
            ('start', 'StarterBlank', {
                'starter': True, 'participated': True, 'minutes': None, 'points': 2, 'plusMinus': 1,
            }),
            ('junk', 'Garbage', {'participated': True, 'minutes': 'abc', 'usageRate': 4}),
            ('clock', 'Clock', {
                'participated': True, 'minutes': 'PT10M', 'usageRate': None, 'points': 4, 'plusMinus': 3,
            }),
        ])
        by_name = {row['Player']: row for _, row in table.iterrows()}
        for name in ('Scratch', 'NpFalse', 'PyFalse'):
            self.assertEqual(by_name[name]['Min'], 'DNP', name)
            self.assertEqual(by_name[name]['PTS'], '', name)
            self.assertEqual(by_name[name]['USG%'], '', name)
        for name in ('Blank', 'Empty', 'NullText', 'NulText', 'NoneText', 'Nano', 'StarterBlank'):
            self.assertEqual(by_name[name]['Min'], '', name)
            self.assertEqual(by_name[name]['USG%'], '', name)
        self.assertEqual(by_name['Blank']['PTS'], 6)
        self.assertEqual(by_name['Blank']['+/-'], 8)
        self.assertEqual(by_name['StarterBlank']['S'], '○')
        self.assertEqual(by_name['ZeroClock']['Min'], '0:00')
        self.assertEqual(by_name['ZeroClock']['USG%'], '0.0%')
        self.assertEqual(by_name['ZeroClock']['PTS'], '')
        self.assertEqual(by_name['Garbage']['Min'], 'abc')
        self.assertEqual(by_name['Garbage']['USG%'], '')
        self.assertEqual(by_name['Clock']['Min'], '10:00')
        self.assertEqual(by_name['Clock']['USG%'], '0.0%')
        names = list(table['Player'])
        self.assertLess(names.index('Blank'), names.index('Clock'))
        self.assertEqual(names[-3:], ['Scratch', 'NpFalse', 'PyFalse'])

    def test_missing_participated_or_minutes_column_stays_blank(self):
        gone = pd.DataFrame([
            _player_game('gone', 'home', minutes=None, points=5, plusMinus=2),
        ]).drop(columns=['participated'])
        named = _report(
            players=gone,
            id_table={'home': 'Braves', 'away': 'Visitors', 'gone': 'Gone'},
            roster=[{'personId': 'gone', 'starter': False, 'shirtNumber': '4'}],
        )
        row = _home_table(named).iloc[0]
        self.assertEqual(row['Min'], '')
        self.assertEqual(row['PTS'], 5)
        self.assertEqual(row['USG%'], '')

        no_clock = pd.DataFrame([
            _player_game('noclock', 'home', participated=True, points=3, plusMinus=1),
        ]).drop(columns=['minutes'])
        named = _report(
            players=no_clock,
            id_table={'home': 'Braves', 'away': 'Visitors', 'noclock': 'NoClock'},
            roster=[{'personId': 'noclock', 'starter': True, 'shirtNumber': '8'}],
            starter_dict={'home': ['noclock'], 'away': []},
        )
        row = _home_table(named).iloc[0]
        self.assertEqual(row['Min'], '')
        self.assertEqual(row['S'], '○')
        self.assertEqual(row['PTS'], 3)

        na_flag = pd.DataFrame([
            _player_game('naflag', 'home', minutes=None, points=1),
        ])
        na_flag['participated'] = pd.NA
        named = _report(
            players=na_flag,
            id_table={'home': 'Braves', 'away': 'Visitors', 'naflag': 'NaFlag'},
            roster=[{'personId': 'naflag', 'starter': False, 'shirtNumber': '9'}],
        )
        self.assertEqual(_home_table(named).iloc[0]['Min'], '')

    def test_missing_game_clock_stays_blank_on_slices_and_a_real_clock_is_zero(self):
        players = pd.DataFrame([
            _player_game('p1', 'home', starter=True, minutes='PT20M0S', plusMinus=4, points=12),
            _player_game('p0', 'home', minutes='PT5M0S', plusMinus=1, points=2),
            _player_game('dnp', 'home', participated=False, minutes=None, points=0),
            _player_game('gap', 'home', minutes='PT10M', plusMinus=2, points=3),
            _player_game('miss', 'home', minutes=None, plusMinus=6, points=5),
            _player_game('keep', 'home', minutes=None, plusMinus=1, points=1),
            _player_game('noch', 'home', minutes=None, plusMinus=1, points=1),
        ])
        periods = pd.DataFrame([
            {'personId': 'p1', 'entityId': 'home', 'periodId': 1, 'minutes': 'PT8M0S', 'points': 2},
            {'personId': 'p1', 'entityId': 'home', 'periodId': 2, 'minutes': 'PT6M0S', 'points': 2},
            {'personId': 'gap', 'entityId': 'home', 'periodId': 1, 'minutes': None, 'points': 1},
            {'personId': 'gap', 'entityId': 'home', 'periodId': 2, 'minutes': None, 'points': 0},
            {'personId': 'miss', 'entityId': 'home', 'periodId': 1, 'minutes': None, 'points': 4},
            {'personId': 'miss', 'entityId': 'home', 'periodId': 2, 'minutes': 'null', 'points': 0},
            {'personId': 'keep', 'entityId': 'home', 'periodId': 1, 'minutes': 'PT8M0S', 'points': 1},
        ])
        report = _report(
            players=players,
            player_periods=periods,
            team_periods=pd.DataFrame([
                _team_row('home', 1),
                _team_row('home', 2),
                _team_row('away', 1),
                _team_row('away', 2),
            ]),
            id_table={
                'home': 'Braves', 'away': 'Visitors',
                'p1': 'Lin', 'p0': 'Zero', 'dnp': 'Bench',
                'gap': 'Gap', 'miss': 'Miss', 'keep': 'Keep', 'noch': 'NoChip',
            },
            roster=[
                {'personId': person_id, 'starter': person_id == 'p1', 'shirtNumber': str(index + 1)}
                for index, person_id in enumerate(['p1', 'p0', 'dnp', 'gap', 'miss', 'keep', 'noch'])
            ],
            starter_dict={'home': ['p1'], 'away': []},
        )
        quarter = _split_records(report.box_score_slice_json()['1']['p_df_dict']['Braves'])
        by_name = {row['Player']: row for _, row in quarter.iterrows()}
        self.assertEqual(by_name['Bench']['Min'], 'DNP')
        self.assertEqual(by_name['Zero']['Min'], '0:00')
        self.assertEqual(by_name['Gap']['Min'], '0:00')
        self.assertEqual(by_name['Miss']['Min'], '')
        self.assertEqual(by_name['Miss']['PTS'], 4)
        self.assertEqual(by_name['Keep']['Min'], '8:00')
        self.assertEqual(by_name['NoChip']['Min'], '')
        half = _split_records(report.box_score_slice_json()['h1']['p_df_dict']['Braves'])
        half_by = {row['Player']: row for _, row in half.iterrows()}
        self.assertEqual(half_by['Bench']['Min'], 'DNP')
        self.assertEqual(half_by['Zero']['Min'], '0:00')
        self.assertEqual(half_by['Gap']['Min'], '0:00')
        self.assertEqual(half_by['Miss']['Min'], '')
        self.assertEqual(half_by['Miss']['USG%'], '')
        self.assertEqual(half_by['Keep']['Min'], '8:00')
        self.assertEqual(half_by['NoChip']['Min'], '')

    def test_team_coaches_summary_blanks_zeros_while_total_keeps_zeros(self):
        team = pd.DataFrame([
            _team_row(
                'home', 1,
                reboundsTeamOffensive=0,
                reboundsTeamDefensive=2,
                reboundsTeamTotal=2,
                turnoversTeam=0,
                foulsCoachTechnical=0,
                foulsBenchTechnical=0,
                foulsCoachDisqualifying=0,
                pointsTwoMade=0,
                pointsTwoAttempted=0,
                pointsThreeMade=0,
                pointsThreeAttempted=0,
                freeThrowsMade=0,
                freeThrowsAttempted=0,
                reboundsOffensive=0,
                reboundsDefensive=2,
                rebounds=2,
                assists=0,
                turnovers=0,
                steals=0,
                blocks=0,
                foulsTotal=0,
                foulsDrawn=0,
                points=0,
                pointsAgainst=10,
                plusMinus=-10,
            ),
        ])
        report = _report(team_stats_df=team, id_table={'home': 'Braves'})
        coaches, total = report.get_player_box_score_summary_json_dict()['Braves']
        self.assertEqual(coaches['#'], 'TEAM / COACHES')
        self.assertIsNone(coaches['OR'])
        self.assertEqual(coaches['DR'], 2)
        self.assertEqual(coaches['REB'], 2)
        self.assertIsNone(coaches['TO'])
        self.assertIsNone(coaches['PF'])
        self.assertEqual(total['#'], 'TOTAL')
        self.assertEqual(total['2M'], 0)
        self.assertEqual(total['AST'], 0)
        self.assertEqual(total['BS'], 0)
        self.assertEqual(total['PTS'], 0)
        self.assertEqual(total['FD'], 0)
        self.assertEqual(total['+/-'], -10)
