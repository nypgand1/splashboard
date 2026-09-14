import pandas as pd
import json
import os

from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.pre_processing_func import process_lineup_pbp, process_lineup_stats
from synergy_reporter.rotation import build_rotation_payload, clock_to_seconds, period_label


def _as_nonneg_int(value):
    if value is None or value == '':
        return 0
    if isinstance(value, str) and not str(value).strip():
        return 0
    if isinstance(value, float) and pd.isna(value):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def shot_pct_display(made, attempted, pct=None):
    """Blank when A==0; 0.0% when A>0 and M==0. M itself stays blank at 0."""
    attempted_n = _as_nonneg_int(attempted)
    if attempted_n <= 0:
        return ''
    if _as_nonneg_int(made) == 0:
        return '0.0%'
    if pct is not None and pd.notnull(pct):
        return f"{float(pct):0.1f}%"
    return f"{100.0 * _as_nonneg_int(made) / attempted_n:0.1f}%"


def efg_pct_display(made2, attempted2, made3, attempted3, efg_val=None):
    """Blank when FGA==0; 0.0% when FGA>0 and (2M+3M)==0."""
    fga = _as_nonneg_int(attempted2) + _as_nonneg_int(attempted3)
    if fga <= 0:
        return ''
    made = _as_nonneg_int(made2) + _as_nonneg_int(made3)
    if made == 0:
        return '0.0%'
    if efg_val is not None and pd.notnull(efg_val):
        return f"{float(efg_val):0.1f}%"
    made3_n = _as_nonneg_int(made3)
    return f"{100.0 * (made + 0.5 * made3_n) / fga:0.1f}%"


