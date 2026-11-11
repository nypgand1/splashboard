# -*- coding: utf-8 -*-
from dash import html
import dash_mantine_components as dmc
import pandas as pd

from synergy_inbounder.logs import data as log_data
from synergy_reporter.column_winners import winning_indexes
from synergy_reporter.team_order import team_stripe
from ui.components import team_name_lines
from ui.tokens import OPP_BEST_STYLE, WINNER_STYLE

KEY_STAT_GROUPS = (
    ('Points in the Paint', (('PIPM', 'M'), ('PIPA', 'A'), ('PIP', 'PT'))),
    ('Second Chance Points', (
        ('SCP2M', '2M'), ('SCP2A', '2A'), ('SCP3M', '3M'), ('SCP3A', '3A'), ('SCP', 'PT'),
    )),
    ('Fast Break Points', (
        ('FBP2M', '2M'), ('FBP2A', '2A'), ('FBP3M', '3M'), ('FBP3A', '3A'), ('FBP', 'PT'),
    )),
    ('Points off Turnovers', (
        ('POT2M', '2M'), ('POT2A', '2A'), ('POT3M', '3M'), ('POT3A', '3A'), ('POT', 'PT'),
    )),
)
KEY_STAT_LEAVES = tuple(
    column for _name, pairs in KEY_STAT_GROUPS for column, _label in pairs
) + ('BP',)
SHOT_GROUPS = (
    ('2PT', ('2M', '2A', '2FG%'), ('M', 'A', '%')),
    ('3PT', ('3M', '3A', '3FG%'), ('M', 'A', '%')),
    ('FT', ('FTM', 'FTA', 'FT%'), ('M', 'A', '%')),
    ('REB', ('OR', 'DR', 'REB'), ('O', 'D', 'T')),
)
COUNT_TAILS = ('AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS')
EXTRA_TAILS = ('eFG%', 'USG%', 'PM')
TAIL_LABEL = {'AST': 'AS', 'PTS': 'PT'}

PACE_CARD_TITLE = 'Pace & Four Factors'
ADVANCED_CARD_TITLE = 'ADVANCED'
KEY_CARD_TITLE = 'Paint / 2nd Chance / Fastbreak / Off TO / Bench'


def stat_header_label(name):
    return TAIL_LABEL.get(name, name)


def stat_th(label, kind, span=None, cols=None, edge=False):
    table_props = {}
    if span:
        table_props['rowSpan'] = span
    if cols:
        table_props['colSpan'] = cols
    props = {'className': kind}
    if table_props:
        props['tableProps'] = table_props
    return dmc.TableTh(label, **props)


def boundary_columns(segments):
    ends = set()
    for index, (kind, cols) in enumerate(segments):
        if not cols:
            continue
        if index + 1 >= len(segments):
            if kind == 'group':
                ends.add(cols[-1])
            continue
        if kind == 'group' or segments[index + 1][0] == 'group':
            ends.add(cols[-1])
    return ends


def card_segments(card_id, columns, include_extra_tails=False):
    present = set(columns)
    if card_id == 'advanced':
        return [('single', (column,)) for column in columns]
    segments = []
    if card_id == 'team':
        for name in ('Team', 'GP', 'Min'):
            if name in present:
                segments.append(('single', (name,)))
        for _title, members, _leaves in SHOT_GROUPS:
            cols = tuple(column for column in members if column in present)
            if cols:
                segments.append(('group', cols))
        tails = COUNT_TAILS + EXTRA_TAILS if include_extra_tails else COUNT_TAILS
        for column in tails:
            if column in present:
                segments.append(('single', (column,)))
        return segments
    if card_id == 'key':
        for name in ('Team', 'GP'):
            if name in present:
                segments.append(('single', (name,)))
        for _name, pairs in KEY_STAT_GROUPS:
            cols = tuple(column for column, _label in pairs if column in present)
            if cols:
                segments.append(('group', cols))
        if 'BP' in present:
            segments.append(('single', ('BP',)))
        return segments
    for name in ('Team', 'GP', 'Pace'):
        if name in present:
            segments.append(('single', (name,)))
    factors = tuple(column for column in ('eFG%', 'TO%', 'ORB%', 'FT-R') if column in present)
    if factors:
        segments.append(('group', factors))
    return segments


