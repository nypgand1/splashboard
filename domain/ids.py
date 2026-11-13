# -*- coding: utf-8 -*-
"""Entity/person ID comparison and shirt-number sorting helpers."""
import pandas as pd

from synergy_inbounder.names import person_name


def same_id(left, right):
    """Compare two entity or person IDs safely across int/str/NaN representations."""
    if left is None or right is None:
        return False
    try:
        if pd.isna(left) or pd.isna(right):
            return False
    except TypeError:
        pass
    return str(left) == str(right)


def shirt_sort_key(shirt_number):
    """Sort numeric jersey numbers first, then non-numeric strings, then missing."""
    if shirt_number in (None, ''):
        return (2, 0, '')
    try:
        return (0, int(str(shirt_number).strip()), '')
    except ValueError:
        return (1, 0, str(shirt_number).strip())


def shirt_label(person_id, id_table, roster_by_id):
    """Format `#shirt Name` when a shirt number is known, otherwise `Name`."""
    name = person_name(id_table, person_id)
    shirt = (roster_by_id.get(person_id) or roster_by_id.get(str(person_id)) or {}).get('shirtNumber')
    if shirt not in (None, ''):
        return f'#{shirt} {name}'
    return name
