import io
import json
import pandas as pd
from dash import html
import dash_ag_grid as dag
import dash_bootstrap_components as dbc

# A4 Landscape content width: 297mm - 2*10mm padding = 277mm ≈ 1047px at 96dpi
A4_CONTENT_WIDTH_PX = 1047

def lineup_tables_for_size(lineup_store_data, lineup_size=5):
    """Pick one lineup-size table map from store data.

    New store shape: {"5": {team: json}, "4": ...}.
    Old store shape: {team: json}.
    """
    if not lineup_store_data:
        return {}
    if isinstance(lineup_store_data, str):
        try:
            lineup_dict = json.loads(lineup_store_data)
        except Exception:
            return {}
    else:
        lineup_dict = lineup_store_data
    if not isinstance(lineup_dict, dict) or not lineup_dict:
        return {}
    inner = lineup_dict.get(str(lineup_size))
    if isinstance(inner, dict):
        return inner
    if all(not str(key).isdigit() for key in lineup_dict):
        return lineup_dict
    return {}

def _pixel_width(s):
    """Calculate absolute pixel width for 11px font size."""
    if s is None or pd.isna(s):
        return 0
    return sum(11 if ord(c) > 127 else 6.5 for c in str(s))

def _calc_col_widths(df, container_px=A4_CONTENT_WIDTH_PX):
    """Calculate relative widths and minimum required widths."""
    raw_widths = {}
    for col in df.columns:
        header_req_px = _pixel_width(col) + 16 + 8
        max_data_req_px = df[col].apply(_pixel_width).max() + 8 if len(df) > 0 else 0
        
        # Absolute minimum width required before text truncation occurs
        raw_widths[col] = int(max(header_req_px, max_data_req_px))

    total_raw = sum(raw_widths.values())

    # We provide scaled widths for the *initial* flex distribution, 
    # but the min_width strictly uses the raw calculation to prevent excess whitespace.
    scaled_widths = {}
    if total_raw <= container_px:
        scale = container_px / total_raw
        scaled_widths = {col: int(w * scale) for col, w in raw_widths.items()}
    else:
        scaled_widths = {col: max(30, int(w * (container_px / total_raw))) for col, w in raw_widths.items()}
        
    return scaled_widths, raw_widths

def create_ag_grid(df, grid_id=None):
    """Create an AG Grid with:
    - ag-theme-material built-in theme
    - domLayout='autoHeight': height matches exact row count (no vertical scroll)
    - Column widths calculated to fit within container: max width capped at A4 width (no horizontal scroll)
    """
    if df is None or df.empty:
        return html.Div("—", className="text-muted fst-italic text-center p-2")

    col_widths, min_widths = _calc_col_widths(df)

    column_defs = []
    for col in df.columns:
        column_defs.append({
            "field": str(col),
            "headerName": str(col),
            "resizable": True,
            "sortable": True,
            "width": col_widths[col],
            "minWidth": min_widths[col], # Use absolute raw width, not scaled width
            "suppressSizeToFit": False,
        })

    return dag.AgGrid(
        id=grid_id if grid_id else f"grid-{id(df)}",
        rowData=df.to_dict("records"),
        columnDefs=column_defs,
        defaultColDef={
            "resizable": True,
            "sortable": True,
            "cellStyle": {"textAlign": "center", "fontSize": "11px", "padding": "2px 4px", "whiteSpace": "nowrap"},
            "headerClass": "center-aligned-header",
        },
        dashGridOptions={
            "domLayout": "autoHeight",
            "rowHeight": 28,
            "headerHeight": 32,
            "animateRows": False,
            "suppressColumnVirtualisation": True,
            "suppressRowVirtualisation": True,
        },
        className="ag-theme-material",
        style={"width": "100%", "maxWidth": f"{A4_CONTENT_WIDTH_PX}px"},
        columnSize="responsiveSizeToFit",
    )

def get_default_blocks(match_info=None):
    """Default report blocks: Match Info text box followed by Synergy data tables."""
    if match_info and isinstance(match_info, dict) and match_info.get('home_team'):
        lines = []
        if match_info.get('date'):
            lines.append(f"{match_info['date']}  {match_info.get('time', '')}")
        if match_info.get('venue'):
            lines.append(match_info['venue'])
        home = match_info.get('home_team', '')
        away = match_info.get('away_team', '')
        h_score = match_info.get('home_score', '')
        a_score = match_info.get('away_score', '')
        lines.append(f"{away}  {a_score}  @  {home}  {h_score}")
        match_text = "\n".join(lines)
    else:
        match_text = ""

    return [
        {
            "id": "block_match_info",
            "type": "text",
            "title": "",
            "content": match_text,
            "width_class": "col-12"
        },
        {
            "id": "block_score",
            "type": "builtin_table",
            "table_key": "score_group",
            "title": "Score"
        },
        {
            "id": "block_four_factors",
            "type": "builtin_table",
            "table_key": "t_adv_df",
            "title": "Pace, PPP & Four Factors"
        },
        {
            "id": "block_team_stats",
            "type": "builtin_table",
            "table_key": "t_df",
            "title": "Team Stats"
        },
        {
            "id": "block_key_stats",
            "type": "builtin_table",
            "table_key": "k_df",
            "title": "Key Stats"
        },
        {
            "id": "block_lineup_stats",
            "type": "builtin_table",
            "table_key": "lineup_dict",
            "title": "Lineup Stats"
        },
        {
            "id": "block_player_stats",
            "type": "builtin_table",
            "table_key": "p_df_dict",
            "title": "Player Box Score"
        },
    ]

