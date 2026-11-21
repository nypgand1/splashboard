import pandas as pd
import json
import os
import threading

from domain.clocks import (
    clock_sort_seconds as _clock_sort_seconds,
    clock_to_seconds,
    minutes_to_mmss,
    sum_clocks as _sum_clocks,
)
from domain.periods import (
    build_period_chips,
    chip_spec as _chip_spec,
    filter_periods as _filter_periods,
    known_period_ids as _known_period_ids,
    period_id_value as _period_id_value,
    period_label,
)
from domain.rates import (
    FLAG_SPLITS as _FLAG_SPLITS,
    PLAYER_COUNT_FIELDS as _PLAYER_COUNT_FIELDS,
    RATE_FIELDS as _RATE_FIELDS,
    SPLIT_LEAVES as _SPLIT_LEAVES,
    TEAM_COUNT_FIELDS as _TEAM_COUNT_FIELDS,
    as_nonneg_int as _as_nonneg_int,
    efg_pct_display,
    flag_split_counts as _flag_split_counts,
    lineup_ppp_display,
    num as _num,
    rate_text as _rate_text,
    recompute_rates as _recompute_rates,
    shot_made as _shot_made,
    shot_pct_display,
    sum_fields as _sum_fields,
    three_decimal_rate as _three_decimal_rate,
    true_shooting as _true_shooting,
)
from synergy_inbounder.names import (
    display_name,
    lineup_token,
    person_full_name,
    person_name,
    shared_short_labels,
    team_person_ids,
)
from synergy_inbounder.settings import SYNERGY_ORGANIZATION_ID
from synergy_inbounder.parser import Parser
from synergy_inbounder.possessions import annotate_possessions, possession_counts
from synergy_inbounder.pre_processing_func import process_lineup_stats
from synergy_reporter.rotation import (
    OT_SECONDS,
    build_rotation_payload,
    quarter_seconds_for_season,
    walk_lineup,
)


def _played_count(minutes, value):
    count = _as_nonneg_int(value)
    if minutes == 'DNP' or count == 0:
        return ''
    return count


def _pm_side(value):
    if isinstance(value, float) and pd.isna(value):
        return 0
    try:
        return _as_nonneg_int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def sort_lineup_table(df):
    """+/- desc, PPP desc, minutes desc, lineup name asc. Blank PPP ranks below 0.00."""
    if df is None or df.empty or '+/-' not in df.columns or 'Lineup' not in df.columns:
        return df
    res = df.copy()
    if 'PPP' in res.columns:
        res['_ppp_sort'] = pd.to_numeric(res['PPP'], errors='coerce')
    else:
        res['_ppp_sort'] = float('nan')
    if 'duration' in res.columns:
        res['_min_sort'] = pd.to_numeric(res['duration'], errors='coerce')
    elif 'Min' in res.columns:
        res['_min_sort'] = res['Min'].map(_clock_sort_seconds)
    else:
        res['_min_sort'] = float('nan')
    res.sort_values(
        by=['+/-', '_ppp_sort', '_min_sort', 'Lineup'],
        ascending=[False, False, False, True],
        na_position='last',
        kind='mergesort',
        inplace=True,
    )
    return res.drop(columns=['_ppp_sort', '_min_sort'])


def _lineup_identity(players):
    """Sorted player ids. The painted short label is not unique."""
    if not isinstance(players, (list, tuple)):
        return ''
    return '|'.join(sorted((str(pid) for pid in players), key=str))


def _blank_team(entity_id):
    row = {field: 0 for field in _TEAM_COUNT_FIELDS}
    row['entityId'] = entity_id
    row['minutes'] = 'PT0S'
    for field in _RATE_FIELDS:
        row[field] = None
    return row


def _ensure_fga(row):
    if pd.isna(row.get('fieldGoalsAttempted')):
        row['fieldGoalsAttempted'] = _num(row.get('pointsTwoAttempted')) + _num(row.get('pointsThreeAttempted'))
    return row


_MISSING_MINUTE_TEXT = frozenset({'', 'null', 'nul', 'none'})


