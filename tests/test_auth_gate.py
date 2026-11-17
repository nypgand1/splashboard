# -*- coding: utf-8 -*-
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app
from auth.config import load_config
from auth.cookie import COOKIE_NAME, read_session, sign_session
from auth.current import Principal, reset, set_principal
from auth.gate import is_public_path
from auth.policy import LOCKED_ADMIN, SESSION_MAX_AGE
from auth.store import StoreUnavailable, connect_path
from pages import admin as admin_page
from ui.components import to_jsonable


def _serialize(node):
    return json.dumps(to_jsonable(node))


class AuthGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, 'auth.db')
        self.store = connect_path(self.db_path, bootstrap={LOCKED_ADMIN})
        self.cfg = load_config()
        self.secret = self.cfg.session_secret
        self.base_url = self.cfg.public_base_url

    def tearDown(self):
        self._tmp.cleanup()

    def _cookie_for(self, payload):
        return sign_session(payload, self.secret)

    def test_cookie_roundtrip_and_rejects_bad_signatures(self):
        payload = {'email': LOCKED_ADMIN, 'role': 'admin', 'issued_at': int(time.time())}
        signed = sign_session(payload, self.secret)
        self.assertEqual(read_session(signed, self.secret), payload)
        self.assertIsNone(read_session(signed, 'wrong-secret'))
        self.assertIsNone(read_session('', self.secret))
        self.assertIsNone(read_session(None, self.secret))

    def test_public_path_allowlist(self):
        for path in (
            '/login',
            '/auth/callback',
            '/logout',
            '/_favicon.ico',
            '/assets/app.css',
            '/_dash-component-suites/dash/deps.js',
        ):
            with self.subTest(public=path):
                self.assertTrue(is_public_path(path))

        for path in (
            '/',
            '/team-stats',
            '/admin',
            '/assets',
            '/assets-extra/a.css',
            '/docs',
            '/redoc',
            '/openapi.json',
            '/_reload-hash',
            '/_dash-layout',
            '/_dash-dependencies',
            '/assets/../secret',
            '/login/../admin',
        ):
            with self.subTest(private=path):
                self.assertFalse(is_public_path(path))

    def test_anonymous_http_gate(self):
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            for path, expected_loc in (
                ('/', '/login?next=%2F'),
                ('/team-stats?a=1', '/login?next=%2Fteam-stats%3Fa%3D1'),
                ('/docs', '/login?next=%2Fdocs'),
                ('/redoc', '/login?next=%2Fredoc'),
                ('/openapi.json', '/login?next=%2Fopenapi.json'),
                ('/_reload-hash', '/login?next=%2F_reload-hash'),
            ):
                with self.subTest(path=path):
                    resp = client.get(path)
                    self.assertEqual(resp.status_code, 303)
                    self.assertEqual(resp.headers.get('location'), expected_loc)
                    self.assertEqual(resp.headers.get('cache-control'), 'no-store')

            for api_path in ('/_dash-layout', '/_dash-dependencies'):
                with self.subTest(api_path=api_path):
                    resp = client.get(api_path)
                    self.assertEqual(resp.status_code, 401)
                    self.assertEqual(resp.json(), {'error': 'auth'})
                    self.assertEqual(resp.headers.get('cache-control'), 'no-store')

            post_resp = client.post('/_dash-update-component', json={})
            self.assertEqual(post_resp.status_code, 401)
            self.assertEqual(post_resp.json(), {'error': 'auth'})
            self.assertEqual(post_resp.headers.get('cache-control'), 'no-store')

            asset_resp = client.get('/assets/app.css')
            self.assertEqual(asset_resp.status_code, 200)

    def test_session_without_email_stays_anonymous_and_is_not_cleared(self):
        cookie = self._cookie_for({'next': '/team-stats'})
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            client.cookies.set(COOKIE_NAME, cookie)
            resp = client.get('/')
            self.assertEqual(resp.status_code, 303)
            self.assertEqual(resp.headers.get('location'), '/login?next=%2F')
            self.assertNotIn(COOKIE_NAME, resp.headers.get('set-cookie', ''))

    def test_expired_or_unallowlisted_email_session_is_cleared(self):
        now = int(time.time())
        cases = [
            ('expired_exact', {'email': LOCKED_ADMIN, 'role': 'admin', 'issued_at': now - SESSION_MAX_AGE}),
            ('bool_issued_at', {'email': LOCKED_ADMIN, 'role': 'admin', 'issued_at': True}),
            ('future_issued_at', {'email': LOCKED_ADMIN, 'role': 'admin', 'issued_at': now + 120}),
            ('bad_email', {'email': 'not-an-email', 'role': 'admin', 'issued_at': now}),
            ('not_in_sqlite', {'email': 'stranger@example.com', 'role': 'member', 'issued_at': now}),
        ]
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            for label, payload in cases:
                with self.subTest(case=label):
                    client.cookies.clear()
                    client.cookies.set(COOKIE_NAME, self._cookie_for(payload))
                    resp = client.get('/_dash-layout')
                    self.assertEqual(resp.status_code, 401)
                    self.assertEqual(resp.json(), {'error': 'auth'})
                    set_cookie = resp.headers.get('set-cookie', '').lower()
                    self.assertIn(COOKIE_NAME, set_cookie)
                    self.assertTrue('max-age=0' in set_cookie or f'{COOKIE_NAME}=null' in set_cookie)

    def test_sqlite_role_wins_over_cookie_role_without_rewriting_cookie(self):
        self.store.add_user(LOCKED_ADMIN, 'member@example.com', 'member')
        cookie = self._cookie_for({
            'email': 'member@example.com',
            'role': 'admin',
            'issued_at': int(time.time()),
        })
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            client.cookies.set(COOKIE_NAME, cookie)
            resp = client.get('/_dash-layout')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get('cache-control'), 'no-store')
            self.assertNotIn(COOKIE_NAME, resp.headers.get('set-cookie', ''))
            body = resp.text
            self.assertIn('member@example.com', body)
            self.assertIn('Logout', body)
            self.assertNotIn('/admin', body)

    def test_admin_dash_layout_shows_account_menu(self):
        cookie = self._cookie_for({
            'email': LOCKED_ADMIN,
            'role': 'admin',
            'issued_at': int(time.time()),
        })
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            client.cookies.set(COOKIE_NAME, cookie)
            resp = client.get('/_dash-layout')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get('cache-control'), 'no-store')
            body = resp.text
            self.assertIn(LOCKED_ADMIN, body)
            self.assertIn('Account', body)
            self.assertIn('Admin', body)
            self.assertIn('Logout', body)

    def test_unauthenticated_websocket_closes_with_4401(self):
        with TestClient(app.server, base_url=self.base_url) as client:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with client.websocket_connect('/_dash-ws-callback'):
                    pass
            self.assertEqual(ctx.exception.code, 4401)

    def test_store_unavailable_returns_503_and_closes_ws_4503(self):
        cookie = self._cookie_for({
            'email': LOCKED_ADMIN,
            'role': 'admin',
            'issued_at': int(time.time()),
        })
        with patch.object(self.store, 'role_for', side_effect=StoreUnavailable('down')):
            with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
                client.cookies.set(COOKIE_NAME, cookie)
                resp = client.get('/')
                self.assertEqual(resp.status_code, 503)
                self.assertEqual(resp.json(), {'error': 'unavailable'})

                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with client.websocket_connect('/_dash-ws-callback'):
                        pass
                self.assertEqual(ctx.exception.code, 4503)

    def test_admin_page_layout_access_control(self):
        self.store.add_user(LOCKED_ADMIN, 'member@example.com', 'member')
        now = int(time.time())

        token = set_principal(Principal('member@example.com', 'member', now))
        try:
            member_text = _serialize(admin_page.layout())
        finally:
            reset(token)
        self.assertIn("You don't have access to this page.", member_text)
        self.assertNotIn('Allowlist', member_text)

        token = set_principal(Principal(LOCKED_ADMIN, 'admin', now))
        try:
            admin_text = _serialize(admin_page.layout())
        finally:
            reset(token)
        self.assertIn('Allowlist', admin_text)
        self.assertNotIn("You don't have access to this page.", admin_text)


if __name__ == '__main__':
    unittest.main()
