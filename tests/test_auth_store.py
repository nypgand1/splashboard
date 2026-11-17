# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from auth.policy import LOCKED_ADMIN
from auth.store import Store, StoreUnavailable, connect_path


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, 'auth.db')
        self.store = connect_path(self.db_path, bootstrap={LOCKED_ADMIN})

    def tearDown(self):
        self._tmp.cleanup()

    def test_seeds_locked_admin(self):
        self.assertEqual(self.store.role_for(LOCKED_ADMIN), 'admin')
        users = self.store.list_users()
        self.assertEqual([u['email'] for u in users], [LOCKED_ADMIN])
        self.assertEqual(users[0]['role'], 'admin')

    def test_bootstrap_includes_extra_permanent_admin(self):
        extra_path = os.path.join(self._tmp.name, 'extra.db')
        store = connect_path(extra_path, bootstrap={LOCKED_ADMIN, 'extra@example.com'})
        self.assertEqual(store.role_for(LOCKED_ADMIN), 'admin')
        self.assertEqual(store.role_for('extra@example.com'), 'admin')
        self.assertEqual(store.remove_user(LOCKED_ADMIN, 'extra@example.com'), 'locked')
        self.assertEqual(store.set_role(LOCKED_ADMIN, 'extra@example.com', 'member'), 'locked')

    def test_add_set_role_and_remove_user(self):
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, '  Alice@Example.com ', 'member'), 'added')
        self.assertEqual(self.store.role_for('alice@example.com'), 'member')
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, 'alice@example.com', 'member'), 'exists')
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, 'alice@example.com', 'admin'), 'updated')
        self.assertEqual(self.store.role_for('alice@example.com'), 'admin')

        self.assertEqual(self.store.set_role(LOCKED_ADMIN, 'alice@example.com', 'admin'), 'exists')
        self.assertEqual(self.store.set_role(LOCKED_ADMIN, 'alice@example.com', 'member'), 'updated')
        self.assertEqual(self.store.role_for('alice@example.com'), 'member')
        self.assertEqual(self.store.set_role(LOCKED_ADMIN, 'nobody@example.com', 'member'), 'missing')

        self.assertEqual(self.store.remove_user(LOCKED_ADMIN, 'alice@example.com'), 'removed')
        self.assertIsNone(self.store.role_for('alice@example.com'))
        self.assertEqual(self.store.remove_user(LOCKED_ADMIN, 'alice@example.com'), 'missing')

        changes = self.store.list_changes()
        actions = [c['action'] for c in changes]
        self.assertEqual(actions, ['remove', 'set_role', 'set_role', 'add'])
        self.assertTrue(all(c['target'] == 'alice@example.com' for c in changes))

    def test_permanent_admin_cannot_be_removed_or_demoted(self):
        self.assertEqual(self.store.remove_user(LOCKED_ADMIN, LOCKED_ADMIN), 'locked')
        self.assertEqual(self.store.set_role(LOCKED_ADMIN, LOCKED_ADMIN, 'member'), 'locked')
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, LOCKED_ADMIN, 'member'), 'locked')
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, LOCKED_ADMIN, 'admin'), 'exists')
        self.assertEqual(self.store.role_for(LOCKED_ADMIN), 'admin')

    def test_invalid_inputs_rejected(self):
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, 'bad-email', 'member'), 'invalid')
        self.assertEqual(self.store.add_user(LOCKED_ADMIN, 'bob@example.com', 'owner'), 'invalid')
        self.assertEqual(self.store.set_role(LOCKED_ADMIN, 'bad-email', 'member'), 'invalid')
        self.assertEqual(self.store.set_role(LOCKED_ADMIN, 'bob@example.com', 'owner'), 'invalid')
        self.assertEqual(self.store.remove_user(LOCKED_ADMIN, 'bad-email'), 'invalid')
        self.assertIsNone(self.store.role_for('bad-email'))

    def test_record_login_and_list_logins(self):
        self.store.record_login('  Bob@Example.com ', 'ok')
        self.store.record_login('stranger@example.com', 'denied')
        self.store.record_login('bad-email', 'ok')
        self.store.record_login('bob@example.com', 'unknown')

        logins = self.store.list_logins()
        self.assertEqual(len(logins), 2)
        self.assertEqual(logins[0]['email'], 'stranger@example.com')
        self.assertEqual(logins[0]['result'], 'denied')
        self.assertEqual(logins[1]['email'], 'bob@example.com')
        self.assertEqual(logins[1]['result'], 'ok')
        self.assertEqual(len(self.store.list_logins(limit=1)), 1)

    def test_store_unavailable_on_bad_path(self):
        bad_store = Store(self._tmp.name, {LOCKED_ADMIN})
        with self.assertRaises(StoreUnavailable):
            bad_store.role_for(LOCKED_ADMIN)


if __name__ == '__main__':
    unittest.main()
