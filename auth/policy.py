# -*- coding: utf-8 -*-
"""Pure allowlist rules. No Dash, FastAPI, Authlib, sqlite, or itsdangerous."""
from urllib.parse import unquote, urlsplit

LOCKED_ADMIN = 'linweihao.tw@gmail.com'
ROLES = ('member', 'admin')
SESSION_MAX_AGE = 7 * 24 * 60 * 60
_SKEW_SECONDS = 60


def normalize_email(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text or '@' not in text:
        return None
    if any(ord(ch) < 33 for ch in text):
        return None
    if text.count('@') != 1:
        return None
    local, domain = text.split('@')
    if not local or not domain:
        return None
    if '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        return None
    return text


def is_permanent_admin(email, bootstrap):
    norm = normalize_email(email)
    if norm is None:
        return False
    if norm == LOCKED_ADMIN:
        return True
    return norm in (bootstrap or ())


def session_expired(issued_at, now):
    if isinstance(issued_at, bool) or not isinstance(issued_at, int):
        return True
    if isinstance(now, bool) or not isinstance(now, (int, float)):
        return True
    now_i = int(now)
    if issued_at > now_i + _SKEW_SECONDS:
        return True
    return (now_i - issued_at) >= SESSION_MAX_AGE


def validate_next(value):
    """Same-site path only. Reject scheme, host, //, backslash, controls, . and .."""
    if not isinstance(value, str) or value == '':
        return None
    if '\\' in value or any(ord(ch) < 0x20 for ch in value):
        return None
    decoded = unquote(value)
    if '\\' in decoded or any(ord(ch) < 0x20 for ch in decoded):
        return None
    if not decoded.startswith('/') or decoded.startswith('//'):
        return None
    parts = urlsplit(decoded)
    if parts.scheme or parts.netloc:
        return None
    path = parts.path
    if not path.startswith('/') or ':' in path:
        return None
    segments = path.split('/')
    if any(segment in ('.', '..') for segment in segments):
        return None
    if len(segments) > 1 and segments[1] in ('login', 'auth'):
        return None
    query = ('?' + parts.query) if parts.query else ''
    return path + query
