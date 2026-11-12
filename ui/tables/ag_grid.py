# -*- coding: utf-8 -*-
import json

import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd

from synergy_inbounder.logs import data as log_data
from ui.tokens import DNP_TEXT, JERSEY_MUTED, OPP_ROW_BG, PRIMARY_INK

LINEUP_COL_SIZES = {
    2: (140, 150),
    3: (180, 190),
    4: (220, 230),
    5: (240, 250),
}


def _lineup_col_size(lineup_size):
    try:
        size = int(lineup_size)
    except Exception as exc:
        log_data.debug('lineup size parse failed: %s', exc)
        size = 5
    return LINEUP_COL_SIZES.get(size, LINEUP_COL_SIZES[5])


def _stamp_designed_widths(column_defs):
    for col in column_defs:
        children = col.get('children')
        if children:
            _stamp_designed_widths(children)
        elif 'width' in col:
            col['designedWidth'] = col['width']
    return column_defs


_LINEUP_FIT_EVENTS = {
    'gridSizeChanged': ['splashboardFitLineupWidth(params)'],
    'firstDataRendered': ['splashboardFitLineupWidth(params)'],
}


def _append_def_class(defn, key, name):
    current = defn.get(key) or ''
    parts = str(current).split()
    if name not in parts:
        parts.append(name)
    defn[key] = ' '.join(parts)


def _lock_column_move(column_defs):
    for defn in column_defs:
        defn['suppressMovable'] = True
        for child in defn.get('children') or []:
            child['suppressMovable'] = True


def _mark_ag_group_edges(column_defs):
    last = len(column_defs) - 1
    for index, defn in enumerate(column_defs):
        children = defn.get('children')
        next_is_group = index < last and bool(column_defs[index + 1].get('children'))
        if children:
            _append_def_class(children[-1], 'cellClass', 'braves-group-end')
        elif next_is_group:
            _append_def_class(defn, 'cellClass', 'braves-group-end')


