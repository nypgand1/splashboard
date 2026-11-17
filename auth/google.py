# -*- coding: utf-8 -*-
"""Google OIDC. Import succeeds when the client id is unset; login reports that."""
import os

_oauth = None


def oauth_client():
    global _oauth
    client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
    if not client_id or not client_secret:
        return None
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        oauth.register(
            name='google',
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
        _oauth = oauth
    return _oauth.google