def render_block(block, bs_dict, lineup_store_data):
    """Render read-only block card(s). Resizable via CSS."""
    b_id = block["id"]
    b_type = block["type"]
    width_class = block.get("width_class", "col-12")

    cards = []

    # ---- Text Block ----
    if b_type == "text":
        children = []
        control_bar = html.Div([
            html.Div("☰", className="drag-handle", title="Drag to reorder")
        ], className="block-controls no-print")
        children.append(control_bar)
        
        children.append(html.Div([
            html.Pre(block.get('content', ''), contentEditable=True, style={
                'whiteSpace': 'pre-wrap', 'fontSize': '13px', 'fontFamily': 'inherit', 
                'margin': '0', 'lineHeight': '1.5', 'color': '#334155',
                'outline': 'none', 'border': 'none', 'minWidth': '100%', 'minHeight': '100%'
            })
        ]))
        cards.append(html.Div(children, id=f"block-card-{b_id}", className="report-block-card"))

    # ---- Built-in Table Block ----
    elif b_type == "builtin_table":
        table_key = block.get("table_key", "")
        
        # Handle multiple tables for p_df_dict
        if table_key == 'p_df_dict' and bs_dict and table_key in bs_dict and bs_dict[table_key]:
            for team_name, p_json in sorted(bs_dict['p_df_dict'].items()):
                sub_id = f"{b_id}-{team_name.replace(' ', '')}"
                p_df = pd.read_json(io.StringIO(p_json), orient='split')
                children = [
                    html.Div([html.Div("☰", className="drag-handle", title="Drag to reorder")], className="block-controls no-print"),
                    html.Div([create_ag_grid(p_df, grid_id=f"grid-player-{team_name}-{b_id}")])
                ]
                cards.append(html.Div(children, id=f"block-card-{sub_id}", className="report-block-card"))
                
        # Handle multiple tables for lineup_dict
        elif table_key == 'lineup_dict' and lineup_store_data:
            lineup_dict = lineup_tables_for_size(lineup_store_data, lineup_size=5)
            for team_name, l_json in sorted(lineup_dict.items()):
                sub_id = f"{b_id}-{team_name.replace(' ', '')}"
                l_df = pd.read_json(io.StringIO(l_json), orient='split')
                children = [
                    html.Div([html.Div("☰", className="drag-handle", title="Drag to reorder")], className="block-controls no-print"),
                    html.Div([create_ag_grid(l_df, grid_id=f"grid-lineup-{team_name}-{b_id}")])
                ]
                cards.append(html.Div(children, id=f"block-card-{sub_id}", className="report-block-card"))
                
        # Single table cases
        else:
            table_content = render_builtin_table_content(table_key, bs_dict, b_id)
            children = [
                html.Div([html.Div("☰", className="drag-handle", title="Drag to reorder")], className="block-controls no-print"),
                html.Div([table_content])
            ]
            cards.append(html.Div(children, id=f"block-card-{b_id}", className="report-block-card"))

    return cards

def render_builtin_table_content(table_key, bs_dict, b_id):
    """Render built-in synergy tables using AG Grid (autoHeight, no scroll)."""
    if not bs_dict:
        return html.Div("載入中...", className="text-muted")

    try:
        if table_key == 'score_group':
            if 'qt_pts_df' in bs_dict and bs_dict['qt_pts_df']:
                df = pd.read_json(io.StringIO(bs_dict['qt_pts_df']), orient='split')
                return create_ag_grid(df, grid_id=f"grid-score-{b_id}")

        if table_key in bs_dict and bs_dict[table_key]:
            df = pd.read_json(io.StringIO(bs_dict[table_key]), orient='split')
            return create_ag_grid(df, grid_id=f"grid-builtin-{table_key}-{b_id}")

    except Exception as e:
        return html.Div(f"Error: {e}", className="text-danger small")

    return html.Div("—", className="text-muted")