def _minutes_missing(value):
    """True when the API sent no clock: blank, None, NaN, null, or nul."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    if isinstance(value, str):
        return value.strip().lower() in _MISSING_MINUTE_TEXT
    return False


def _did_not_play(row):
    """True only when participated is present and false.

    A missing or NA flag stays "played", matching ``row.get(..., True)``.
    ``bool`` covers NumPy false, where ``value is False`` does not.
    """
    try:
        value = row.get('participated', True)
    except AttributeError:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return not bool(value)


def _game_long_dnp(row):
    return _did_not_play(row)


def _player_min_label(row):
    if _did_not_play(row):
        return 'DNP'
    minutes = row.get('minutes')
    if _minutes_missing(minutes):
        return ''
    return minutes_to_mmss(minutes)


def _clocks_present(values):
    for value in values:
        if not _minutes_missing(value):
            return True
    return False


def _regulation_base(minutes):
    try:
        base = float(minutes)
    except (TypeError, ValueError):
        return 48.0
    if base <= 0:
        return 48.0
    return base


class PostGameReport():
    def __init__(self, game_id, organization_id=None):
        org = organization_id or SYNERGY_ORGANIZATION_ID
        (
            self.team_stats_df,
            self.team_stats_periods_df,
            self.player_stats_df,
            self.starter_dict,
            self.playbyplay_df,
            self.id_table,
            self.roster,
            self.player_stats_periods_df,
        ) = Parser.parse_game_bundle(org, game_id)
        from synergy_inbounder.runtime_cache import cached_regulation_minutes
        self.regulation_minutes = cached_regulation_minutes(org, game_id)
        self.stats_failed = bool(getattr(self.playbyplay_df, 'attrs', {}).get('stats_failed'))
        self._derive_lock = threading.RLock()
        self._lineup_frame_df = None
        self._play_by_play_view = None
        self._raw_lineup_df_dict = None
        self._lineup_json_by_size = None
        self._rotation_payload = None
        self._matchup_payload = None

    def get_period_team_pts_df(self):
        qt_pts_df = pd.DataFrame()
        qt_pts_df['Team'] = self.team_stats_periods_df.apply(lambda x: display_name(self.id_table, x.get('entityId')), axis=1)
        qt_pts_df['Period'] = self.team_stats_periods_df['periodId'].apply(period_label)
        qt_pts_df['PTS'] = self.team_stats_periods_df['points']

        totals_df = qt_pts_df.groupby('Team')['PTS'].sum().reset_index()
        totals_df['Period'] = 'Total'
        qt_pts_df = pd.concat([qt_pts_df, totals_df])

        qt_pts_df = qt_pts_df.pivot(index='Team', columns='Period', values='PTS').reset_index()
        qt_pts_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return qt_pts_df
    
    def _period_team_metric_df(self, column_name, label):
        df = pd.DataFrame()
        df['Team'] = self.team_stats_periods_df.apply(
            lambda x: display_name(self.id_table, x.get('entityId')), axis=1,
        )
        df['Period'] = self.team_stats_periods_df['periodId'].apply(period_label)
        df[label] = self.team_stats_periods_df.get(column_name, '')
        df = df.pivot(index='Team', columns='Period', values=label).reset_index()
        df.sort_values(by=['Team'], ascending=True, inplace=True)
        return df

    def get_period_team_fouls_df(self):
        return self._period_team_metric_df('foulsTotal', 'Foul')

    def get_period_team_timeout_df(self):
        return self._period_team_metric_df('timeoutsUsed', 'TOut')

    def get_team_advance_stats_df(self, source=None, period_ids=None, share_mean=True, poss_by_entity=None):
        stats = self.team_stats_df if source is None else source
        if stats is None or stats.empty:
            return pd.DataFrame(columns=['Team', 'Pace', 'eFG%', 'TO%', 'ORB%', 'FT-R'])
        if poss_by_entity is None:
            poss_series = self._possession_totals(stats, period_ids)
            poss_list = poss_series.tolist()
        else:
            poss_list = [float(poss_by_entity.get(eid, 0)) for eid in stats['entityId'].tolist()]
        base = _regulation_base(getattr(self, 'regulation_minutes', None))
        records = stats.to_dict('records')
        paces = []
        for row, poss in zip(records, poss_list):
            duration = (clock_to_seconds(row.get('minutes')) or 0.0) / 5.0
            if duration <= 0 or pd.isnull(poss):
                paces.append(None)
            else:
                paces.append(base * 60.0 * poss / duration)
        if share_mean:
            valid = [p for p in paces if p is not None and pd.notnull(p)]
            mean_pace = (sum(valid) / len(valid)) if valid else None
            paces = [mean_pace] * len(records)

        def _rate(numer, denom, digits, scale=1):
            if pd.isnull(denom) or denom == 0 or pd.isnull(numer):
                return ''
            return f"{(scale * numer / denom):.{digits}f}"

        rows_out = []
        for row, poss, pace in zip(records, poss_list, paces):
            efg_val = row.get('fieldGoalsEffectivePercentage')
            to_txt = _rate(row.get('turnovers'), poss, 1, scale=100)
            orb_for = row.get('reboundsOffensive')
            orb_ag = row.get('reboundsDefensiveAgainst')
            orb_denom = (orb_for + orb_ag) if (pd.notnull(orb_for) and pd.notnull(orb_ag)) else None
            orb_txt = _rate(orb_for, orb_denom, 1, scale=100)
            ftr_txt = _rate(row.get('freeThrowsAttempted'), row.get('fieldGoalsAttempted'), 1, scale=100)
            rows_out.append({
                'Team': display_name(self.id_table, row.get('entityId')),
                'Pace': f"{pace:0.1f}" if (pace is not None and pd.notnull(pace)) else '',
                'eFG%': f"{efg_val:0.1f}%" if pd.notnull(efg_val) else '',
                'TO%': f"{to_txt}%" if to_txt else '',
                'ORB%': f"{orb_txt}%" if orb_txt else '',
                'FT-R': f"{ftr_txt}%" if ftr_txt else '',
            })
        rows_out.sort(key=lambda r: r['Team'])
        return pd.DataFrame(rows_out)

    def get_team_advanced_df(self, source=None, period_ids=None, poss_by_entity=None):
        stats = self.team_stats_df if source is None else source
        if stats is None or stats.empty:
            return pd.DataFrame(columns=['Team', 'PPP', 'AS/TO', 'AST%', '3P-R', 'TS%'])
        if poss_by_entity is None:
            poss_list = self._possession_totals(stats, period_ids).tolist()
        else:
            poss_list = [float(poss_by_entity.get(eid, 0)) for eid in stats['entityId'].tolist()]
        rows_out = []
        for row, poss in zip(stats.to_dict('records'), poss_list):
            rows_out.append({
                'Team': display_name(self.id_table, row.get('entityId')),
                'PPP': _rate_text(row.get('points'), poss, 2),
                'AS/TO': _rate_text(row.get('assists'), row.get('turnovers'), 2),
                'AST%': _rate_text(row.get('assists'), row.get('fieldGoalsMade'), 1, scale=100, suffix='%'),
                '3P-R': _rate_text(row.get('pointsThreeAttempted'), row.get('fieldGoalsAttempted'), 1, scale=100, suffix='%'),
                'TS%': _true_shooting(row.get('points'), row.get('fieldGoalsAttempted'), row.get('freeThrowsAttempted')),
            })
        rows_out.sort(key=lambda r: r['Team'])
        return pd.DataFrame(rows_out)

    def _lock(self):
        """Re-entrant lock. Reports built without ``__init__`` get one on first use."""
        lock = self.__dict__.get('_derive_lock')
        if lock is None:
            lock = threading.RLock()
            self._derive_lock = lock
        return lock

    def _lineup_frame(self):
        """One lineup walk and one possession annotation for this report."""
        with self._lock():
            cached = self.__dict__.get('_lineup_frame_df')
            if cached is not None:
                return cached
            frame = walk_lineup(self.playbyplay_df, self.starter_dict or {})
            self._lineup_frame_df = annotate_possessions(frame)
            return self._lineup_frame_df

    def _possession_totals(self, stats, period_ids):
        pbp = getattr(self, 'playbyplay_df', None)
        if pbp is None or len(pbp) == 0:
            return (
                stats['fieldGoalsAttempted'].fillna(0)
                + 0.4 * stats['freeThrowsAttempted'].fillna(0)
                + stats['turnovers'].fillna(0)
                - stats['reboundsOffensive'].fillna(0)
            )
        counts = possession_counts(self._lineup_frame(), period_ids)
        return stats['entityId'].map(lambda entity_id: float(counts.get(entity_id, 0)))

    def box_score_period_chips(self):
        player_ids = _known_period_ids(getattr(self, 'player_stats_periods_df', None))
        if not player_ids:
            return [{'label': 'All', 'value': 'all'}]
        period_ids = player_ids | _known_period_ids(getattr(self, 'team_stats_periods_df', None))
        return build_period_chips(period_ids)

    def _slice_team_frame(self, period_ids, recompute):
        source = _filter_periods(getattr(self, 'team_stats_periods_df', None), period_ids)
        entities = []
        if self.team_stats_df is not None and len(self.team_stats_df) and 'entityId' in self.team_stats_df.columns:
            entities = list(self.team_stats_df['entityId'])
        by_entity = {}
        if len(source) and 'entityId' in source.columns:
            for s_row in source.to_dict('records'):
                by_entity.setdefault(s_row.get('entityId'), []).append(s_row)
        rows = []
        for entity_id in entities:
            matched_rows = by_entity.get(entity_id, ())
            if len(matched_rows) == 1 and not recompute:
                row = _blank_team(entity_id)
                for key, value in matched_rows[0].items():
                    if key != 'periodId':
                        row[key] = value
                row['entityId'] = entity_id
                _ensure_fga(row)
            else:
                row = _blank_team(entity_id)
                if matched_rows:
                    for field in _TEAM_COUNT_FIELDS:
                        total = 0.0
                        for m_row in matched_rows:
                            total += _num(m_row.get(field))
                        row[field] = total
                    clocks = [m_row.get('minutes') for m_row in matched_rows if 'minutes' in m_row]
                    if clocks:
                        row['minutes'] = _sum_clocks(clocks)
                row['entityId'] = entity_id
                _recompute_rates(row)
            rows.append(row)
        return pd.DataFrame(rows)

    def _slice_player_frame(self, period_ids, recompute):
        source = _filter_periods(getattr(self, 'player_stats_periods_df', None), period_ids)
        game = self.player_stats_df if self.player_stats_df is not None else pd.DataFrame()
        by_key = {}
        if len(source) and 'personId' in source.columns and 'entityId' in source.columns:
            for s_row in source.to_dict('records'):
                by_key.setdefault((s_row.get('personId'), s_row.get('entityId')), []).append(s_row)
        built = []
        for game_row in game.to_dict('records'):
            person_id = game_row.get('personId')
            entity_id = game_row.get('entityId')
            if _game_long_dnp(game_row):
                kept = dict(game_row)
                kept['_blank_usage'] = False
                built.append(kept)
                continue
            played = not _minutes_missing(game_row.get('minutes'))
            matched_rows = by_key.get((person_id, entity_id), ())
            if len(matched_rows) == 1 and not recompute:
                row = dict(matched_rows[0])
                row['personId'] = person_id
                row['entityId'] = entity_id
                row['starter'] = bool(game_row.get('starter', False))
                row['participated'] = True
                row['_blank_usage'] = False
                if _minutes_missing(row.get('minutes')) and played:
                    row['minutes'] = 'PT0S'
                built.append(row)
                continue
            row = {field: 0 for field in _PLAYER_COUNT_FIELDS}
            row.update({
                'personId': person_id,
                'entityId': entity_id,
                'starter': bool(game_row.get('starter', False)),
                'participated': True,
                'minutes': 'PT0S' if played else None,
                '_blank_usage': True,
                'usageRate': None,
            })
            for field in _RATE_FIELDS:
                row[field] = None
            if matched_rows:
                for field in _PLAYER_COUNT_FIELDS:
                    total = 0.0
                    for m_row in matched_rows:
                        total += _num(m_row.get(field))
                    row[field] = int(round(total)) if field != 'plusMinus' else round(total, 4)
                clocks = [m_row.get('minutes') for m_row in matched_rows if 'minutes' in m_row]
                if clocks:
                    if _clocks_present(clocks):
                        row['minutes'] = _sum_clocks(clocks)
                    elif played:
                        row['minutes'] = 'PT0S'
                    else:
                        row['minutes'] = None
            built.append(row)
        return pd.DataFrame(built)

    def box_score_slice_json(self):
        payload = {}
        pbp = getattr(self, 'playbyplay_df', None)
        use_pbp_poss = pbp is not None and len(pbp) > 0
        lineup_frame = self._lineup_frame() if use_pbp_poss else None
        for chip in self.box_score_period_chips():
            value = chip['value']
            if value == 'all':
                continue
            period_ids, recompute = _chip_spec(value)
            team = self._slice_team_frame(period_ids, recompute)
            players = self._slice_player_frame(period_ids, recompute)
            player_frames = self._get_player_stats_df_dict(players, blank_usage=recompute)
            poss = possession_counts(lineup_frame, period_ids) if use_pbp_poss else None
            payload[value] = {
                't_adv_df': self.get_team_advance_stats_df(team, period_ids, poss_by_entity=poss).to_json(date_format='iso', orient='split'),
                'adv_df': self.get_team_advanced_df(team, period_ids, poss_by_entity=poss).to_json(date_format='iso', orient='split'),
                't_df': self.get_team_stats_df(team).to_json(date_format='iso', orient='split'),
                'k_df': self.get_team_key_stats_df(team, period_ids).to_json(date_format='iso', orient='split'),
                'p_df_dict': {
                    name: frame.to_json(date_format='iso', orient='split')
                    for name, frame in player_frames.items()
                },
                'p_summary_dict': self.get_player_box_score_summary_json_dict(team),
            }
        return payload

    def get_team_stats_df(self, source=None):
        stats = self.team_stats_df if source is None else source
        if stats is None or stats.empty:
            return pd.DataFrame(columns=[
                'Team', 'Min', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
                'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS',
            ])
        has_fd = 'foulsDrawn' in stats.columns
        rows_out = []
        for x in stats.to_dict('records'):
            rows_out.append({
                'Team': display_name(self.id_table, x.get('entityId')),
                'Min': minutes_to_mmss(x.get('minutes')),
                '2M': _as_nonneg_int(x.get('pointsTwoMade')),
                '2A': _as_nonneg_int(x.get('pointsTwoAttempted')),
                '2FG%': shot_pct_display(x.get('pointsTwoMade'), x.get('pointsTwoAttempted'), x.get('pointsTwoPercentage')),
                '3M': _as_nonneg_int(x.get('pointsThreeMade')),
                '3A': _as_nonneg_int(x.get('pointsThreeAttempted')),
                '3FG%': shot_pct_display(x.get('pointsThreeMade'), x.get('pointsThreeAttempted'), x.get('pointsThreePercentage')),
                'FTM': _as_nonneg_int(x.get('freeThrowsMade')),
                'FTA': _as_nonneg_int(x.get('freeThrowsAttempted')),
                'FT%': shot_pct_display(x.get('freeThrowsMade'), x.get('freeThrowsAttempted'), x.get('freeThrowsPercentage')),
                'OR': _as_nonneg_int(x.get('reboundsOffensive')),
                'DR': _as_nonneg_int(x.get('reboundsDefensive')),
                'REB': _as_nonneg_int(x.get('rebounds')),
                'AST': _as_nonneg_int(x.get('assists')),
                'TO': _as_nonneg_int(x.get('turnovers')),
                'ST': _as_nonneg_int(x.get('steals')),
                'BS': _as_nonneg_int(x.get('blocks')),
                'PF': _as_nonneg_int(x.get('foulsTotal')),
                'FD': _as_nonneg_int(x.get('foulsDrawn')) if has_fd else 0,
                'PTS': _as_nonneg_int(x.get('points')),
            })
        rows_out.sort(key=lambda r: r['Team'])
        return pd.DataFrame(rows_out)
            
    def get_team_key_stats_df(self, source=None, period_ids=None):
        stats = self.team_stats_df if source is None else source
        k_df = pd.DataFrame()
        k_df['Team'] = stats.apply(lambda x: display_name(self.id_table, x.get('entityId')), axis=1)
        entity_ids = list(stats['entityId'])
        splits = _flag_split_counts(getattr(self, 'playbyplay_df', None), entity_ids, period_ids)

        def _ints(column):
            if column not in stats.columns:
                return [0] * len(stats)
            values = []
            for value in stats[column].tolist():
                if value is None:
                    values.append(0)
                    continue
                try:
                    if pd.isna(value):
                        values.append(0)
                        continue
                except TypeError:
                    pass
                try:
                    values.append(int(value))
                except (TypeError, ValueError):
                    values.append(0)
            return values

        k_df['PIPM'] = _ints('pointsInThePaintMade')
        k_df['PIPA'] = _ints('pointsInThePaintAttempted')
        k_df['PIP'] = _ints('pointsInThePaint')
        for prefix, _flag, points_col in _FLAG_SPLITS:
            for leaf in _SPLIT_LEAVES:
                column = prefix + leaf
                k_df[column] = [splits[entity][column] for entity in entity_ids]
            k_df[prefix] = _ints(points_col)
        k_df['BP'] = _ints('pointsFromBench')
        k_df.sort_values(by=['Team'], ascending=True, inplace=True)
        return k_df
    
    def _get_player_stats_df_dict(self, source=None, blank_usage=False):
        from synergy_reporter.report_components import sort_player_rows_for_report

        roster_shirt_dict = {r['personId']: r['shirtNumber'] for r in (self.roster or []) if r.get('shirtNumber') is not None}
        roster_starter_dict = {r['personId']: bool(r.get('starter')) for r in (self.roster or [])}

        players = self.player_stats_df if source is None else source
        by_team = {}
        if players is not None and not players.empty and 'entityId' in players.columns:
            for row in players.to_dict('records'):
                by_team.setdefault(row.get('entityId'), []).append(row)

        p_df_dict = dict()
        for t in self.team_stats_df['entityId'].to_list():
            team_name = display_name(self.id_table, t)
            team_rows = by_team.get(t, ())
            if not team_rows:
                p_df_dict[team_name] = pd.DataFrame(columns=[
                    '#', 'Player', 'S', 'Min', '+/-',
                    '2M', '2A', '2FG%', '3M', '3A', '3FG%',
                    'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB',
                    'AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS',
                    'eFG%', 'USG%', 'PM',
                ])
                continue
            starters_for_team = set(self.starter_dict.get(t, []))
            rows_out = []
            for x in team_rows:
                pid = x.get('personId')
                shirt = roster_shirt_dict.get(pid)
                min_label = _player_min_label(x)
                is_dnp = min_label == 'DNP'
                pm_val = x.get('plusMinus')
                if is_dnp or pd.isna(pm_val):
                    plus_minus = ''
                else:
                    plus_minus = int(round(float(pm_val)))

                two_m_raw = x.get('pointsTwoMade')
                two_a_raw = x.get('pointsTwoAttempted')
                three_m_raw = x.get('pointsThreeMade')
                three_a_raw = x.get('pointsThreeAttempted')
                ft_m_raw = x.get('freeThrowsMade')
                ft_a_raw = x.get('freeThrowsAttempted')

                if is_dnp:
                    two_fg = ''
                    three_fg = ''
                    ft_fg = ''
                    efg_str = ''
                    usg_str = ''
                    pm_str = ''
                else:
                    two_fg = shot_pct_display(two_m_raw, two_a_raw, x.get('pointsTwoPercentage'))
                    three_fg = shot_pct_display(three_m_raw, three_a_raw, x.get('pointsThreePercentage'))
                    ft_fg = shot_pct_display(ft_m_raw, ft_a_raw, x.get('freeThrowsPercentage'))
                    efg_str = efg_pct_display(
                        two_m_raw, two_a_raw,
                        three_m_raw, three_a_raw,
                        x.get('fieldGoalsEffectivePercentage'),
                    )
                    if blank_usage or x.get('_blank_usage') == True or clock_to_seconds(x.get('minutes')) is None:  # noqa: E712
                        usg_str = ''
                    else:
                        usg_val = x.get('usageRate')
                        usg_str = f"{usg_val:0.1f}%" if pd.notnull(usg_val) else '0.0%'
                    pm_str = f"{_pm_side(x.get('plus'))}-{_pm_side(x.get('minus'))}"

                rows_out.append({
                    '#': str(shirt) if shirt is not None else '',
                    'Player': person_name(self.id_table, pid),
                    '_playerFull': person_full_name(self.id_table, pid),
                    'S': '○' if (roster_starter_dict.get(pid) or pid in starters_for_team) else '',
                    'Min': min_label,
                    '+/-': plus_minus,
                    '2M': _played_count(min_label, two_m_raw),
                    '2A': _played_count(min_label, two_a_raw),
                    '2FG%': two_fg,
                    '3M': _played_count(min_label, three_m_raw),
                    '3A': _played_count(min_label, three_a_raw),
                    '3FG%': three_fg,
                    'FTM': _played_count(min_label, ft_m_raw),
                    'FTA': _played_count(min_label, ft_a_raw),
                    'FT%': ft_fg,
                    'OR': _played_count(min_label, x.get('reboundsOffensive')),
                    'DR': _played_count(min_label, x.get('reboundsDefensive')),
                    'REB': _played_count(min_label, x.get('rebounds')),
                    'AST': _played_count(min_label, x.get('assists')),
                    'TO': _played_count(min_label, x.get('turnovers')),
                    'ST': _played_count(min_label, x.get('steals')),
                    'BS': _played_count(min_label, x.get('blocks')),
                    'PF': _played_count(min_label, x.get('foulsTotal')),
                    'FD': _played_count(min_label, x.get('foulsDrawn')),
                    'PTS': _played_count(min_label, x.get('points')),
                    'eFG%': efg_str,
                    'USG%': usg_str,
                    'PM': pm_str,
                })
            p_df_t = pd.DataFrame(sort_player_rows_for_report(rows_out))
            p_df_dict[team_name] = p_df_t
        return p_df_dict

    def _raw_lineup_stats(self):
        with self._lock():
            cached = self.__dict__.get('_raw_lineup_df_dict')
            if cached is None:
                self._raw_lineup_df_dict = process_lineup_stats(self._lineup_frame())
            return self._raw_lineup_df_dict

    def _get_lineup_stats_df_dict(self, lineup_size=5):
        lineup_df_dict = self._raw_lineup_stats()
        roster_shirt_dict = {r['personId']: r['shirtNumber'] for r in (self.roster or []) if r.get('shirtNumber') is not None}

        def _shirt(pid):
            if pid in roster_shirt_dict:
                return roster_shirt_dict[pid]
            return roster_shirt_dict.get(str(pid))

        def _player_sort_key(pid):
            bib_str = _shirt(pid)
            if bib_str is not None:
                try:
                    return (0, int(bib_str))
                except Exception as exc:
                    from synergy_inbounder.logs import data as log_data
                    log_data.debug('lineup bib parse failed: %s', exc)
            return (1, person_name(self.id_table, pid))

        u_df_dict = dict()
        for t in lineup_df_dict:
            team_name = self.id_table.get(t, t)
            raw_lineup_df = lineup_df_dict[t]
            on_court = raw_lineup_df[t].tolist() if t in raw_lineup_df.columns else []
            shared = shared_short_labels(
                self.id_table,
                team_person_ids(self.roster, t, on_court),
            )

            def decode_lineup(lineup, shared=shared):
                if not isinstance(lineup, (list, tuple)):
                    return ''
                sorted_players = sorted(lineup, key=_player_sort_key)
                return '-'.join(
                    lineup_token(self.id_table, pid, _shirt(pid), shared)
                    for pid in sorted_players
                )

            team_lineup_df = raw_lineup_df.copy()

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
            team_lineup_df['_lineup_key'] = team_lineup_df[t].apply(_lineup_identity)

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
            team_lineup_df['PPP'] = team_lineup_df.apply(
                lambda x: lineup_ppp_display(x['PTS'], x['POSS']), axis=1,
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
            team_lineup_df['BS'] = team_lineup_df['BLK'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['PF'] = team_lineup_df['PF'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v))
            team_lineup_df['FD'] = team_lineup_df['FD'].apply(lambda v: '' if pd.isna(v) or int(v) == 0 else int(v)) if 'FD' in team_lineup_df.columns else ''
            for column in ('PIP', 'SCP', 'FBP', 'POT'):
                team_lineup_df[column] = team_lineup_df[column].apply(
                    lambda v: '' if pd.isna(v) or int(v) == 0 else int(v)
                )

            team_lineup_df['PTS'] = team_lineup_df['PTS'].apply(
                lambda v: '' if pd.isna(v) or int(v) == 0 else int(v)
            )

            def _blank_count(value):
                if pd.isna(value) or int(value) == 0:
                    return ''
                return int(value)

            team_lineup_df['Opp_2FG%'] = team_lineup_df.apply(
                lambda x: shot_pct_display(x['Opp_2M'], x['Opp_2A']), axis=1,
            )
            team_lineup_df['Opp_3FG%'] = team_lineup_df.apply(
                lambda x: shot_pct_display(x['Opp_3M'], x['Opp_3A']), axis=1,
            )
            team_lineup_df['Opp_FT%'] = team_lineup_df.apply(
                lambda x: shot_pct_display(x['Opp_1M'], x['Opp_1A']), axis=1,
            )
            team_lineup_df['Opp_PPP'] = team_lineup_df.apply(
                lambda x: lineup_ppp_display(x['Opp_PTS'], x['Opp_POSS']), axis=1,
            )
            for source, dest in (
                ('Opp_2M', 'Opp_2M'),
                ('Opp_2A', 'Opp_2A'),
                ('Opp_3M', 'Opp_3M'),
                ('Opp_3A', 'Opp_3A'),
                ('Opp_1M', 'Opp_FTM'),
                ('Opp_1A', 'Opp_FTA'),
                ('Opp_OR', 'Opp_OR'),
                ('Opp_DR', 'Opp_DR'),
                ('Opp_REB', 'Opp_REB'),
                ('Opp_AST', 'Opp_AST'),
                ('Opp_TOV', 'Opp_TO'),
                ('Opp_STL', 'Opp_ST'),
                ('Opp_BLK', 'Opp_BS'),
                ('Opp_PF', 'Opp_PF'),
                ('Opp_FD', 'Opp_FD'),
                ('Opp_PTS', 'Opp_PTS'),
                ('Opp_PIP', 'Opp_PIP'),
                ('Opp_SCP', 'Opp_SCP'),
                ('Opp_FBP', 'Opp_FBP'),
                ('Opp_POT', 'Opp_POT'),
            ):
                team_lineup_df[dest] = team_lineup_df[source].apply(_blank_count)

            team_lineup_df = sort_lineup_table(team_lineup_df)
            u_df_dict[team_name] = team_lineup_df[[
                'Lineup', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
                'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS',
                'PF', 'FD', 'PTS', 'PIP', 'SCP', 'FBP', 'POT', 'PPP',
                'Opp_2M', 'Opp_2A', 'Opp_2FG%', 'Opp_3M', 'Opp_3A', 'Opp_3FG%',
                'Opp_FTM', 'Opp_FTA', 'Opp_FT%', 'Opp_OR', 'Opp_DR', 'Opp_REB',
                'Opp_AST', 'Opp_TO', 'Opp_ST', 'Opp_BS', 'Opp_PF', 'Opp_FD',
                'Opp_PTS', 'Opp_PIP', 'Opp_SCP', 'Opp_FBP', 'Opp_POT', 'Opp_PPP',
                '_lineup_key',
            ]].copy()

        return u_df_dict

    def get_player_box_score_summary_json_dict(self, source=None):
        summary_dict = dict()
        team_df = self.team_stats_df if source is None else source
        for t in team_df['entityId'].to_list():
            team_name = display_name(self.id_table, t)
            team_rows = team_df[team_df['entityId'] == t]
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
                except Exception as exc:
                    from synergy_inbounder.logs import data as log_data
                    log_data.debug('box score int parse failed: %s', exc)
                    return None

            def _pos_int(k):
                val = _clean_int(k)
                return val if (val is not None and val > 0) else None

            or_team = _pos_int('reboundsTeamOffensive')
            dr_team = _pos_int('reboundsTeamDefensive')
            reb_team = _pos_int('reboundsTeamTotal')
            to_team = _pos_int('turnoversTeam')
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
                'BS': None,
                'PF': pf_team,
                'FD': None,
                'PTS': None,
                'eFG%': None,
                'USG%': None,
                'PM': None,
            }

            two_m = _clean_int('pointsTwoMade') if _clean_int('pointsTwoMade') is not None else 0
            two_a = _clean_int('pointsTwoAttempted') if _clean_int('pointsTwoAttempted') is not None else 0
            two_pct = shot_pct_display(two_m, two_a, _val('pointsTwoPercentage', None)) or None

            three_m = _clean_int('pointsThreeMade') if _clean_int('pointsThreeMade') is not None else 0
            three_a = _clean_int('pointsThreeAttempted') if _clean_int('pointsThreeAttempted') is not None else 0
            three_pct = shot_pct_display(three_m, three_a, _val('pointsThreePercentage', None)) or None

            ft_m = _clean_int('freeThrowsMade') if _clean_int('freeThrowsMade') is not None else 0
            ft_a = _clean_int('freeThrowsAttempted') if _clean_int('freeThrowsAttempted') is not None else 0
            ft_pct = shot_pct_display(ft_m, ft_a, _val('freeThrowsPercentage', None)) or None

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
                'BS': _clean_int('blocks') if _clean_int('blocks') is not None else 0,
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
        with self._lock():
            cached = self.__dict__.get('_lineup_json_by_size')
            if cached is None:
                cached = {}
                self._lineup_json_by_size = cached
            missing = [size for size in sizes if str(size) not in cached]
            for size in missing:
                cached[str(size)] = self.get_lineup_stats_json_dict(lineup_size=size)
            return {str(size): cached[str(size)] for size in sizes}
   
    def get_rotation_payload(self, home_team_id=None, away_team_id=None, live=False, season_id=None):
        cache_key = (str(home_team_id), str(away_team_id), bool(live), str(season_id or ''))
        with self._lock():
            cached = self.__dict__.get('_rotation_payload')
            if cached is not None and self.__dict__.get('_rotation_key') == cache_key:
                return cached
            df = self._lineup_frame().copy()
            self._rotation_payload = build_rotation_payload(
                df,
                starter_dict=self.starter_dict,
                id_table=self.id_table,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                roster=self.roster,
                live=bool(live),
                quarter_seconds=quarter_seconds_for_season(season_id),
                ot_seconds=OT_SECONDS,
            )
            self._rotation_key = cache_key
            return self._rotation_payload

    def get_matchup_payload(self, home_team_id=None, away_team_id=None):
        cache_key = (str(home_team_id), str(away_team_id))
        with self._lock():
            cached = self.__dict__.get('_matchup_payload')
            if cached is not None and self.__dict__.get('_matchup_key') == cache_key:
                return cached
            from synergy_reporter.matchups import build_matchup_payload
            df = self._lineup_frame().copy()
            shirts = {}
            for person in self.roster or []:
                if not isinstance(person, dict) or person.get('personId') is None:
                    continue
                if person.get('shirtNumber') is None:
                    continue
                shirts[person['personId']] = person['shirtNumber']
                shirts[str(person['personId'])] = person['shirtNumber']

            def _on_court(team_id):
                if team_id is None:
                    return []
                column = team_id if team_id in df.columns else str(team_id)
                if column not in df.columns:
                    return []
                return df[column].tolist()

            team_people = {}
            for team_id in (home_team_id, away_team_id):
                if team_id is None:
                    continue
                team_people[str(team_id)] = team_person_ids(
                    self.roster, team_id, _on_court(team_id),
                )
            self._matchup_payload = build_matchup_payload(
                df,
                home_id=home_team_id,
                away_id=away_team_id,
                id_table=self.id_table or {},
                shirts=shirts,
                team_people=team_people,
            )
            self._matchup_key = cache_key
            return self._matchup_payload

    def get_play_by_play_df(self):
        with self._lock():
            cached = self.__dict__.get('_play_by_play_view')
            if cached is not None:
                return cached
            return self._build_play_by_play_view()

    def _build_play_by_play_view(self):
        df = self._lineup_frame().copy()
        team_id_list = df['entityId'].dropna().unique()
        
        df['Team'] = df.apply(lambda x: self.id_table.get(x['entityId'], x['entityId']), axis=1)
        df['Player'] = df['personId'].apply(lambda pid: person_name(self.id_table, pid))
        team_name_list = df['Team'].dropna().unique()
        
        def decode_scores(scores):
            if not isinstance(scores, str):
                return scores
            d = json.loads(scores)
            return str({self.id_table.get(t ,t):  d[t] for t in d})[1:-1].replace('\'', '')
        df['scores'] = df['scores'].apply(lambda x: decode_scores(x))
    
        shirts = {}
        for person in self.roster or []:
            if isinstance(person, dict) and person.get('personId') is not None:
                shirts[person['personId']] = person.get('shirtNumber')
                shirts[str(person['personId'])] = person.get('shirtNumber')

        def shirt_of(pid):
            if pid is None or (isinstance(pid, float) and pd.isna(pid)):
                return None
            if pid in shirts:
                return shirts[pid]
            return shirts.get(str(pid))

        def decode_lineup(lineup, shared):
            if not isinstance(lineup, (list, tuple)):
                return ''
            names = [
                lineup_token(self.id_table, pid, shirt_of(pid), shared)
                for pid in lineup
            ]
            return str(sorted(names))[1:-1].replace('\'', '')

        for t in team_id_list:
            lists = df[t].tolist() if t in df.columns else []
            shared = shared_short_labels(
                self.id_table, team_person_ids(self.roster, t, lists),
            )
            df[self.id_table.get(t, f"name_{t}")] = df[t].apply(
                lambda lineup, shared=shared: decode_lineup(lineup, shared)
            )

        if 'personId' in df.columns:
            df['shirtNumber'] = df['personId'].map(shirt_of)
        if 'x' not in df.columns:
            df['x'] = float('nan')
        if 'y' not in df.columns:
            df['y'] = float('nan')

        col_list = ['timestamp', 'sequence', 'periodId', 'clock', 'entityId', 'Team', 'personId', 'Player', 'eventType', 'subType', 'success', 'scores', 'options', 'x', 'y', 'shirtNumber']
        col_list.extend(team_name_list)
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
