# -*- coding: utf-8 -*-
"""Sqlite allowlist, admin audit, and login log. One connection per call."""
import os
import sqlite3
import time

from auth.config import load_config, local_db_path
from auth.policy import ROLES, is_permanent_admin, normalize_email

_SCHEMA = (
    '''
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        role TEXT NOT NULL CHECK (role IN ('member', 'admin')),
        created_at INTEGER NOT NULL
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS admin_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at INTEGER NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT NOT NULL
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS login_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at INTEGER NOT NULL,
        email TEXT NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('ok', 'denied'))
    )
    ''',
)

_store = None


class StoreUnavailable(Exception):
    pass


class Store:
    def __init__(self, path, bootstrap):
        self.path = path
        self.bootstrap = frozenset(bootstrap or ())
        self._ready = False

    def init(self):
        if self._ready:
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = self._open()
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            for statement in _SCHEMA:
                conn.execute(statement)
            conn.execute('BEGIN IMMEDIATE')
            now = int(time.time())
            for email in sorted(self.bootstrap):
                conn.execute(
                    '''
                    INSERT INTO users (email, role, created_at) VALUES (?, 'admin', ?)
                    ON CONFLICT(email) DO UPDATE SET role='admin'
                    ''',
                    (email, now),
                )
            conn.execute('COMMIT')
        except sqlite3.Error as exc:
            try:
                conn.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            raise StoreUnavailable from exc
        finally:
            conn.close()
        self._ready = True

    def _open(self):
        try:
            conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        except sqlite3.Error as exc:
            raise StoreUnavailable from exc
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA busy_timeout=5000')
        except sqlite3.Error as exc:
            conn.close()
            raise StoreUnavailable from exc
        return conn

    def _connect(self):
        self.init()
        return self._open()

    def _immediate(self, fn):
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            result = fn(conn)
            conn.execute('COMMIT')
            return result
        except StoreUnavailable:
            try:
                conn.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            raise
        except sqlite3.Error as exc:
            try:
                conn.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            raise StoreUnavailable from exc
        finally:
            conn.close()

    def _query(self, sql, params=()):
        conn = self._connect()
        try:
            return list(conn.execute(sql, params))
        except sqlite3.Error as exc:
            raise StoreUnavailable from exc
        finally:
            conn.close()

    def role_for(self, email):
        norm = normalize_email(email)
        if norm is None:
            return None
        rows = self._query('SELECT role FROM users WHERE email = ?', (norm,))
        if is_permanent_admin(norm, self.bootstrap):
            return 'admin'
        if not rows:
            return None
        role = rows[0]['role']
        if role not in ROLES:
            return None
        return role

    def record_login(self, email, result):
        norm = normalize_email(email)
        if norm is None or result not in ('ok', 'denied'):
            return

        def run(conn):
            conn.execute(
                'INSERT INTO login_events (at, email, result) VALUES (?, ?, ?)',
                (int(time.time()), norm, result),
            )

        self._immediate(run)

    def add_user(self, actor, email, role):
        norm = normalize_email(email)
        if norm is None or role not in ROLES:
            return 'invalid'
        if is_permanent_admin(norm, self.bootstrap) and role != 'admin':
            return 'locked'

        def run(conn):
            row = conn.execute('SELECT role FROM users WHERE email = ?', (norm,)).fetchone()
            if row is not None and (row['role'] == role or is_permanent_admin(norm, self.bootstrap)):
                return 'exists'
            now = int(time.time())
            if row is None:
                conn.execute(
                    'INSERT INTO users (email, role, created_at) VALUES (?, ?, ?)',
                    (norm, role, now),
                )
                action = 'add'
                code = 'added'
            else:
                conn.execute('UPDATE users SET role = ? WHERE email = ?', (role, norm))
                action = 'set_role'
                code = 'updated'
            conn.execute(
                'INSERT INTO admin_changes (at, actor, action, target) VALUES (?, ?, ?, ?)',
                (now, actor, action, norm),
            )
            return code

        return self._immediate(run)

    def set_role(self, actor, email, role):
        norm = normalize_email(email)
        if norm is None or role not in ROLES:
            return 'invalid'
        if is_permanent_admin(norm, self.bootstrap) and role != 'admin':
            return 'locked'

        def run(conn):
            row = conn.execute('SELECT role FROM users WHERE email = ?', (norm,)).fetchone()
            if row is None:
                return 'missing'
            if row['role'] == role or is_permanent_admin(norm, self.bootstrap):
                return 'exists'
            now = int(time.time())
            conn.execute('UPDATE users SET role = ? WHERE email = ?', (role, norm))
            conn.execute(
                'INSERT INTO admin_changes (at, actor, action, target) VALUES (?, ?, ?, ?)',
                (now, actor, 'set_role', norm),
            )
            return 'updated'

        return self._immediate(run)

    def remove_user(self, actor, email):
        norm = normalize_email(email)
        if norm is None:
            return 'invalid'
        if is_permanent_admin(norm, self.bootstrap):
            return 'locked'

        def run(conn):
            row = conn.execute('SELECT role FROM users WHERE email = ?', (norm,)).fetchone()
            if row is None:
                return 'missing'
            now = int(time.time())
            conn.execute('DELETE FROM users WHERE email = ?', (norm,))
            conn.execute(
                'INSERT INTO admin_changes (at, actor, action, target) VALUES (?, ?, ?, ?)',
                (now, actor, 'remove', norm),
            )
            return 'removed'

        return self._immediate(run)

    def list_users(self):
        rows = self._query(
            'SELECT email, role, created_at FROM users ORDER BY email COLLATE NOCASE'
        )
        return [
            {'email': row['email'], 'role': row['role'], 'created_at': row['created_at']}
            for row in rows
        ]

    def list_changes(self, limit=100):
        rows = self._query(
            '''
            SELECT at, actor, action, target FROM admin_changes
            ORDER BY at DESC, id DESC LIMIT ?
            ''',
            (int(limit),),
        )
        return [
            {
                'at': row['at'],
                'actor': row['actor'],
                'action': row['action'],
                'target': row['target'],
            }
            for row in rows
        ]

    def list_logins(self, limit=100):
        rows = self._query(
            '''
            SELECT at, email, result FROM login_events
            ORDER BY at DESC, id DESC LIMIT ?
            ''',
            (int(limit),),
        )
        return [
            {'at': row['at'], 'email': row['email'], 'result': row['result']}
            for row in rows
        ]


def connect_path(path, bootstrap=None):
    """Point this process at `path` and create tables."""
    global _store
    emails = load_config().bootstrap if bootstrap is None else frozenset(bootstrap)
    _store = Store(path, emails)
    _store.init()
    return _store


def get_store():
    global _store
    if _store is None:
        cfg = load_config()
        _store = Store(cfg.db_path or local_db_path(), cfg.bootstrap)
    return _store