def edge_columns(card_id, columns, include_extra_tails=False):
    return boundary_columns(card_segments(card_id, columns, include_extra_tails=include_extra_tails))


def span_labels(columns, names, edges):
    present = set(columns)
    nodes = []
    for name in names:
        if name not in present:
            continue
        if name == 'Team':
            label = 'TEAM'
        elif name == 'GP':
            label = 'GP'
        else:
            label = name.upper()
        nodes.append(stat_th(label, 'braves-th-span', span=2, edge=name in edges))
    return nodes


def card_header_rows(card_id, columns, include_extra_tails=False):
    present = set(columns)
    edges = edge_columns(card_id, columns, include_extra_tails=include_extra_tails)
    if card_id == 'advanced':
        labels = []
        for column in columns:
            if column == 'Team':
                labels.append('TEAM')
            elif column == 'GP':
                labels.append('GP')
            else:
                labels.append(column)
        return [dmc.TableTr([
            stat_th(label, 'braves-th-single') for label in labels
        ])]

    top = []
    sub = []
    if card_id == 'team':
        top.extend(span_labels(columns, ('Team', 'GP', 'Min'), edges))
        for title, members, leaves in SHOT_GROUPS:
            if not any(column in present for column in members):
                continue
            top.append(stat_th(
                title, 'braves-th-group', cols=len(leaves), edge=members[-1] in edges,
            ))
            sub.extend(
                stat_th(leaf, 'braves-th-sub', edge=column in edges)
                for column, leaf in zip(members, leaves)
            )
        tails = COUNT_TAILS + EXTRA_TAILS if include_extra_tails else COUNT_TAILS
        for column in tails:
            if column in present:
                top.append(stat_th(
                    stat_header_label(column),
                    'braves-th-span-tight',
                    span=2,
                    edge=column in edges,
                ))
    elif card_id == 'key':
        top.extend(span_labels(columns, ('Team', 'GP'), edges))
        for name, pairs in KEY_STAT_GROUPS:
            found = [(column, label) for column, label in pairs if column in present]
            if not found:
                continue
            top.append(stat_th(
                name, 'braves-th-group', cols=len(found), edge=found[-1][0] in edges,
            ))
            sub.extend(
                stat_th(label, 'braves-th-sub', edge=column in edges)
                for column, label in found
            )
        if 'BP' in present:
            top.append(stat_th('BP', 'braves-th-span', span=2, edge='BP' in edges))
    else:
        top.extend(span_labels(columns, ('Team', 'GP', 'Pace'), edges))
        factors = [column for column in ('eFG%', 'TO%', 'ORB%', 'FT-R') if column in present]
        if factors:
            top.append(stat_th(
                'FOUR FACTORS', 'braves-th-group', cols=len(factors),
                edge=factors[-1] in edges,
            ))
            sub.extend(
                stat_th(column, 'braves-th-sub', edge=column in edges) for column in factors
            )
    rows = [dmc.TableTr(top)]
    if sub:
        rows.append(dmc.TableTr(sub))
    return rows


