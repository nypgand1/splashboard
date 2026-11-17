# -*- coding: utf-8 -*-
"""Starlette session cookie bytes. Policy stays free of itsdangerous."""
import json
from base64 import b64decode, b64encode

import itsdangerous
from itsdangerous.exc import BadSignature

from auth.policy import SESSION_MAX_AGE

COOKIE_NAME = 'splashboard_session'


def sign_session(data, secret):
    raw = b64encode(json.dumps(data).encode('utf-8'))
    return itsdangerous.TimestampSigner(str(secret)).sign(raw).decode('utf-8')


def read_session(value, secret, max_age=SESSION_MAX_AGE):
    if not isinstance(value, str) or value == '':
        return None
    try:
        raw = itsdangerous.TimestampSigner(str(secret)).unsign(value, max_age=max_age)
    except BadSignature:
        return None
    try:
        data = json.loads(b64decode(raw))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data
