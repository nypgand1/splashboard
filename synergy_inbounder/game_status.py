# -*- coding: utf-8 -*-
"""Fixture status buckets shared by Home, Game, and live/official routing."""

FINISHED_STATUSES = frozenset({'FINISHED', 'CONFIRMED'})
LIVE_PLAY_STATUSES = frozenset({
    'PENDING',
    'ABOUT_TO_START',
    'WARM_UP',
    'ON_PITCH',
    'IN_PROGRESS',
})
UNPLAYED_STATUSES = frozenset({'SCHEDULED', 'IF_NEEDED', 'DRAFT', 'POSTPONED'})
VOID_STATUSES = frozenset({'CANCELLED', 'BYE'})
ABANDONED_STATUSES = frozenset({'ABANDONED'})

BUCKET_FINISHED = 'finished'
BUCKET_LIVE = 'live'
BUCKET_UNPLAYED = 'unplayed'
BUCKET_VOID = 'void'

SCORE_EM_DASH = '—'
SCORE_VS = 'vs'

BADGE_STYLES = {
    BUCKET_UNPLAYED: {
        'backgroundColor': '#e0f2fe',
        'color': '#0284c7',
        'border': '1px solid #00b4d8',
    },
    BUCKET_LIVE: {
        'backgroundColor': '#fee2e2',
        'color': '#dc2626',
        'border': '1px solid #ef4444',
    },
    BUCKET_FINISHED: {
        'backgroundColor': '#f1f5f9',
        'color': '#475569',
        'border': '1px solid #cbd5e1',
    },
    BUCKET_VOID: {
        'backgroundColor': '#e2e8f0',
        'color': '#334155',
        'border': '1px solid #94a3b8',
    },
}


def normalize_status(status):
    if status is None:
        return ''
    return str(status).strip()


def status_bucket(status):
    value = normalize_status(status)
    if value in FINISHED_STATUSES:
        return BUCKET_FINISHED
    if value in LIVE_PLAY_STATUSES:
        return BUCKET_LIVE
    if value in VOID_STATUSES or value in ABANDONED_STATUSES:
        return BUCKET_VOID
    return BUCKET_UNPLAYED


def is_finished_status(status):
    return status_bucket(status) == BUCKET_FINISHED


def is_live_play_status(status):
    return status_bucket(status) == BUCKET_LIVE


def score_is_clickable(status):
    value = normalize_status(status)
    if value in ABANDONED_STATUSES:
        return True
    return status_bucket(status) in (BUCKET_LIVE, BUCKET_FINISHED)


def badge_label(status):
    value = normalize_status(status)
    return value or 'UNKNOWN'


def _is_numeric_score(val):
    if val is None:
        return False
    try:
        if val != val:
            return False
    except Exception:
        pass
    text = str(val).strip()
    if not text or text.lower() in ('nan', 'none', '-', '—', 'vs'):
        return False
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def format_score_display(status, home_score=None, away_score=None):
    if not score_is_clickable(status):
        return SCORE_EM_DASH
    if _is_numeric_score(home_score) and _is_numeric_score(away_score):
        return f"{home_score} : {away_score}"
    return SCORE_VS