def parse_numeric_stat(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s in ('nan', 'None', '—', '-'):
        return None
    if s.endswith('%'):
        try:
            return float(s[:-1])
        except Exception as exc:
            log_data.debug('percent parse failed: %s', exc)
            return None
    if '(' in s and '%' in s:
        try:
            pct_part = s.split('(')[1].split('%')[0].strip()
            return float(pct_part)
        except Exception as exc:
            log_data.debug('fraction percent parse failed: %s', exc)
    if '-' in s and not s.startswith('-'):
        try:
            made_part = s.split('-')[0].strip()
            return float(made_part)
        except Exception as exc:
            log_data.debug('made-attempt parse failed: %s', exc)
    if ':' in s:
        try:
            parts = s.split(':')
            return float(parts[0]) * 60 + float(parts[1])
        except Exception as exc:
            log_data.debug('clock stat parse failed: %s', exc)
    try:
        return float(s)
    except Exception as exc:
        log_data.debug('stat parse failed: %s', exc)
        return None


def scroll_card_paper(scroll_id, title=None):
    scrolled = dmc.Box(id=scroll_id, className='braves-table-scroll')
    children = [scrolled]
    if title:
        children.insert(0, dmc.Text(
            title.upper(),
            size='xs',
            fw=700,
            c='dimmed',
            mb=6,
            style={'letterSpacing': '0.05em'},
        ))
    return dmc.Paper(
        children,
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def dmc_table_from_df(df, is_team_summary=True, title=None, away_name=None, home_name=None):
    if df is None or df.empty:
        return dmc.Text('No data available.', c='dimmed', ta='center', fs='italic', p='sm')

    is_timeouts_card = bool(title and 'timeout' in title.lower())
    col_winners = {}
    if is_team_summary and len(df) and not is_timeouts_card:
        is_fouls_card = bool(title and 'foul' in title.lower())
        for col in df.columns:
            if col in ('Team', 'Min', '3Pr', '3P-R'):
                continue
            values = [parse_numeric_stat(df.iloc[index][col]) for index in range(len(df))]
            lower = is_fouls_card or col in ('Foul', 'PF', 'TO', 'TOV', 'TO%')
            col_winners[col] = set(winning_indexes(values, lower))

    has_grouped_cols = any(c in df.columns for c in ('2M', '2A', '2FG%', '3M', '3A', '3FG%'))
    has_key_stats_grouped = any(c in df.columns for c in KEY_STAT_LEAVES)

    if has_grouped_cols:
        edge_cols = edge_columns('team', df.columns, include_extra_tails=True)
        header = card_header_rows('team', df.columns, include_extra_tails=True)
    elif has_key_stats_grouped:
        edge_cols = edge_columns('key', df.columns)
        header = card_header_rows('key', df.columns)
    elif any(c in df.columns for c in ('eFG%', 'TO%', 'ORB%', 'FT-R')):
        edge_cols = edge_columns('pace', df.columns)
        header = card_header_rows('pace', df.columns)
    elif any(c in df.columns for c in ('PPP', 'AS/TO', 'AST%', '3P-R', 'TS%')):
        edge_cols = set()
        adv_cols = (['Team'] if 'Team' in df.columns else []) + [
            col for col in ('PPP', 'AS/TO', 'AST%', '3P-R', 'TS%') if col in df.columns
        ]
        header = card_header_rows('advanced', adv_cols)
    else:
        edge_cols = set()
        header = [dmc.TableTr([
            stat_th(col, 'braves-th-single') for col in df.columns
        ])]

    rows = []
    for row_idx in range(len(df)):
        team_stripe_style = {}
        if is_team_summary and 'Team' in df.columns:
            raw_name = df.iloc[row_idx]['Team']
            team_name = '' if pd.isna(raw_name) else str(raw_name)
            stripe_color = team_stripe(team_name, away_name, home_name, row_idx)
            team_stripe_style = {'borderLeft': f'3.5px solid {stripe_color}'}

        cells = []
        for c_idx, col in enumerate(df.columns):
            val = df.iloc[row_idx][col]
            if pd.isna(val) or val is None or str(val).strip() in ('nan', 'None'):
                val_str = ''
            elif is_timeouts_card and str(val).strip() in ('0', '0.0'):
                val_str = ''
            else:
                val_str = str(val)

            is_winner = row_idx in col_winners.get(col, ())
            cell_style = {}
            if is_winner:
                cell_style.update(WINNER_STYLE)
            if c_idx == 0 and team_stripe_style:
                cell_style.update(team_stripe_style)
            classes = ['braves-group-end'] if col in edge_cols else []
            cells.append(dmc.TableTd(
                val_str,
                style=cell_style or None,
                className=' '.join(classes) or None,
            ))

        rows.append(dmc.TableTr(cells, className='braves-clean-row'))

    table = dmc.Table(
        [dmc.TableThead(header), dmc.TableTbody(rows)],
        withTableBorder=False,
        withColumnBorders=False,
        className='braves-clean-table',
        style={'width': '100%'},
    )

    scrolled = dmc.Box(table, className='braves-table-scroll')
    paper_children = [scrolled]
    if title:
        paper_children = [
            dmc.Text(title.upper(), size='xs', fw=700, c='dimmed', mb=6, style={'letterSpacing': '0.05em'}),
            scrolled,
        ]
    return dmc.Paper(
        paper_children,
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def team_label_cell(text, keep_vs=False):
    raw = '' if text is None else str(text)
    name = raw[:-3] if keep_vs and raw.endswith(' vs') else raw
    first, second = team_name_lines(name)
    if not second:
        return raw
    suffix = ' vs' if keep_vs else ''
    return html.Span(
        [
            html.Span(name + suffix, className='ts-team-full'),
            html.Span(first + suffix, className='ts-team-line1'),
            html.Span(second, className='ts-team-line2'),
        ],
        className='ts-team-label is-split',
    )


def team_stats_body_rows(card):
    columns = card.get('columns') or []
    edges = edge_columns(card.get('id'), columns)
    records = []
    for index, record in enumerate(card.get('rows') or []):
        records.append(record)
        opp_rows = card.get('opp_rows') or []
        if index < len(opp_rows):
            records.append(opp_rows[index])
    rows = []
    for record in records:
        opp = bool(isinstance(record, dict) and record.get('opp'))
        cells = []
        for column in columns:
            cell = record.get(column) if isinstance(record, dict) else None
            text = ''
            style = None
            if isinstance(cell, dict):
                text = '' if cell.get('text') is None else str(cell.get('text'))
                if opp and cell.get('opp_best'):
                    style = dict(OPP_BEST_STYLE)
                elif cell.get('winner'):
                    style = dict(WINNER_STYLE)
            classes = []
            if column in edges:
                classes.append('braves-group-end')
            if opp and column == 'Team':
                classes.append('braves-opp-label')
            kwargs = {}
            if style:
                kwargs['style'] = style
            if classes:
                kwargs['className'] = ' '.join(classes)
            content = text
            if column == 'Team':
                content = team_label_cell(
                    text,
                    keep_vs=(
                        not opp
                        and not (isinstance(record, dict) and record.get('summary'))
                        and text.endswith(' vs')
                    ),
                )
            cells.append(dmc.TableTd(content, **kwargs))
        class_name = 'braves-clean-row braves-opp-row' if opp else 'braves-clean-row'
        if isinstance(record, dict) and record.get('summary'):
            class_name += ' braves-summary-end' if opp else ' braves-summary-row'
        rows.append(dmc.TableTr(cells, className=class_name))
    return rows


def team_stats_paper(card):
    table = dmc.Table(
        [
            dmc.TableThead(card_header_rows(card.get('id'), card.get('columns') or [])),
            dmc.TableTbody(team_stats_body_rows(card)),
        ],
        withTableBorder=False,
        withColumnBorders=False,
        className='braves-clean-table',
        style={'width': '100%'},
    )
    children = [dmc.Box(table, className='braves-table-scroll')]
    title = card.get('title')
    if title:
        children.insert(0, dmc.Text(
            str(title).upper(),
            size='xs',
            fw=700,
            c='dimmed',
            mb=6,
            style={'letterSpacing': '0.05em'},
        ))
    return dmc.Paper(
        children,
        withBorder=True,
        radius='md',
        p='sm',
        shadow='xs',
        className='braves-card-wrapper',
    )


def team_stats_cards_view(cards):
    return dmc.Stack(
        [
            dmc.SimpleGrid(
                cols={'base': 1, 'lg': 2},
                spacing='12px',
                children=[team_stats_paper(cards['pace']), team_stats_paper(cards['advanced'])],
            ),
            team_stats_paper(cards['key']),
            team_stats_paper(cards['team']),
        ],
        gap='sm',
    )
