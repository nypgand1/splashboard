# -*- coding: utf-8 -*-
import unittest

from auth.policy import (
    LOCKED_ADMIN,
    ROLES,
    SESSION_MAX_AGE,
    is_permanent_admin,
    normalize_email,
    session_expired,
    validate_next,
)


class AuthPolicyTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(LOCKED_ADMIN, 'linweihao.tw@gmail.com')
        self.assertEqual(ROLES, ('member', 'admin'))
        self.assertEqual(SESSION_MAX_AGE, 7 * 24 * 60 * 60)

    def test_normalize_email_valid(self):
        self.assertEqual(normalize_email('  User@Example.COM  '), 'user@example.com')
        self.assertEqual(normalize_email('linweihao.tw@gmail.com'), LOCKED_ADMIN)

    def test_normalize_email_invalid(self):
        bad_values = [
            None,
            123,
            ['a@b.com'],
            '',
            '   ',
            'noatsign.com',
            'a@b@c.com',
            '@example.com',
            'user@',
            'user@localhost',
            'user@.example.com',
            'user@example.com.',
            'us er@example.com',
            'user@exa\nmple.com',
            'user\x00@example.com',
        ]
        for value in bad_values:
            with self.subTest(value=value):
                self.assertIsNone(normalize_email(value))

    def test_is_permanent_admin(self):
        self.assertTrue(is_permanent_admin(LOCKED_ADMIN, ()))
        self.assertTrue(is_permanent_admin('  LinWeiHao.TW@Gmail.COM ', ()))
        self.assertTrue(is_permanent_admin('extra@example.com', {'extra@example.com'}))
        self.assertFalse(is_permanent_admin('member@example.com', {'extra@example.com'}))
        self.assertFalse(is_permanent_admin('not-an-email', {'extra@example.com'}))

    def test_session_expired(self):
        now = 1_700_000_000
        self.assertFalse(session_expired(now, now))
        self.assertFalse(session_expired(now - (SESSION_MAX_AGE - 1), now))
        self.assertTrue(session_expired(now - SESSION_MAX_AGE, now))
        self.assertTrue(session_expired(now - SESSION_MAX_AGE - 1, now))

        self.assertFalse(session_expired(now + 60, now))
        self.assertTrue(session_expired(now + 61, now))

        for bad_issued in (True, False, None, '1700000000', 1700000000.5):
            with self.subTest(issued_at=bad_issued):
                self.assertTrue(session_expired(bad_issued, now))

        for bad_now in (True, False, None, '1700000000'):
            with self.subTest(now=bad_now):
                self.assertTrue(session_expired(now, bad_now))

    def test_validate_next_allows_same_site_paths(self):
        cases = [
            ('/', '/'),
            ('/?q=1', '/?q=1'),
            ('/team-stats', '/team-stats'),
            ('/game/plg/x?tab=1', '/game/plg/x?tab=1'),
            ('/authenticate', '/authenticate'),
            ('/team-stats?a=1#section', '/team-stats?a=1'),
            ('/#top', '/'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(validate_next(raw), expected)

    def test_validate_next_rejects_unsafe_or_auth_paths(self):
        bad = [
            '',
            None,
            123,
            'team-stats',
            'https://evil.example',
            '//evil.example',
            '/\\evil.example',
            '/%5Cevil.example',
            '/%09/evil.example',
            '/foo/../bar',
            '/foo/%2e%2e/bar',
            '/foo/./bar',
            '/.',
            '/foo:bar',
            '/login',
            '/login?next=/',
            '/auth/callback',
            '/auth/callback?code=1',
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                self.assertIsNone(validate_next(raw))


if __name__ == '__main__':
    unittest.main()
