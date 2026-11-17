# -*- coding: utf-8 -*-
"""Environment for the gate. Values are read once per process."""
import os
from pathlib import Path

from dotenv import load_dotenv

from auth.policy import LOCKED_ADMIN, normalize_email

ROOT = Path(__file__).resolve().parents[1]
DEV_SESSION_SECRET = 'dev-only-not-for-fly'
_config = None


class Config:
    def __init__(self, session_secret, public_base_url, https_only, bootstrap, db_path, fly):
        self.session_secret = session_secret
        self.public_base_url = public_base_url
        self.https_only = https_only
        self.bootstrap = bootstrap
        self.db_path = db_path
        self.fly = fly


def _bootstrap(raw):
    found = {LOCKED_ADMIN}
    for part in (raw or '').split(','):
        norm = normalize_email(part)
        if norm:
            found.add(norm)
    return frozenset(found)


def _read():
    load_dotenv(ROOT / '.env')
    fly = bool(os.environ.get('FLY_APP_NAME'))
    secret = os.environ.get('SESSION_SECRET', '').strip()
    if fly and not secret:
        raise SystemExit('Refusing to start: SESSION_SECRET is required')
    if not secret:
        secret = DEV_SESSION_SECRET
    public = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    if not public:
        public = 'https://splashboard.fly.dev' if fly else 'http://localhost:8050'
    explicit = os.environ.get('AUTH_DB_PATH', '').strip()
    if explicit:
        db_path = explicit
    elif fly:
        db_path = '/data/auth.db'
    else:
        db_path = None
    return Config(
        secret,
        public,
        public.startswith('https://'),
        _bootstrap(os.environ.get('AUTH_BOOTSTRAP_ADMINS', '')),
        db_path,
        fly,
    )


def load_config():
    global _config
    if _config is None:
        _config = _read()
    return _config


def local_db_path():
    return str(ROOT / '.auth' / 'auth.db')


def prepare_storage():
    """Create tables when Fly or AUTH_DB_PATH is set. Other imports stay lazy."""
    cfg = load_config()
    if cfg.fly:
        if not os.path.ismount('/data'):
            raise SystemExit('Refusing to start: /data is not mounted')
        if cfg.session_secret == DEV_SESSION_SECRET:
            raise SystemExit('Refusing to start: SESSION_SECRET is required')
        from auth.store import get_store
        get_store().init()
        return
    if os.environ.get('AUTH_DB_PATH', '').strip():
        from auth.store import get_store
        get_store().init()
