# -*- coding: utf-8 -*-
import os
import tempfile
import time
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch
from urllib.parse import urlsplit

from authlib.integrations.base_client.errors import OAuthError
from starlette.testclient import TestClient

import app
from auth.config import load_config
from auth.cookie import COOKIE_NAME, read_session, sign_session
from auth.policy import LOCKED_ADMIN
from auth.store import connect_path


class AuthRoutesTests(unittest.TestCase):
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

    def _extract_session_cookie(self, resp):
        jar = SimpleCookie()
        jar.load(resp.headers.get('set-cookie', ''))
        morsel = jar.get(COOKIE_NAME)
        return read_session(morsel.value, self.secret) if morsel else None

    def test_get_login_redirects_wrong_host_to_public_base_url(self):
        parsed = urlsplit(self.base_url)
        other_host = 'http://127.0.0.1:8050' if parsed.netloc != '127.0.0.1:8050' else 'http://localhost:8050'
        with TestClient(app.server, base_url=other_host, follow_redirects=False) as client:
            resp = client.get('/login?next=%2Fteam-stats')
            self.assertEqual(resp.status_code, 303)
            self.assertEqual(resp.headers.get('location'), self.base_url + '/login?next=%2Fteam-stats')

    def test_get_login_anonymous_renders_html_without_setting_cookie(self):
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            resp = client.get('/login')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get('cache-control'), 'no-store')
            self.assertIn('Continue with Google', resp.text)
            self.assertNotIn(COOKIE_NAME, resp.headers.get('set-cookie', ''))

    def test_get_login_signed_in_redirects_to_valid_next_or_root(self):
        cookie = self._cookie_for({
            'email': LOCKED_ADMIN,
            'role': 'admin',
            'issued_at': int(time.time()),
        })
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            client.cookies.set(COOKIE_NAME, cookie)
            resp = client.get('/login?next=%2Fteam-stats')
            self.assertEqual(resp.status_code, 303)
            self.assertEqual(resp.headers.get('location'), '/team-stats')

            bad_next = client.get('/login?next=//evil.example')
            self.assertEqual(bad_next.status_code, 303)
            self.assertEqual(bad_next.headers.get('location'), '/')

    def test_post_login_without_google_client_returns_503(self):
        with patch('auth.routes.oauth_client', return_value=None):
            with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
                resp = client.post('/login', data={'next': '/team-stats'})
                self.assertEqual(resp.status_code, 503)
                self.assertIn('Sign-in is unavailable. Try again later.', resp.text)

    def test_logout_get_returns_405_and_post_clears_cookie(self):
        cookie = self._cookie_for({
            'email': LOCKED_ADMIN,
            'role': 'admin',
            'issued_at': int(time.time()),
        })
        with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
            client.cookies.set(COOKIE_NAME, cookie)
            get_resp = client.get('/logout')
            self.assertEqual(get_resp.status_code, 405)
            self.assertEqual(get_resp.headers.get('cache-control'), 'no-store')
            self.assertNotIn(COOKIE_NAME, get_resp.headers.get('set-cookie', ''))

            post_resp = client.post('/logout')
            self.assertEqual(post_resp.status_code, 303)
            self.assertEqual(post_resp.headers.get('location'), '/login')
            self.assertEqual(post_resp.headers.get('cache-control'), 'no-store')
            set_cookie = post_resp.headers.get('set-cookie', '').lower()
            self.assertIn(COOKIE_NAME, set_cookie)
            self.assertTrue('max-age=0' in set_cookie or f'{COOKIE_NAME}=null' in set_cookie)

    def test_callback_unverified_email_returns_400_and_logs_nothing(self):
        class FakeClient:
            async def authorize_access_token(self, _request):
                return {'userinfo': {'email': LOCKED_ADMIN, 'email_verified': False}}

        with patch('auth.routes.oauth_client', return_value=FakeClient()):
            with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
                resp = client.get('/auth/callback')
                self.assertEqual(resp.status_code, 400)
                self.assertIn('This Google account has not verified its email.', resp.text)
                self.assertEqual(self.store.list_logins(), [])

    def test_callback_not_on_list_returns_403_and_logs_denied(self):
        class FakeClient:
            async def authorize_access_token(self, _request):
                return {'userinfo': {'email': '  Stranger@Example.com ', 'email_verified': True}}

        with patch('auth.routes.oauth_client', return_value=FakeClient()):
            with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
                resp = client.get('/auth/callback')
                self.assertEqual(resp.status_code, 403)
                self.assertIn('This Google account is not on the list. Ask an admin to add it.', resp.text)
                logins = self.store.list_logins()
                self.assertEqual(len(logins), 1)
                self.assertEqual(logins[0]['email'], 'stranger@example.com')
                self.assertEqual(logins[0]['result'], 'denied')

    def test_callback_success_sets_session_logs_ok_and_redirects_to_next(self):
        self.store.add_user(LOCKED_ADMIN, 'member@example.com', 'member')

        class FakeClient:
            async def authorize_access_token(self, _request):
                return {'userinfo': {'email': '  Member@Example.com ', 'email_verified': True}}

        with patch('auth.routes.oauth_client', return_value=FakeClient()):
            with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
                client.cookies.set(COOKIE_NAME, self._cookie_for({'next': '/team-stats'}))
                resp = client.get('/auth/callback')
                self.assertEqual(resp.status_code, 303)
                self.assertEqual(resp.headers.get('location'), '/team-stats')
                session = self._extract_session_cookie(resp)
                self.assertIsNotNone(session)
                self.assertEqual(session['email'], 'member@example.com')
                self.assertEqual(session['role'], 'member')
                self.assertIsInstance(session['issued_at'], int)

                logins = self.store.list_logins()
                self.assertEqual(len(logins), 1)
                self.assertEqual(logins[0]['email'], 'member@example.com')
                self.assertEqual(logins[0]['result'], 'ok')

    def test_callback_oauth_access_denied_returns_400_and_logs_nothing(self):
        class FakeClient:
            async def authorize_access_token(self, _request):
                raise OAuthError(error='access_denied')

        with patch('auth.routes.oauth_client', return_value=FakeClient()):
            with TestClient(app.server, base_url=self.base_url, follow_redirects=False) as client:
                resp = client.get('/auth/callback')
                self.assertEqual(resp.status_code, 400)
                self.assertIn('Google sign-in was cancelled.', resp.text)
                self.assertEqual(self.store.list_logins(), [])


if __name__ == '__main__':
    unittest.main()