def _display_cell(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except TypeError:
        pass
    return value


def _lineup_visible_columns(df):
    return [
        col for col in df.columns
        if not str(col).startswith('Opp_') and not str(col).startswith('_')
    ]


def _lineup_pair_records(df):
    """One lineup JSON row becomes our row, then an Opp row on the same columns."""
    columns = _lineup_visible_columns(df)
    records = []
    for raw in df.to_dict('records'):
        own = {col: _display_cell(raw.get(col)) for col in columns}
        label = own.get('Lineup', own.get('Lineups', ''))
        key = _display_cell(raw.get('_lineup_key'))
        pair = key or label
        our = dict(own)
        our['_opp'] = False
        our['_pair'] = pair
        our['_own'] = dict(own)
        records.append(our)
        opp = {}
        for col in columns:
            if col in ('Min', '+/-'):
                opp[col] = ''
            elif 'lineup' in str(col).lower():
                opp[col] = label
            else:
                opp[col] = _display_cell(raw.get('Opp_' + col, ''))
        opp['_opp'] = True
        opp['_pair'] = pair
        opp['_own'] = dict(own)
        records.append(opp)
    return records


_DESC_SORT_FIELDS = {
    '#', 'Min', '+/-',
    '2M', '2A', '2FG%', '3M', '3A', '3FG%', 'FTM', 'FTA', 'FT%',
    'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS', 'PF', 'FD', 'PTS',
    'PIP', 'SCP', 'FBP', 'POT', 'PPP', 'eFG%', 'USG%',
}
DESC_FIRST_SORT = ['desc', 'asc', None]


def _numeric_rank_js():
    # M:SS becomes seconds. A trailing % is stripped so 0.0% and .833 compare
    # as numbers. Blank stays below 0.
    return (
        "(function(raw) {"
        "return raw === '' || raw === null || raw === undefined ? null"
        " : (typeof raw === 'number' ? (raw !== raw ? null : raw)"
        " : (typeof raw === 'string' && raw.indexOf(':') >= 0"
        " ? (function(parts) {"
        "return parts && parts.length === 2 && (+parts[0]) === (+parts[0]) && (+parts[1]) === (+parts[1])"
        " ? (+parts[0]) * 60 + (+parts[1]) : null;"
        "})(raw.split(':'))"
        " : (typeof raw === 'string'"
        " ? (function(text) { return (+text) === (+text) ? +text : null; })(raw.replace('%', ''))"
        " : null)));"
        "})"
    )


def _lineup_pair_comparator(field):
    # dash-ag-grid evaluates this once with static-eval. That walker rejects
    # var/if/for, and it prewalks the body with every parameter set to null,
    # so member access and `typeof` stay behind a null check.
    # AG Grid inverts a descending column. The DNP bias flips with
    # isDescending so those rows stay last in both directions.
    field_js = json.dumps(field)
    rank = _numeric_rank_js()
    return {
        "function": (
            "(function(a, b, nodeA, nodeB, isDescending) {"
            "return (function(dnpA, dnpB) {"
            "return dnpA !== dnpB ? (dnpA ? 1 : -1) * (isDescending ? -1 : 1)"
            " : (function(av, bv) {"
            "return (function(an, bn) {"
            "return an === null && bn === null ? (av < bv ? -1 : av > bv ? 1 : 0)"
            " : an === null ? -1 : bn === null ? 1"
            " : an < bn ? -1 : an > bn ? 1 : 0;"
            "})(" + rank + "(av), " + rank + "(bv));"
            "})("
            f"nodeA && nodeA.data ? (nodeA.data._own ? nodeA.data._own[{field_js}] : nodeA.data[{field_js}]) : null,"
            f"nodeB && nodeB.data ? (nodeB.data._own ? nodeB.data._own[{field_js}] : nodeB.data[{field_js}]) : null);"
            "})("
            "nodeA && nodeA.data && nodeA.data.Min === 'DNP',"
            "nodeB && nodeB.data && nodeB.data.Min === 'DNP');"
            "})"
        )
    }


# Family, then the initial run. J.Lee sorts with K.Lee. dash-ag-grid's
# function walker rejects var/if/for and prewalks with null arguments.
_PLAYER_NAME_COMPARATOR = {
    "function": (
        "(function(a, b) {"
        "return (function(keyOf) {"
        "return (function(ka, kb) {"
        "return !ka || !kb ? 0"
        " : ka[0] < kb[0] ? -1 : ka[0] > kb[0] ? 1"
        " : ka[1] < kb[1] ? -1 : ka[1] > kb[1] ? 1 : 0;"
        "})(keyOf ? keyOf(a) : null, keyOf ? keyOf(b) : null);"
        "})(function(label) {"
        "return (function(text) {"
        "return (function(match) {"
        "return match ? [match[2].toLowerCase(), match[1].toLowerCase()]"
        " : [(text && text.toLowerCase) ? text.toLowerCase() : '', ''];"
        "})(text && text.match ? text.match(/^((?:[A-Z]\\.)+)(.+)$/) : null);"
        "})(label == null ? '' : '' + label);"
        "});"
        "})"
    ),
}


def _apply_click_sort(col):
    field = col.get('field')
    if field == 'Player':
        col['comparator'] = _PLAYER_NAME_COMPARATOR
        return
    if field not in _DESC_SORT_FIELDS:
        return
    col['sortingOrder'] = list(DESC_FIRST_SORT)
    col['comparator'] = _lineup_pair_comparator(field)


def _apply_click_sort_columns(column_defs):
    for col in column_defs:
        children = col.get('children')
        if children:
            _apply_click_sort_columns(children)
            continue
        _apply_click_sort(col)


# postSortRows is compiled as `params => expr` on every sort. Snapshot the
# comparator order first: indexOf on the live array moves while it sorts.
_LINEUP_POST_SORT = {
    "function": (
        "(function(original) {"
        "return params.nodes.sort(function(a, b) {"
        "return (function(ai, bi) {"
        "return ai < bi ? -1 : ai > bi ? 1"
        " : ((a && a.data && a.data._opp) ? 1 : 0) - ((b && b.data && b.data._opp) ? 1 : 0);"
        "})("
        "original ? original.indexOf(original.find(function(n) {"
        "return n && n.data && a && a.data && n.data._pair === a.data._pair && !n.data._opp;"
        "})) : -1,"
        "original ? original.indexOf(original.find(function(n) {"
        "return n && n.data && b && b.data && n.data._pair === b.data._pair && !n.data._opp;"
        "})) : -1);"
        "});"
        "})(params && params.nodes ? params.nodes.slice() : [])"
    )
}


def _build_stats_column_defs(columns, filterable_cols=None, lineup_size=5):
    col_set = set(columns)
    column_defs = []

    sorted_cell_rules = {"ag-sorted-col-bg": "params.column.isSortActive()"}
    is_lineup = any('lineup' in str(name).lower() for name in col_set)
    if is_lineup:
        count_min, count_w = 22, 22
        pct_min, pct_w = 42, 42
        letter_min, letter_w = 28, 30
        minute_min, minute_w = 44, 48
        plusminus_min, plusminus_w = 34, 36
        pt_min, pt_w = 36, 40
        key_min, key_w = 26, 26
        ppp_min, ppp_w = 36, 40
    else:
        count_min, count_w = 36, 38
        pct_min, pct_w = 52, 56
        letter_min, letter_w = 42, 44
        minute_min, minute_w = 50, 56
        plusminus_min, plusminus_w = 46, 48
        pt_min, pt_w = 44, 46
        key_min, key_w = 42, 44
        ppp_min, ppp_w = 48, 52

    def _num_col(field, header, min_w, width):
        return {
            "field": field,
            "headerName": header,
            "sortable": True,
            "minWidth": min_w,
            "width": width,
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        }

    # Pinned left columns: #, PLAYER/LINEUP/TEAM, S
    if '#' in col_set:
        column_defs.append({
            "field": "#",
            "headerName": "#",
            "pinned": "left",
            "sortable": True,
            "filter": False,
            "cellDataType": "text",
            "minWidth": 36,
            "width": 38,
            "cellStyle": {"textAlign": "center", "fontWeight": "600", "color": JERSEY_MUTED},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
            "valueFormatter": {"function": "params.value != null ? params.value : ''"},
            "colSpan": {"function": "params.data && (params.data['#'] === 'TEAM / COACHES' || params.data['#'] === 'TOTAL') ? 2 : 1"},
        })

    first_col = next((c for c in ('Player', 'Lineup', 'Lineups', 'Team') if c in col_set), None)
    if first_col:
        is_lineup = 'lineup' in first_col.lower()
        has_filter = bool(filterable_cols and any(fc.lower() in first_col.lower() for fc in filterable_cols))
        col_def = {
            "field": first_col,
            "headerName": first_col.upper(),
            "pinned": "left",
            "sortable": True,
            "filter": has_filter,
            "cellStyle": {"textAlign": "center", "fontWeight": "700"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        }
        if is_lineup:
            min_w, width = _lineup_col_size(lineup_size)
            col_def["minWidth"] = min_w
            col_def["width"] = width
            col_def["wrapText"] = True
            col_def["autoHeight"] = True
            col_def["cellStyle"] = {
                "textAlign": "center",
                "fontWeight": "700",
                "whiteSpace": "normal",
                "lineHeight": "1.3",
            }
        else:
            col_def["minWidth"] = 95
            col_def["width"] = 95
            if first_col == 'Player':
                col_def["tooltipField"] = "_playerFull"
        column_defs.append(col_def)

    if 'S' in col_set:
        column_defs.append({
            "field": "S",
            "headerName": "S",
            "sortable": True,
            "minWidth": 34,
            "width": 36,
            "cellRenderer": "StarterCell",
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if 'Min' in col_set:
        column_defs.append({
            "field": "Min",
            "headerName": "MIN",
            "sortable": True,
            "minWidth": minute_min,
            "width": minute_w,
            "cellStyle": {
                "styleConditions": [
                    {
                        "condition": "params.value === 'DNP'",
                        "style": {"textAlign": "center", "fontWeight": "700", "color": DNP_TEXT, "letterSpacing": "0.05em"}
                    }
                ],
                "default": {"textAlign": "center"}
            },
            "colSpan": {"function": "params.data && params.data['Min'] === 'DNP' ? 30 : 1"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if '+/-' in col_set:
        column_defs.append({
            "field": "+/-",
            "headerName": "+/-",
            "sortable": True,
            "minWidth": plusminus_min,
            "width": plusminus_w,
            "cellRenderer": "PlusMinusCell",
            "cellStyle": {"textAlign": "center"},
            "cellClass": "ag-cell-align-center",
            "headerClass": "ag-header-align-center",
            "cellClassRules": sorted_cell_rules,
        })

    if any(c in col_set for c in ('2M', '2A', '2FG%')):
        children = []
        if '2M' in col_set:
            children.append(_num_col("2M", "M", count_min, count_w))
        if '2A' in col_set:
            children.append(_num_col("2A", "A", count_min, count_w))
        if '2FG%' in col_set:
            children.append(_num_col("2FG%", "%", pct_min, pct_w))
        column_defs.append({
            "headerName": "2PT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('3M', '3A', '3FG%')):
        children = []
        if '3M' in col_set:
            children.append(_num_col("3M", "M", count_min, count_w))
        if '3A' in col_set:
            children.append(_num_col("3A", "A", count_min, count_w))
        if '3FG%' in col_set:
            children.append(_num_col("3FG%", "%", pct_min, pct_w))
        column_defs.append({
            "headerName": "3PT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('FTM', 'FTA', 'FT%')):
        children = []
        if 'FTM' in col_set:
            children.append(_num_col("FTM", "M", count_min, count_w))
        if 'FTA' in col_set:
            children.append(_num_col("FTA", "A", count_min, count_w))
        if 'FT%' in col_set:
            children.append(_num_col("FT%", "%", pct_min, pct_w))
        column_defs.append({
            "headerName": "FT",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    if any(c in col_set for c in ('OR', 'DR', 'REB')):
        children = []
        if 'OR' in col_set:
            children.append(_num_col("OR", "O", count_min, count_w))
        if 'DR' in col_set:
            children.append(_num_col("DR", "D", count_min, count_w))
        if 'REB' in col_set:
            children.append(_num_col("REB", "T", count_min, count_w))
        column_defs.append({
            "headerName": "REB",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": children,
        })

    stat_specs = [
        ('AST', 'AS', letter_min, letter_w),
        ('TO', 'TO', letter_min, letter_w),
        ('ST', 'ST', letter_min, letter_w),
        ('BS', 'BS', letter_min, letter_w),
        ('PF', 'PF', letter_min, letter_w),
        ('FD', 'FD', letter_min, letter_w),
        ('PTS', 'PT', pt_min, pt_w),
    ]
    for col_name, hdr_name, min_w, w in stat_specs:
        if col_name in col_set:
            column_defs.append({
                "field": col_name,
                "headerName": hdr_name,
                "sortable": True,
                "minWidth": min_w,
                "width": w,
                "cellStyle": {"textAlign": "center"},
                "cellClass": "ag-cell-align-center",
                "headerClass": "ag-header-align-center",
                "cellClassRules": sorted_cell_rules,
            })

    key_fields = [name for name in ('PIP', 'SCP', 'FBP', 'POT') if name in col_set]
    if key_fields:
        column_defs.append({
            "headerName": "Key Stats",
            "marryChildren": True,
            "headerClass": "ag-header-group-center",
            "children": [
                {
                    "field": name,
                    "headerName": name,
                    "sortable": True,
                    "minWidth": key_min,
                    "width": key_w,
                    "cellStyle": {"textAlign": "center"},
                    "cellClass": "ag-cell-align-center",
                    "headerClass": "ag-header-align-center",
                    "cellClassRules": sorted_cell_rules,
                }
                for name in key_fields
            ],
        })

    stat_specs = [
        ('PPP', 'PPP', ppp_min, ppp_w),
        ('eFG%', 'eFG%', 54, 58),
        ('USG%', 'USG%', 54, 58),
        ('PM', 'PM', 56, 62),
    ]
    for col_name, hdr_name, min_w, w in stat_specs:
        if col_name in col_set:
            column_defs.append({
                "field": col_name,
                "headerName": hdr_name,
                "sortable": True,
                "minWidth": min_w,
                "width": w,
                "cellStyle": {"textAlign": "center"},
                "cellClass": "ag-cell-align-center",
                "headerClass": "ag-header-align-center",
                "cellClassRules": sorted_cell_rules,
            })

    _apply_click_sort_columns(column_defs)
    _mark_ag_group_edges(column_defs)
    _lock_column_move(column_defs)
    return _stamp_designed_widths(column_defs)


def _apply_matchup_pair_columns(column_defs):
    for col in column_defs:
        children = col.get('children')
        if children:
            _apply_matchup_pair_columns(children)
            continue
        field = col.get('field')
        if not field:
            continue
        col['comparator'] = _lineup_pair_comparator(field)
        if field != 'Lineup':
            continue
        rules = dict(col.get('cellClassRules') or {})
        rules['ag-cell-align-right'] = 'params.data && params.data._opp'
        rules['ag-cell-align-left'] = '!(params.data && params.data._opp)'
        col['cellClassRules'] = rules
        col.pop('cellClass', None)
        col['filterValueGetter'] = {
            'function': "params.data && params.data._filter ? params.data._filter : ''",
        }
        col['cellStyle'] = {
            'styleConditions': [
                {
                    'condition': 'params.data && params.data._opp',
                    'style': {
                        'textAlign': 'right',
                        'fontWeight': '400',
                        'color': PRIMARY_INK,
                        'whiteSpace': 'normal',
                        'lineHeight': '1.3',
                    },
                }
            ],
            'defaultStyle': {
                'textAlign': 'left',
                'fontWeight': '700',
                'whiteSpace': 'normal',
                'lineHeight': '1.3',
            },
        }


def _matchup_column_defs():
    columns = [
        'Lineup', 'Min', '+/-', '2M', '2A', '2FG%', '3M', '3A', '3FG%',
        'FTM', 'FTA', 'FT%', 'OR', 'DR', 'REB', 'AST', 'TO', 'ST', 'BS',
        'PF', 'FD', 'PTS', 'PIP', 'SCP', 'FBP', 'POT', 'PPP',
    ]
    column_defs = _build_stats_column_defs(
        columns,
        filterable_cols=['Lineup'],
        lineup_size=5,
    )
    _apply_matchup_pair_columns(column_defs)
    return column_defs


def _matchup_grid(grid_id='matchup-grid', row_data=None):
    return dag.AgGrid(
        id=grid_id,
        rowData=list(row_data or []),
        columnDefs=_matchup_column_defs(),
        defaultColDef={
            'sortable': True,
            'filter': False,
            'resizable': True,
            'suppressMovable': True,
            'cellDataType': False,
        },
        dashGridOptions={
            'domLayout': 'autoHeight',
            'suppressHorizontalScroll': False,
            'suppressMovableColumns': True,
            'postSortRows': _LINEUP_POST_SORT,
        },
        eventListeners=_LINEUP_FIT_EVENTS,
        className='ag-theme-alpine braves-clean-ag-grid braves-lineup-grid',
        style={'width': '100%'},
        getRowId="params.data._pair + (params.data._opp ? ':other' : ':view')",
        getRowStyle={
            'styleConditions': [
                {
                    'condition': 'params.data && params.data._opp',
                    'style': {'backgroundColor': OPP_ROW_BG},
                }
            ],
            'defaultStyle': {'backgroundColor': '#ffffff'},
        },
        rowClassRules={'lineup-opp-row': 'params.data && params.data._opp'},
    )


def _apply_lineup_pair_columns(column_defs):
    for col in column_defs:
        children = col.get("children")
        if children:
            _apply_lineup_pair_columns(children)
            continue
        field = col.get("field")
        if not field:
            continue
        col["comparator"] = _lineup_pair_comparator(field)
        if "lineup" not in str(field).lower():
            continue
        rules = dict(col.get("cellClassRules") or {})
        rules["ag-cell-align-right"] = "params.data && params.data._opp"
        rules["ag-cell-align-center"] = "!(params.data && params.data._opp)"
        col["cellClassRules"] = rules
        col.pop("cellClass", None)
        field_js = json.dumps(field)
        col["valueGetter"] = {
            "function": (
                "params.data && params.data._opp ? 'Opp' : "
                f"(params.data ? params.data[{field_js}] : '')"
            ),
        }
        col["filterValueGetter"] = {
            "function": f"params.data ? params.data[{field_js}] : ''",
        }
        col["cellStyle"] = {
            "styleConditions": [
                {
                    "condition": "params.data && params.data._opp",
                    "style": {
                        "textAlign": "right",
                        "fontWeight": "400",
                        "color": PRIMARY_INK,
                        "whiteSpace": "normal",
                        "lineHeight": "1.3",
                    },
                }
            ],
            "defaultStyle": {
                "textAlign": "center",
                "fontWeight": "700",
                "whiteSpace": "normal",
                "lineHeight": "1.3",
            },
        }


def _ag_grid_from_df(df, page_size=None, filterable_cols=None, pinned_bottom_data=None, lineup_size=5, row_records=None, pair_rows=False, show_opp=False, grid_id=None):
    if df is None or df.empty:
        return dmc.Text("No data available.", c="dimmed", ta="center", fs="italic", p="sm")

    sorted_cell_rules = {"ag-sorted-col-bg": "params.column.isSortActive()"}

    if any(c in df.columns for c in ('2M', '2A', '2FG%', '3M', '3A', '3FG%')):
        column_defs = _build_stats_column_defs(
            df.columns,
            filterable_cols=filterable_cols,
            lineup_size=lineup_size,
        )
    else:
        column_defs = []
        for c in df.columns:
            align = "center"
            cell_style = {"textAlign": align}
            if c in ('Player', 'Lineup', 'Lineups') or 'lineup' in c.lower():
                cell_style["fontWeight"] = "700"

            has_filter = bool(filterable_cols and (c in filterable_cols or any(fc.lower() in c.lower() for fc in filterable_cols)))

            col_width_props = {}
            if c in ('Lineup', 'Lineups') or 'lineup' in c.lower():
                min_w, width = _lineup_col_size(lineup_size)
                col_width_props["minWidth"] = min_w
                col_width_props["width"] = width
            elif c in ('Player', 'Team'):
                col_width_props["minWidth"] = 90
                col_width_props["width"] = 95
            elif c == 'Min':
                col_width_props["minWidth"] = 50
                col_width_props["width"] = 55
            elif c in ('PM', '+/-'):
                col_width_props["minWidth"] = 42
                col_width_props["width"] = 45
            else:
                col_width_props["minWidth"] = 38
                col_width_props["width"] = 42

            col_def = {
                "field": c,
                "headerName": c,
                "sortable": True,
                "filter": has_filter,
                "cellStyle": cell_style,
                "cellClass": f"ag-cell-align-{align}",
                "headerClass": f"ag-header-align-{align}",
                "cellClassRules": sorted_cell_rules,
                **col_width_props,
            }
            if c in ('Lineup', 'Lineups') or 'lineup' in c.lower():
                col_def['wrapText'] = True
                col_def['autoHeight'] = True
                col_def['cellStyle'] = {
                    **cell_style,
                    'whiteSpace': 'normal',
                    'lineHeight': '1.3',
                }
            col_def['suppressMovable'] = True
            _apply_click_sort(col_def)
            column_defs.append(col_def)
        _stamp_designed_widths(column_defs)

    dash_options = {
        "domLayout": "autoHeight",
        "suppressHorizontalScroll": False,
        "suppressMovableColumns": True,
    }
    lineup_events = None
    if any('lineup' in str(col).lower() for col in df.columns):
        lineup_events = _LINEUP_FIT_EVENTS
    if page_size:
        dash_options["pagination"] = True
        dash_options["paginationPageSize"] = page_size
    if pinned_bottom_data:
        dash_options["pinnedBottomRowData"] = pinned_bottom_data
    pair_props = {}
    if pair_rows:
        _apply_lineup_pair_columns(column_defs)
        dash_options["postSortRows"] = _LINEUP_POST_SORT
        dash_options["isExternalFilterPresent"] = {
            "function": "false" if show_opp else "true",
        }
        dash_options["doesExternalFilterPass"] = {
            "function": "!(params && params.data && params.data._opp)",
        }
        pair_props = {
            "id": grid_id,
            "getRowId": "params.data._pair + (params.data._opp ? ':opp' : ':us')",
            "getRowStyle": {
                "styleConditions": [
                    {
                        "condition": "params.data && params.data._opp",
                        "style": {"backgroundColor": OPP_ROW_BG},
                    }
                ],
                "defaultStyle": {"backgroundColor": "#ffffff"},
            },
            "rowClassRules": {"lineup-opp-row": "params.data && params.data._opp"},
        }

    grid_class = "ag-theme-alpine braves-clean-ag-grid"
    if any('lineup' in str(c).lower() for c in df.columns):
        grid_class += " braves-lineup-grid"
    if lineup_events:
        pair_props = dict(pair_props)
        pair_props['eventListeners'] = lineup_events
    return dmc.Paper(
        dag.AgGrid(
            rowData=row_records if row_records is not None else df.to_dict('records'),
            columnDefs=column_defs,
            defaultColDef={"sortable": True, "filter": False, "resizable": True, "suppressMovable": True, "cellClassRules": sorted_cell_rules, "cellDataType": False},
            dashGridOptions=dash_options,
            className=grid_class,
            style={'width': '100%'},
            **pair_props,
        ),
        withBorder=True,
        radius="md",
        shadow="xs",
        mb="md",
        className="braves-grid-wrap",
        style={"overflowX": "auto"},
    )
