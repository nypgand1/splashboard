# -*- coding: utf-8 -*-
"""Display names for teams and venues. Player names stay on the raw id fallback."""

TEAM_TBD = 'TBD'


def _blank(value):
    if value is None:
        return True
    try:
        import pandas as pd
        if pd.isna(value):
            return True
    except TypeError:
        pass
    text = str(value).strip()
    return (not text) or text.lower() in ('nan', 'none')


def display_name(id_table, entity_id):
    """Team or venue label. Missing id, missing row, or a blank name is TBD."""
    if _blank(entity_id):
        return TEAM_TBD
    table = id_table or {}
    name = table.get(entity_id)
    if name is None:
        name = table.get(str(entity_id))
    if _blank(name):
        return TEAM_TBD
    return str(name).strip()
