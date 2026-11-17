# -*- coding: utf-8 -*-
"""Login, Google callback, and logout. The Dash app does not own this flow."""
import time
from urllib.parse import urlsplit

from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from auth import login_html
from auth.config import load_config
from auth.current import get as current_principal
from auth.google import oauth_client
from auth.policy import validate_next
from auth.store import StoreUnavailable, get_store


def mount(app):
    cfg = load_config()

    @app.get('/login')
    async def login_get(request: Request):
        expected = urlsplit(cfg.public_base_url).netloc
        if request.url.netloc != expected:
            target = cfg.public_base_url + request.url.path
            if request.url.query:
                target += '?' + request.url.query
            return _redirect(target)
        principal = current_principal()
        nxt = validate_next(request.query_params.get('next', ''))
        if principal is not None:
            return _redirect(nxt or '/')
        return _html(login_html.form(nxt or ''))

    @app.post('/login')
    async def login_post(request: Request):
        form = await request.form()
        nxt = validate_next(str(form.get('next') or ''))
        if nxt:
            request.session['next'] = nxt
        elif 'next' in request.session:
            request.session.pop('next', None)
        client = oauth_client()
        if client is None:
            return _html(login_html.message(login_html.UNAVAILABLE), 503)
        redirect_uri = cfg.public_base_url + '/auth/callback'
        try:
            return await client.authorize_redirect(request, redirect_uri)
        except Exception as exc:
            from authlib.integrations.base_client.errors import OAuthError

            if isinstance(exc, OAuthError):
                return _oauth_failure(exc)
            return _html(login_html.message(login_html.UNAVAILABLE), 503)

    @app.get('/auth/callback')
    async def auth_callback(request: Request):
        from authlib.integrations.base_client.errors import OAuthError

        client = oauth_client()
        if client is None:
            return _html(login_html.message(login_html.UNAVAILABLE), 503)
        try:
            token = await client.authorize_access_token(request)
        except OAuthError as exc:
            return _oauth_failure(exc)
        except Exception:
            return _html(login_html.message(login_html.UNAVAILABLE), 503)
        user = token.get('userinfo') if isinstance(token, dict) else None
        if not isinstance(user, dict):
            try:
                user = await client.userinfo(token=token)
            except Exception:
                user = None
        if not isinstance(user, dict) or user.get('email_verified') is not True:
            return _html(login_html.message(login_html.UNVERIFIED), 400)
        from auth.policy import normalize_email

        email = normalize_email(user.get('email'))
        if email is None:
            return _html(login_html.message(login_html.INCOMPLETE), 400)
        try:
            role = get_store().role_for(email)
        except StoreUnavailable:
            return _html(login_html.message(login_html.UNAVAILABLE), 503)
        if role is None:
            try:
                get_store().record_login(email, 'denied')
            except StoreUnavailable:
                return _html(login_html.message(login_html.UNAVAILABLE), 503)
            return _html(login_html.message(login_html.NOT_ON_LIST), 403)
        request.session['email'] = email
        request.session['role'] = role
        request.session['issued_at'] = int(time.time())
        nxt = validate_next(request.session.pop('next', None))
        try:
            get_store().record_login(email, 'ok')
        except StoreUnavailable:
            request.session.clear()
            return _html(login_html.message(login_html.UNAVAILABLE), 503)
        return _redirect(nxt or '/')

    @app.post('/logout')
    async def logout_post(request: Request):
        request.session.clear()
        return _redirect('/login')

    @app.get('/logout')
    async def logout_get():
        return HTMLResponse('Method Not Allowed', status_code=405, headers={'Cache-Control': 'no-store'})


def _oauth_failure(exc):
    error = getattr(exc, 'error', '') or ''
    text = login_html.CANCELLED if error == 'access_denied' else login_html.INCOMPLETE
    return _html(login_html.message(text), 400)


def _html(body, status=200):
    return HTMLResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})


def _redirect(location):
    return RedirectResponse(location, status_code=303, headers={'Cache-Control': 'no-store'})
