# -*- coding: utf-8 -*-
"""Pure ASGI gate. Public paths are an allowlist. Everything else needs a session."""
import json
import time
from urllib.parse import quote

from auth.current import Principal, reset, set_principal
from auth.policy import normalize_email, session_expired
from auth.store import StoreUnavailable, get_store

_PUBLIC_EXACT = frozenset({
    '/login',
    '/auth/callback',
    '/logout',
    '/_favicon.ico',
})


def is_public_path(path):
    if not isinstance(path, str) or not path.startswith('/'):
        return False
    segments = path.split('/')
    if any(segment in ('.', '..') for segment in segments):
        return False
    if path in _PUBLIC_EXACT:
        return True
    if path.startswith('/assets/'):
        return True
    if path.startswith('/_dash-component-suites/'):
        return True
    return False


def is_dash_api(path):
    if not isinstance(path, str) or not path.startswith('/_dash-'):
        return False
    return not path.startswith('/_dash-component-suites/')


class AuthGate:
    def __init__(self, app, store_getter=None, now=None):
        self.app = app
        self.store_getter = store_getter or get_store
        self.now = now or time.time

    async def __call__(self, scope, receive, send):
        kind = scope.get('type')
        if kind not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return
        if kind == 'websocket':
            await self._websocket(scope, receive, send)
            return
        await self._http(scope, receive, send)

    def _lookup(self, session):
        """Return a principal. Clear the session only when an email is present and rejected."""
        if session is None or not hasattr(session, 'get'):
            return None
        raw = session.get('email')
        if not isinstance(raw, str) or raw == '':
            return None
        email = normalize_email(raw)
        issued = session.get('issued_at')
        if email is None or session_expired(issued, self.now()):
            session.clear()
            return None
        role = self.store_getter().role_for(email)
        if role is None:
            session.clear()
            return None
        return Principal(email, role, int(issued))

    async def _http(self, scope, receive, send):
        path = scope.get('path') or '/'
        method = str(scope.get('method') or 'GET').upper()
        session = scope.get('session')
        principal = None
        unavailable = False
        try:
            principal = self._lookup(session)
        except StoreUnavailable:
            unavailable = True
            principal = None
        token = set_principal(principal)
        try:
            if unavailable:
                await _json(send, 503, {'error': 'unavailable'})
                return
            if is_public_path(path):
                await self.app(scope, receive, send)
                return
            if principal is None:
                if is_dash_api(path) or method != 'GET':
                    await _json(send, 401, {'error': 'auth'})
                    return
                await _redirect(send, _login_location(scope))
                return
            await self.app(scope, receive, _nostore(send))
        finally:
            reset(token)

    async def _websocket(self, scope, receive, send):
        session = scope.get('session')
        principal = None
        unavailable = False
        try:
            principal = self._lookup(session)
        except StoreUnavailable:
            unavailable = True
        if unavailable or principal is None:
            await _close_websocket(receive, send, 4503 if unavailable else 4401)
            return
        token = set_principal(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            reset(token)


def _login_location(scope):
    path = scope.get('path') or '/'
    raw_query = scope.get('query_string') or b''
    if isinstance(raw_query, bytes):
        query = raw_query.decode('latin-1')
    else:
        query = str(raw_query)
    target = path + (('?' + query) if query else '')
    return '/login?next=' + quote(target, safe='')


def _nostore(send):
    async def wrapper(message):
        if message.get('type') == 'http.response.start':
            headers = []
            replaced = False
            for key, value in message.get('headers') or []:
                if key.lower() == b'cache-control':
                    headers.append((b'cache-control', b'no-store'))
                    replaced = True
                else:
                    headers.append((key, value))
            if not replaced:
                headers.append((b'cache-control', b'no-store'))
            message = dict(message)
            message['headers'] = headers
        await send(message)
    return wrapper


async def _json(send, status, payload):
    body = json.dumps(payload).encode('utf-8')
    await send({
        'type': 'http.response.start',
        'status': status,
        'headers': [
            (b'content-type', b'application/json'),
            (b'cache-control', b'no-store'),
            (b'content-length', str(len(body)).encode('ascii')),
        ],
    })
    await send({'type': 'http.response.body', 'body': body})


async def _redirect(send, location):
    await send({
        'type': 'http.response.start',
        'status': 303,
        'headers': [
            (b'location', location.encode('ascii')),
            (b'cache-control', b'no-store'),
            (b'content-length', b'0'),
        ],
    })
    await send({'type': 'http.response.body', 'body': b''})


async def _close_websocket(receive, send, code):
    while True:
        message = await receive()
        if message.get('type') == 'websocket.connect':
            await send({'type': 'websocket.close', 'code': code})
            return
        if message.get('type') == 'websocket.disconnect':
            return
