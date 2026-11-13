# -*- coding: utf-8 -*-
"""Named-club menus from fixture rows.

Home passes the whole season. Team Stats passes one game type. The label
lookup stays with the caller because the row shapes differ.
"""


def named_side_options(records, name_of, all_label, all_value='all', prefix=''):
    """Options for clubs named on ``records``.

    ``name_of(record, side)`` receives ``'home'`` or ``'away'`` and returns
    ``(entity_id, name)``, or ``None`` when that side is missing. The first
    option is ``all_label``. ``visible`` is true when at least two clubs remain.
    """
    found = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        for side in ('home', 'away'):
            pair = name_of(record, side)
            if not pair:
                continue
            entity, name = pair
            entity = str(entity or '').strip()
            name = str(name or '').strip()
            if not entity or not name:
                continue
            found.setdefault(entity, name)
    ordered = sorted(found.items(), key=lambda item: (item[1], item[0]))
    options = [{'label': all_label, 'value': all_value}]
    options.extend(
        {'label': prefix + name, 'value': entity} for entity, name in ordered
    )
    return options, len(ordered) >= 2
