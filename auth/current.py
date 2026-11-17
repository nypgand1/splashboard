# -*- coding: utf-8 -*-
"""Request principal. Default is anonymous so layout can render outside a request."""
from contextvars import ContextVar

_principal = ContextVar('splashboard_principal', default=None)


class Principal:
    def __init__(self, email, role, issued_at):
        self.email = email
        self.role = role
        self.issued_at = issued_at


def get():
    return _principal.get()


def set_principal(value):
    return _principal.set(value)


def reset(token):
    _principal.reset(token)