def minutes_to_mmss(value):
    """Convert Synergy PT duration (or seconds) to M:SS (e.g. 45:59, 8:21, 0:06)."""
    seconds = clock_to_seconds(value)
    if seconds is None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ''
        text = str(value).strip()
        return text
    total = int(round(float(seconds)))
    if total < 0:
        total = 0
    return '{:d}:{:02d}'.format(total // 60, total % 60)


class PostGameReport():
    def __init__(self, game_id):
        (
            self.team_stats_df,
            self.team_stats_periods_df,
            self.player_stats_df,
            self.starter_dict,
            self.playbyplay_df,
            self.id_table,
            self.roster,
        ) = Parser.parse_game_bundle(SYNERGY_ORGANIZATION_ID, game_id)
        self._play_by_play_view = None
        self._raw_lineup_df_dict = None
        self._lineup_json_by_size = None
        self._rotation_payload = None

    def get_period_team_pts_df(self):
        qt_pts_df = pd.DataFrame()
        qt_pts_df['Team'] = self.team_stats_periods_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        qt_pts_df['Period'] = self.team_stats_periods_df['periodId'].apply(period_label)
        qt_pts_df['PTS'] = self.team_stats_periods_df['points']

        totals_df = qt_pts_df.groupby('Team')['PTS'].sum().reset_index()
        totals_df['Period'] = 'Total'
        qt_pts_df = pd.concat([qt_pts_df, totals_df])

        qt_pts_df = qt_pts_df.pivot(index='Team', columns='Period', values='PTS').reset_index()
        qt_pts_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_pts_df
    
    def get_period_team_fouls_df(self):
        qt_foul_df = pd.DataFrame()
        qt_foul_df['Team'] = self.team_stats_periods_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        qt_foul_df['Period'] = self.team_stats_periods_df['periodId'].apply(period_label)
        qt_foul_df['Foul'] = self.team_stats_periods_df.get('foulsTotal', '')
        qt_foul_df = qt_foul_df.pivot(index='Team', columns='Period', values='Foul').reset_index()
        qt_foul_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_foul_df
        
    def get_period_team_timeout_df(self):
        qt_tout_df = pd.DataFrame()
        qt_tout_df['Team'] = self.team_stats_periods_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        qt_tout_df['Period'] = self.team_stats_periods_df['periodId'].apply(period_label)
        qt_tout_df['TOut'] = self.team_stats_periods_df.get('timeoutsUsed', '')
        qt_tout_df = qt_tout_df.pivot(index='Team', columns='Period', values='TOut').reset_index()
        qt_tout_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_tout_df

    def get_team_advance_stats_df(self):
        t_adv_df = pd.DataFrame()
        t_adv_df['Team'] = self.team_stats_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        self.team_stats_df['poss'] = self.team_stats_df['fieldGoalsAttempted'] + 0.4 * self.team_stats_df['freeThrowsAttempted'] + self.team_stats_df['turnovers'] - self.team_stats_df['reboundsOffensive']
        self.team_stats_df['duration'] = pd.to_timedelta(self.team_stats_df['minutes'].str.replace('PT', '', regex=False) \
                                                                                    .str.replace('M', ' min ', regex=False) \
                                                                                    .str.replace('S', 'sec', regex=False)).dt.total_seconds()/5
        #TODO: assume a 48 mins game
        t_adv_df['Pace'] = self.team_stats_df.apply(lambda x: 48*60*x['poss']/x['duration'] if pd.notnull(x['duration']) else None, axis=1)
        t_adv_df['Pace'] = t_adv_df['Pace'].mean()
        t_adv_df['Pace'] = t_adv_df['Pace'].apply(lambda x: f"{x:0.1f}")

        t_adv_df['PPP'] = self.team_stats_df.apply(lambda x: f"{(x['points']/x['poss']):0.2f}" if pd.notnull(x['poss']) else '', axis=1)
        t_adv_df['eFG%'] = self.team_stats_df.apply(lambda x: f"{x['fieldGoalsEffectivePercentage']:0.1f}%" if pd.notnull(x['fieldGoalsEffectivePercentage']) else '', axis=1)
        t_adv_df['TOV%'] = self.team_stats_df.apply(lambda x: f"{(100*x['turnovers']/x['poss']):0.1f}%" if pd.notnull(x['poss']) else '', axis=1)
        t_adv_df['ORB%'] = self.team_stats_df.apply(lambda x: f"{(100*x['reboundsOffensive']/(x['reboundsOffensive']+x['reboundsDefensiveAgainst'])):0.1f}%" if pd.notnull(x['reboundsOffensive']+x['reboundsDefensiveAgainst']) else '', axis=1)
        t_adv_df['FT-R'] = self.team_stats_df.apply(lambda x: f"{(100*x['freeThrowsAttempted']/x['fieldGoalsAttempted']):0.1f}%" if pd.notnull(x['fieldGoalsAttempted']) else '', axis=1)
        t_adv_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return t_adv_df

    def get_team_stats_df(self):
        t_df = pd.DataFrame()
        t_df['Team'] = self.team_stats_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        t_df['Min'] = self.team_stats_df['minutes'].map(minutes_to_mmss)
        t_df['2M'] = self.team_stats_df['pointsTwoMade'].fillna(0).astype(int)
        t_df['2A'] = self.team_stats_df['pointsTwoAttempted'].fillna(0).astype(int)
        t_df['2FG%'] = self.team_stats_df.apply(lambda x: f"{x['pointsTwoPercentage']:0.1f}%" if x['pointsTwoAttempted'] != 0 else '', axis=1)
        t_df['3M'] = self.team_stats_df['pointsThreeMade'].fillna(0).astype(int)
        t_df['3A'] = self.team_stats_df['pointsThreeAttempted'].fillna(0).astype(int)
        t_df['3FG%'] = self.team_stats_df.apply(lambda x: f"{x['pointsThreePercentage']:0.1f}%" if x['pointsThreeAttempted'] != 0 else '', axis=1)
        t_df['FTM'] = self.team_stats_df['freeThrowsMade'].fillna(0).astype(int)
        t_df['FTA'] = self.team_stats_df['freeThrowsAttempted'].fillna(0).astype(int)
        t_df['FT%'] = self.team_stats_df.apply(lambda x: f"{x['freeThrowsPercentage']:0.1f}%" if x['freeThrowsAttempted'] != 0 else '', axis=1)
        t_df['OR'] = self.team_stats_df['reboundsOffensive'].fillna(0).astype(int)
        t_df['DR'] = self.team_stats_df['reboundsDefensive'].fillna(0).astype(int)
        t_df['REB'] = self.team_stats_df['rebounds'].fillna(0).astype(int)
        t_df['AST'] = self.team_stats_df['assists'].fillna(0).astype(int)
        t_df['TO'] = self.team_stats_df['turnovers'].fillna(0).astype(int)
        t_df['ST'] = self.team_stats_df['steals'].fillna(0).astype(int)
        t_df['BL'] = self.team_stats_df['blocks'].fillna(0).astype(int)
        t_df['PF'] = self.team_stats_df['foulsTotal'].fillna(0).astype(int)
        t_df['FD'] = self.team_stats_df['foulsDrawn'].fillna(0).astype(int) if 'foulsDrawn' in self.team_stats_df.columns else 0
        t_df['PTS'] = self.team_stats_df['points'].fillna(0).astype(int)
        t_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return t_df
            
    def get_team_key_stats_df(self):
        k_df = pd.DataFrame()
        k_df['Team'] = self.team_stats_df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        k_df['PIPM'] = self.team_stats_df['pointsInThePaintMade'].fillna(0).astype(int)
        k_df['PIPA'] = self.team_stats_df['pointsInThePaintAttempted'].fillna(0).astype(int)
        k_df['PIP'] = self.team_stats_df['pointsInThePaint'].fillna(0).astype(int)
        k_df['SCPM'] = self.team_stats_df['pointsSecondChanceMade'].fillna(0).astype(int)
        k_df['SCPA'] = self.team_stats_df['pointsSecondChanceAttempted'].fillna(0).astype(int)
        k_df['SCP'] = self.team_stats_df['pointsSecondChance'].fillna(0).astype(int)
        k_df['FBP'] = self.team_stats_df['pointsFastBreak'].fillna(0).astype(int)
        k_df['POT'] = self.team_stats_df['pointsFromTurnover'].fillna(0).astype(int)
        k_df['BP'] = self.team_stats_df['pointsFromBench'].fillna(0).astype(int)
        k_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return k_df
    
    def _get_player_stats_df_dict(self):
        roster_shirt_dict = {r['personId']: r['shirtNumber'] for r in (self.roster or []) if r.get('shirtNumber') is not None}
        roster_starter_dict = {r['personId']: bool(r.get('starter')) for r in (self.roster or [])}

        p_df_dict = dict()
        for t in self.team_stats_df['entityId'].to_list():
            team_name = self.id_table.get(t, t)
            p_df = self.player_stats_df[self.player_stats_df['entityId']==t]
            starters_for_team = set(self.starter_dict.get(t, []))

            p_df_t = pd.DataFrame()
            p_df_t['#'] = p_df['personId'].apply(lambda pid: str(roster_shirt_dict.get(pid, '')) if roster_shirt_dict.get(pid) is not None else '')
            p_df_t['Player'] = p_df.apply(lambda x: self.id_table.get(x['personId'], x['personId']), axis=1)
            p_df_t['S'] = p_df['personId'].apply(lambda pid: '○' if (roster_starter_dict.get(pid) or pid in starters_for_team) else '')

            is_participated = p_df['participated'].fillna(True) if 'participated' in p_df.columns else pd.Series(True, index=p_df.index)
            # If minutes is None/empty and not participated -> DNP
            p_df_t['Min'] = p_df.apply(lambda x: 'DNP' if (not x.get('participated', True) or (pd.isna(x.get('minutes')) and not x.get('starter', False))) else minutes_to_mmss(x.get('minutes')), axis=1)
            p_df_t['+/-'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or pd.isna(x.get('plusMinus')) else int(round(float(x.get('plusMinus')))), axis=1)

            p_df_t['2M'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('pointsTwoMade', 0) == 0 else int(x.get('pointsTwoMade', 0)), axis=1)
            p_df_t['2A'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('pointsTwoAttempted', 0) == 0 else int(x.get('pointsTwoAttempted', 0)), axis=1)
            p_df_t['2FG%'] = p_df.apply(
                lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' else shot_pct_display(
                    x.get('pointsTwoMade'), x.get('pointsTwoAttempted'), x.get('pointsTwoPercentage'),
                ),
                axis=1,
            )

            p_df_t['3M'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('pointsThreeMade', 0) == 0 else int(x.get('pointsThreeMade', 0)), axis=1)
            p_df_t['3A'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('pointsThreeAttempted', 0) == 0 else int(x.get('pointsThreeAttempted', 0)), axis=1)
            p_df_t['3FG%'] = p_df.apply(
                lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' else shot_pct_display(
                    x.get('pointsThreeMade'), x.get('pointsThreeAttempted'), x.get('pointsThreePercentage'),
                ),
                axis=1,
            )

            p_df_t['FTM'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('freeThrowsMade', 0) == 0 else int(x.get('freeThrowsMade', 0)), axis=1)
            p_df_t['FTA'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('freeThrowsAttempted', 0) == 0 else int(x.get('freeThrowsAttempted', 0)), axis=1)
            p_df_t['FT%'] = p_df.apply(
                lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' else shot_pct_display(
                    x.get('freeThrowsMade'), x.get('freeThrowsAttempted'), x.get('freeThrowsPercentage'),
                ),
                axis=1,
            )

            p_df_t['OR'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('reboundsOffensive', 0) == 0 else int(x.get('reboundsOffensive', 0)), axis=1)
            p_df_t['DR'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('reboundsDefensive', 0) == 0 else int(x.get('reboundsDefensive', 0)), axis=1)
            p_df_t['REB'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('rebounds', 0) == 0 else int(x.get('rebounds', 0)), axis=1)
            p_df_t['AST'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('assists', 0) == 0 else int(x.get('assists', 0)), axis=1)
            p_df_t['TO'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('turnovers', 0) == 0 else int(x.get('turnovers', 0)), axis=1)
            p_df_t['ST'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('steals', 0) == 0 else int(x.get('steals', 0)), axis=1)
            p_df_t['BL'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('blocks', 0) == 0 else int(x.get('blocks', 0)), axis=1)
            p_df_t['PF'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('foulsTotal', 0) == 0 else int(x.get('foulsTotal', 0)), axis=1)
            p_df_t['FD'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('foulsDrawn', 0) == 0 else int(x.get('foulsDrawn', 0)), axis=1)
            p_df_t['PTS'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' or x.get('points', 0) == 0 else int(x.get('points', 0)), axis=1)

            # eFG%: blank if FGA==0 or DNP, 0.0% if FGA>0 and 0 made
            def _calc_efg(x):
                if p_df_t.loc[x.name, 'Min'] == 'DNP':
                    return ''
                return efg_pct_display(
                    x.get('pointsTwoMade'), x.get('pointsTwoAttempted'),
                    x.get('pointsThreeMade'), x.get('pointsThreeAttempted'),
                    x.get('fieldGoalsEffectivePercentage'),
                )
            p_df_t['eFG%'] = p_df.apply(_calc_efg, axis=1)

            # USG%: blank if DNP or not played, 0.0% if played but 0 usage
            def _calc_usg(x):
                if p_df_t.loc[x.name, 'Min'] == 'DNP':
                    return ''
                if not x.get('minutes'):
                    return ''
                usg_val = x.get('usageRate')
                return f"{usg_val:0.1f}%" if pd.notnull(usg_val) else '0.0%'
            p_df_t['USG%'] = p_df.apply(_calc_usg, axis=1)

            p_df_t['PM'] = p_df.apply(lambda x: '' if p_df_t.loc[x.name, 'Min'] == 'DNP' else f"{int(round(float(x.get('plus', 0) or 0)))}-{int(round(float(x.get('minus', 0) or 0)))}", axis=1)
    
            from synergy_reporter.report_components import sort_player_stats_for_report
            p_df_t = sort_player_stats_for_report(p_df_t)
            p_df_dict[team_name] = p_df_t
        return p_df_dict

    def _raw_lineup_stats(self):
        if self._raw_lineup_df_dict is None:
            self._raw_lineup_df_dict = process_lineup_stats(self.get_play_by_play_df())
        return self._raw_lineup_df_dict

    def _get_lineup_stats_df_dict(self, lineup_size=5):
        lineup_df_dict = self._raw_lineup_stats()
        roster_shirt_dict = {r['personId']: r['shirtNumber'] for r in (self.roster or []) if r.get('shirtNumber') is not None}

        def _player_sort_key(pid):
            bib_str = roster_shirt_dict.get(pid)
            if bib_str is not None:
                try:
                    return (0, int(bib_str))
                except Exception:
                    pass
            return (1, str(self.id_table.get(pid, pid)))

        def decode_lineup(lineup):
            sorted_players = sorted(lineup, key=_player_sort_key)
            return "-".join([str(self.id_table.get(p, p)) for p in sorted_players])

        u_df_dict = dict()
        for t in lineup_df_dict:
            team_name = self.id_table.get(t, t)
            team_lineup_df = lineup_df_dict[t].copy()

            if lineup_size and lineup_size < 5:
                import itertools
                expanded_rows = []
                for _, row in team_lineup_df.iterrows():
                    players = row[t]
                    if not isinstance(players, (list, tuple)):
                        continue
                    for combo in itertools.combinations(players, lineup_size):
                        new_row = row.copy()
                        new_row[t] = list(combo)
                        expanded_rows.append(new_row)
                    if expanded_rows:
                        team_lineup_df = pd.DataFrame(expanded_rows)
                        team_lineup_df['_combo_key'] = team_lineup_df[t].apply(lambda x: tuple(sorted(x)))
                        grouped = team_lineup_df.groupby('_combo_key', as_index=False).sum(numeric_only=True, min_count=1)
                        grouped[t] = grouped['_combo_key'].apply(list)
                        team_lineup_df = grouped.drop(columns=['_combo_key'])
            elif lineup_size and lineup_size > 5:
                team_lineup_df = team_lineup_df[team_lineup_df[t].apply(lambda x: len(x) == lineup_size)]

            team_lineup_df['Lineup'] = team_lineup_df[t].apply(lambda x: decode_lineup(x))

            team_lineup_df['Min'] = team_lineup_df.apply(lambda x: f"{int(x['duration']//60)}:{x['duration']%60:02.0f}", axis=1)
            team_lineup_df['+/-'] = team_lineup_df['PTS']-team_lineup_df['Opp_PTS']

            # Zero values blanking. Compute % from raw M/A before blanking zeros.
            team_lineup_df['2FG%'] = team_lineup_df.apply(
                lambda x: shot_pct_display(x['2M'], x['2A']), axis=1,
            )
            team_lineup_df['3FG%'] = team_lineup_df.apply(
                lambda x: shot_pct_display(x['3M'], x['3A']), axis=1,
            )
            team_lineup_df['FT%'] = team_lineup_df.apply(
                lambda x: shot_pct_display(x['1M'], x['1A']), axis=1,
            )
            team_lineup_df['eFG%'] = team_lineup_df.apply(
                lambda x: efg_pct_display(x['2M'], x['2A'], x['3M'], x['3A']), axis=1,
            )
            team_lineup_df['2M'] = team_lineup_df['2M'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['2A'] = team_lineup_df['2A'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))

            team_lineup_df['3M'] = team_lineup_df['3M'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['3A'] = team_lineup_df['3A'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))

            team_lineup_df['FTM'] = team_lineup_df['1M'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['FTA'] = team_lineup_df['1A'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))

            team_lineup_df['OR'] = team_lineup_df['OR'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['DR'] = team_lineup_df['DR'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['REB'] = team_lineup_df['REB'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['AST'] = team_lineup_df['AST'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['TO'] = team_lineup_df['TOV'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['ST'] = team_lineup_df['STL'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['BL'] = team_lineup_df['BLK'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['PF'] = team_lineup_df['PF'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['FD'] = team_lineup_df['FD'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v)) if 'FD' in team_lineup_df.columns else ''

            # PTS
            team_lineup_df['PTS_RAW'] = team_lineup_df['PTS'].fillna(0).astype(int)
            team_lineup_df['PTS'] = team_lineup_df['PTS_RAW'].apply(lambda v: '' if v == 0 else v)

            team_lineup_df['PM'] = team_lineup_df.apply(lambda x: f"{x['PTS_RAW']}-{int(x.get('Opp_PTS', 0))}", axis=1)

            team_lineup_df = team_lineup_df[[
                'Lineup', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
                'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BL',
                'PF', 'FD', 'PTS', 'eFG%', 'PM'
            ]].copy()
            team_lineup_df.sort_values(by=['+/-', 'Lineup'], ascending=[False, True], inplace=True)
            u_df_dict[team_name] = team_lineup_df

        return u_df_dict

    def get_player_box_score_summary_json_dict(self):
        summary_dict = dict()
        for t in self.team_stats_df['entityId'].to_list():
            team_name = self.id_table.get(t, t)
            team_rows = self.team_stats_df[self.team_stats_df['entityId'] == t]
            if team_rows.empty:
                continue
            row = team_rows.iloc[0]

            def _val(k, default=0):
                v = row.get(k)
                return default if (pd.isna(v) or v is None) else v

            def _clean_int(k):
                v = row.get(k)
                if v is None or v == '' or (isinstance(v, float) and pd.isna(v)):
                    return None
                try:
                    return int(v)
                except Exception:
                    return None

            or_team = _clean_int('reboundsTeamOffensive')
            dr_team = _clean_int('reboundsTeamDefensive')
            reb_team = _clean_int('reboundsTeamTotal')
            to_team = _clean_int('turnoversTeam')
            coach_fouls = int(_val('foulsCoachTechnical', 0)) + int(_val('foulsBenchTechnical', 0)) + int(_val('foulsCoachDisqualifying', 0))
            pf_team = coach_fouls if coach_fouls > 0 else None

            team_coaches_row = {
                '#': 'TEAM / COACHES',
                'Player': '',
                'S': '',
                'Min': None,
                '+/-': None,
                '2M': None,
                '2A': None,
                '2FG%': None,
                '3M': None,
                '3A': None,
                '3FG%': None,
                'FTM': None,
                'FTA': None,
                'FT%': None,
                'OR': or_team,
                'DR': dr_team,
                'REB': reb_team,
                'AST': None,
                'TO': to_team,
                'ST': None,
                'BL': None,
                'PF': pf_team,
                'FD': None,
                'PTS': None,
                'eFG%': None,
                'USG%': None,
                'PM': None,
            }

            two_m = _clean_int('pointsTwoMade') if _clean_int('pointsTwoMade') is not None else 0
            two_a = _clean_int('pointsTwoAttempted') if _clean_int('pointsTwoAttempted') is not None else 0
            two_pct = f"{float(_val('pointsTwoPercentage', 0)):0.1f}%" if two_a > 0 else None

            three_m = _clean_int('pointsThreeMade') if _clean_int('pointsThreeMade') is not None else 0
            three_a = _clean_int('pointsThreeAttempted') if _clean_int('pointsThreeAttempted') is not None else 0
            three_pct = f"{float(_val('pointsThreePercentage', 0)):0.1f}%" if three_a > 0 else None

            ft_m = _clean_int('freeThrowsMade') if _clean_int('freeThrowsMade') is not None else 0
            ft_a = _clean_int('freeThrowsAttempted') if _clean_int('freeThrowsAttempted') is not None else 0
            ft_pct = f"{float(_val('freeThrowsPercentage', 0)):0.1f}%" if ft_a > 0 else None

            efg_val = _val('fieldGoalsEffectivePercentage', None)
            efg_str = f"{float(efg_val):0.1f}%" if pd.notnull(efg_val) else None

            pts_for = _clean_int('points')
            pts_against = _clean_int('pointsAgainst')
            pm_str = f"{pts_for}-{pts_against}" if (pts_for is not None and pts_against is not None) else None

            min_val = row.get('minutes')
            min_str = minutes_to_mmss(min_val) if pd.notnull(min_val) else None

            total_row = {
                '#': 'TOTAL',
                'Player': '',
                'S': '',
                'Min': min_str,
                '+/-': _clean_int('plusMinus'),
                '2M': two_m,
                '2A': two_a,
                '2FG%': two_pct,
                '3M': three_m,
                '3A': three_a,
                '3FG%': three_pct,
                'FTM': ft_m,
                'FTA': ft_a,
                'FT%': ft_pct,
                'OR': _clean_int('reboundsOffensive') if _clean_int('reboundsOffensive') is not None else 0,
                'DR': _clean_int('reboundsDefensive') if _clean_int('reboundsDefensive') is not None else 0,
                'REB': _clean_int('rebounds') if _clean_int('rebounds') is not None else 0,
                'AST': _clean_int('assists') if _clean_int('assists') is not None else 0,
                'TO': _clean_int('turnovers') if _clean_int('turnovers') is not None else 0,
                'ST': _clean_int('steals') if _clean_int('steals') is not None else 0,
                'BL': _clean_int('blocks') if _clean_int('blocks') is not None else 0,
                'PF': _clean_int('foulsTotal') if _clean_int('foulsTotal') is not None else 0,
                'FD': _clean_int('foulsDrawn'),
                'PTS': _clean_int('points') if _clean_int('points') is not None else 0,
                'eFG%': efg_str,
                'USG%': None,
                'PM': pm_str,
            }

            summary_dict[team_name] = [team_coaches_row, total_row]
        return summary_dict

    def get_player_stats_json_dict(self):
        player_stats_df_dict = self._get_player_stats_df_dict()
        return {team_name: df.to_json(date_format='iso', orient='split') for team_name, df in player_stats_df_dict.items()}

    def get_lineup_stats_json_dict(self, lineup_size=5):
        lineup_stats_df_dict = self._get_lineup_stats_df_dict(lineup_size=lineup_size)
        return {team_name: df.to_json(date_format='iso', orient='split') for team_name, df in lineup_stats_df_dict.items()}

    def get_all_lineup_stats_json_dict(self, sizes=(5, 4, 3, 2)):
        if self._lineup_json_by_size is None:
            self._lineup_json_by_size = {}
        missing = [size for size in sizes if str(size) not in self._lineup_json_by_size]
        for size in missing:
            self._lineup_json_by_size[str(size)] = self.get_lineup_stats_json_dict(lineup_size=size)
        return {str(size): self._lineup_json_by_size[str(size)] for size in sizes}
   
    def get_rotation_payload(self, home_team_id=None, away_team_id=None):
        cache_key = (str(home_team_id), str(away_team_id))
        if self._rotation_payload is not None and getattr(self, '_rotation_key', None) == cache_key:
            return self._rotation_payload

        df = self.playbyplay_df.copy()
        process_lineup_pbp(df, self.starter_dict)
        self._rotation_payload = build_rotation_payload(
            df,
            starter_dict=self.starter_dict,
            id_table=self.id_table,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            roster=self.roster,
        )
        self._rotation_key = cache_key
        return self._rotation_payload

    def get_play_by_play_df(self):
        if self._play_by_play_view is not None:
            return self._play_by_play_view

        df = self.playbyplay_df.copy()
        process_lineup_pbp(df, self.starter_dict)
        team_id_list = df['entityId'].dropna().unique()
        
        df['Team'] = df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        df['Player'] = df.apply(lambda x: self.id_table.get(x['personId'], x['personId']), axis=1)
        team_name_list = df['Team'].dropna().unique()
        
        def decode_scores(scores):
            if not isinstance(scores, str):
                return scores
            d = json.loads(scores)
            return str({self.id_table.get(t ,t):  d[t] for t in d})[1:-1].replace('\'', '')
        df['scores'] = df['scores'].apply(lambda x: decode_scores(x))
    
        def decode_lineup(lineup):
            return str(sorted([self.id_table.get(p ,p) for p in lineup]))[1:-1].replace('\'', '')
        for t in team_id_list:
            df[self.id_table.get(t, f"name_{t}")] = df[t].apply(lambda x: decode_lineup(x))
        
        col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'entityId', 'Team', 'personId', 'Player', 'eventType', 'subType', 'success', 'scores', 'options'] 
        col_list.extend(team_name_list)
        col_list.extend(team_id_list)
        if 'ERROR' in df:
            col_list.append('ERROR')
    
        self._play_by_play_view = df[col_list]
        return self._play_by_play_view
 
    def save_all_reports_to_csv(self):
        if not os.path.exists('csv_output'):
            os.makedirs('csv_output')
        self.get_period_team_pts_df().to_csv('csv_output/period_team_pts.csv', index=False, encoding='utf-8')
        self.get_period_team_fouls_df().to_csv('csv_output/period_team_fouls.csv', index=False, encoding='utf-8')
        self.get_period_team_timeout_df().to_csv('csv_output/period_team_timeout.csv', index=False, encoding='utf-8')
        self.get_team_advance_stats_df().to_csv('csv_output/team_advance_stats.csv', index=False, encoding='utf-8')
        self.get_team_stats_df().to_csv('csv_output/team_stats.csv', index=False, encoding='utf-8')
        self.get_team_key_stats_df().to_csv('csv_output/team_key_stats.csv', index=False, encoding='utf-8')

        player_stats_dfs = self._get_player_stats_df_dict()
        for team_name, df in player_stats_dfs.items():
            df.sort_values(by=['+/-', 'PTS', 'AST', 'REB'], ascending=False).to_csv(f'csv_output/player_stats_{team_name}.csv', index=False, encoding='utf-8')

        lineup_stats_dfs = self._get_lineup_stats_df_dict()
        for team_name, df in lineup_stats_dfs.items():
            df.to_csv(f'csv_output/lineup_stats_{team_name}.csv', index=False, encoding='utf-8')
 
def main():
    game_id = input('Game Id? ')
    r = PostGameReport(str(game_id))
    r.save_all_reports_to_csv()

if __name__ == '__main__':
    main()
