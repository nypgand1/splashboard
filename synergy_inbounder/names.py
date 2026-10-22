# -*- coding: utf-8 -*-
"""Team, venue, and player display names.

Team and venue misses render TBD. A missing player name stays the raw id.
Latin player labels are shortened at paint; CJK names stay full.
"""
import re

TEAM_TBD = 'TBD'

_CJK = re.compile(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af\uf900-\ufaff]')
_LABEL_KEY = re.compile(r'^((?:[A-Z]\.)+)(.+)$')
_SUFFIXES = {'JR', 'SR', 'II', 'III', 'IV'}
_PARTICLES = {'DE', 'DEL', 'VAN', 'VON', 'DA', 'DI', 'ST', 'LA', 'LE', 'BIN', 'AL'}


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


def contains_cjk(value):
    return bool(_CJK.search('' if value is None else str(value)))


def _letters(token):
    return ''.join(ch for ch in token if ch.isalpha())


def _is_suffix(token):
    return _letters(token).upper() in _SUFFIXES


def _is_particle(token):
    return _letters(token).upper() in _PARTICLES


def _is_caps_word(token):
    if '.' in token:
        return False
    letters = _letters(token)
    return len(letters) >= 2 and letters.isupper()


def _token_is_all_caps(token):
    letters = _letters(token)
    return bool(letters) and letters.isupper()


def _drop_suffixes(tokens):
    cleaned = list(tokens)
    while cleaned and _is_suffix(cleaned[-1]):
        cleaned.pop()
    return cleaned


def _title_token(token):
    def repl(match):
        word = match.group(0)
        return word[:1].upper() + word[1:].lower()

    return re.sub(r'[A-Za-z]+', repl, token)


def _title_join(tokens):
    return ' '.join(_title_token(token) for token in tokens)


def _initials(given):
    letters = []
    for syllable in str(given).split('-'):
        for ch in syllable:
            if ch.isalpha():
                letters.append(ch.upper())
                break
    return '.'.join(letters)


def _format(given, family):
    initials = _initials(given)
    if not initials:
        return family
    return f'{initials}.{family}'


def _family_tokens(tokens, family_index):
    if family_index > 1 and _is_particle(tokens[family_index - 1]):
        return [tokens[family_index - 1], tokens[family_index]]
    return [tokens[family_index]]


def _label_from_tokens(tokens):
    tokens = _drop_suffixes(tokens)
    if not tokens:
        return ''
    if len(tokens) == 1:
        return _title_token(tokens[0])
    if all(_token_is_all_caps(token) for token in tokens):
        family = _title_join(_family_tokens(tokens, len(tokens) - 1))
        return _format(tokens[0], family)
    if _is_caps_word(tokens[0]) and any(not _is_caps_word(token) for token in tokens[1:]):
        end = 1
        while end < len(tokens) and _is_caps_word(tokens[end]):
            end += 1
        return _format(tokens[end], _title_join(tokens[:end]))
    caps_at = [index for index, token in enumerate(tokens) if _is_caps_word(token)]
    family_index = caps_at[-1] if caps_at else len(tokens) - 1
    return _format(tokens[0], _title_join(_family_tokens(tokens, family_index)))


def _comma_label(text):
    head, tail = text.split(',', 1)
    head_tokens = _drop_suffixes(head.split())
    tail_tokens = _drop_suffixes(tail.replace(',', ' ').split())
    if not tail_tokens:
        if not head_tokens:
            return text.strip()
        if len(head_tokens) == 1:
            return _title_token(head_tokens[0])
        return _label_from_tokens(head_tokens)
    if not head_tokens:
        if len(tail_tokens) == 1:
            return _title_token(tail_tokens[0])
        return _label_from_tokens(tail_tokens)
    return _format(tail_tokens[0], _title_token(head_tokens[-1]))


def player_label(name):
    """Short Latin label. CJK and a single token stay as written."""
    if _blank(name):
        return ''
    text = str(name).strip()
    if _CJK.search(text):
        return text
    if ',' in text:
        return _comma_label(text)
    tokens = text.split()
    if len(tokens) == 1:
        return tokens[0]
    return _label_from_tokens(tokens)


def player_sort_key(label):
    """Family, then initials, so J.Lee sorts with K.Lee."""
    text = '' if label is None else str(label).strip()
    match = _LABEL_KEY.match(text)
    if not match:
        return (text.casefold(), '')
    return (match.group(2).casefold(), match.group(1).casefold())


def _table_get(id_table, entity_id):
    table = id_table or {}
    if entity_id in table:
        found = table[entity_id]
    else:
        found = table.get(str(entity_id))
    return found


def person_full_name(id_table, person_id):
    """Stored nameFullLocal. A miss or a blank name is the raw id."""
    if _blank(person_id):
        return ''
    name = _table_get(id_table, person_id)
    if _blank(name):
        return str(person_id).strip()
    return str(name).strip()


def person_name(id_table, person_id):
    """Painted player label. A miss stays the raw id, never TBD."""
    full = person_full_name(id_table, person_id)
    if not full or full == str(person_id).strip():
        return full
    return player_label(full)


def shirt_text(shirt):
    """Jersey text. 7 and 7.0 are 7. A blank shirt is empty."""
    if isinstance(shirt, bool) or _blank(shirt):
        return ''
    if isinstance(shirt, int):
        return str(shirt)
    if isinstance(shirt, float):
        if shirt.is_integer():
            return str(int(shirt))
        return str(shirt).strip()
    text = str(shirt).strip()
    if len(text) > 2 and text.endswith('.0') and text[:-2].lstrip('-').isdigit():
        return text[:-2]
    return text


def shared_short_labels(id_table, person_ids):
    """Short labels worn by two or more of these people."""
    groups = {}
    for pid in person_ids or []:
        if _blank(pid):
            continue
        label = person_name(id_table, pid)
        if not label:
            continue
        groups.setdefault(label, set()).add(str(pid).strip())
    return {label for label, ids in groups.items() if len(ids) >= 2}


def lineup_token(id_table, person_id, shirt, shared_labels):
    """Short label. A shared label with a shirt gains # and that shirt."""
    label = person_name(id_table, person_id)
    if shared_labels and label in shared_labels:
        text = shirt_text(shirt)
        if text:
            return f'{label}#{text}'
    return label


def team_person_ids(roster, team_id, on_court_lists):
    """That team's roster, including DNP, plus anyone on its on-court lists."""
    found = []
    seen = set()

    def add(pid):
        if _blank(pid):
            return
        key = str(pid).strip()
        if key in seen:
            return
        seen.add(key)
        found.append(pid)

    team = None if team_id is None else str(team_id).strip()
    for person in roster or []:
        if not isinstance(person, dict):
            continue
        entity = person.get('entityId')
        if not team or entity is None or str(entity).strip() != team:
            continue
        add(person.get('personId'))
    for players in on_court_lists or []:
        if isinstance(players, (list, tuple)):
            for pid in players:
                add(pid)
    return found
