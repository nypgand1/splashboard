# -*- coding: utf-8 -*-
"""Allowlist admin. Reads the request principal. Does not talk to Google."""
import datetime

from dash import ALL, Input, Output, State, callback, dcc, html, no_update, register_page
import dash_mantine_components as dmc

from auth.current import get as current_principal
from auth.policy import LOCKED_ADMIN, is_permanent_admin
from auth.store import StoreUnavailable, get_store
from ui.components import empty_state, error_alert

register_page(__name__, name='Splashboard TFB | Admin', path='/admin')

_TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
_CELL = {'textAlign': 'center'}
_MESSAGES = {
    'added': 'Added.',
    'updated': 'Updated.',
    'exists': 'That email is already on the list.',
    'invalid': 'Enter a valid email address.',
    'locked': 'This admin cannot be removed.',
    'removed': 'Removed.',
    'missing': 'That email is not on the list.',
}
_DENIAL = "You don't have access to this page."
_LOAD_ERROR = 'Could not load this page. Try again later.'
_SAVE_ERROR = 'Could not save this change. Try again later.'


def _when(at):
    moment = datetime.datetime.fromtimestamp(int(at), tz=_TAIPEI)
    return moment.strftime('%Y-%m-%d %H:%M:%S.') + f'{moment.microsecond:06d}+08:00'


def _th(text):
    return html.Th(text, style=_CELL)


def _td(child):
    return html.Td(child, style=_CELL)


def _table(head, body_rows):
    return dmc.Table(
        [
            html.Thead(html.Tr([_th(label) for label in head])),
            html.Tbody(body_rows),
        ],
        striped=True,
        withTableBorder=True,
        className='admin-table',
    )


def _flash_for(code):
    text = _MESSAGES.get(code, _SAVE_ERROR)
    color = 'green' if code in ('added', 'updated', 'removed') else 'red'
    return dmc.Alert(text, title='Admin', color=color)


def _guard():
    user = current_principal()
    if user is None or not getattr(user, 'email', None):
        return None, 'denied'
    try:
        role = get_store().role_for(user.email)
    except StoreUnavailable:
        return None, 'down'
    if role != 'admin':
        return None, 'denied'
    return user.email, None


def _roster_rows():
    store = get_store()
    bootstrap = store.bootstrap
    rows = []
    for user in store.list_users():
        email = user['email']
        permanent = is_permanent_admin(email, bootstrap) or email == LOCKED_ADMIN
        if permanent:
            role = 'admin'
            control = 'admin'
            remove = ''
        else:
            role = user['role']
            control = dmc.Select(
                id={'type': 'admin-role', 'index': email},
                data=[
                    {'value': 'member', 'label': 'member'},
                    {'value': 'admin', 'label': 'admin'},
                ],
                value=role,
                allowDeselect=False,
                searchable=False,
                clearable=False,
                w=120,
            )
            remove = html.Button(
                'Remove',
                type='button',
                className='admin-remove',
                **{'data-admin-remove': email},
            )
        rows.append(html.Tr([
            _td(email),
            _td(control),
            _td(_when(user['created_at'])),
            _td(remove),
        ]))
    return rows


def _roster():
    try:
        rows = _roster_rows()
    except StoreUnavailable:
        return error_alert(_LOAD_ERROR)
    if not rows:
        return empty_state('No accounts yet.', 'Add an email below.')
    return _table(('Email', 'Role', 'Added', ''), rows)


def _changes():
    try:
        rows = get_store().list_changes(limit=100)
    except StoreUnavailable:
        return error_alert(_LOAD_ERROR)
    if not rows:
        return empty_state('No admin changes yet.', 'Add or update an account to record one.')
    return _table(
        ('Time', 'Actor', 'Action', 'Target'),
        [
            html.Tr([
                _td(_when(row['at'])),
                _td(row['actor']),
                _td(row['action']),
                _td(row['target']),
            ])
            for row in rows
        ],
    )


def _logins():
    try:
        rows = get_store().list_logins(limit=100)
    except StoreUnavailable:
        return error_alert(_LOAD_ERROR)
    if not rows:
        return empty_state('No sign-ins yet.', 'A sign-in appears here after someone uses Google.')
    return _table(
        ('Time', 'Email', 'Result'),
        [
            html.Tr([
                _td(_when(row['at'])),
                _td(row['email']),
                _td(row['result']),
            ])
            for row in rows
        ],
    )


def _remove_dialog():
    return html.Dialog(
        [
            html.H2('Remove this account?', id='admin-remove-title'),
            html.P(id='admin-remove-copy'),
            html.Form(
                [
                    html.Button('Cancel', value='cancel', autoFocus=True),
                    html.Button('Remove', value='remove'),
                ],
                method='dialog',
            ),
        ],
        id='admin-remove-dialog',
        **{'aria-labelledby': 'admin-remove-title'},
    )


def _saved(code):
    if code == 'down':
        return error_alert(_SAVE_ERROR), no_update, no_update
    return _flash_for(code), _roster(), _changes()


def layout():
    user = current_principal()
    if user is None or getattr(user, 'role', None) != 'admin':
        return dmc.Container(dmc.Text(_DENIAL), px='md', py='md')
    try:
        roster = _roster()
        changes = _changes()
        logins = _logins()
    except StoreUnavailable:
        return dmc.Container(error_alert(_LOAD_ERROR), px='md', py='md')
    return dmc.Container(
        dmc.Stack(
            [
                dmc.Title('Admin', order=2),
                dmc.Title('Allowlist', order=3),
                dmc.Group(
                    [
                        dmc.TextInput(
                            id='admin-email',
                            label='Email',
                            autoComplete='email',
                            inputProps={'type': 'email', 'inputMode': 'email'},
                            w=280,
                        ),
                        dmc.Select(
                            id='admin-role',
                            label='Role',
                            data=[
                                {'value': 'member', 'label': 'member'},
                                {'value': 'admin', 'label': 'admin'},
                            ],
                            value='member',
                            allowDeselect=False,
                            searchable=False,
                            clearable=False,
                            w=160,
                        ),
                        dmc.Button(
                            'Add',
                            id='admin-add',
                            n_clicks=0,
                            style={'backgroundColor': '#0077b6', 'color': '#ffffff'},
                        ),
                    ],
                    align='flex-end',
                    gap='sm',
                    wrap='wrap',
                ),
                html.Div(id='admin-flash'),
                html.Div(roster, id='admin-roster'),
                dmc.Title('Change log', order=3),
                html.Div(changes, id='admin-changes'),
                dmc.Title('Login log', order=3),
                html.Div(logins, id='admin-logins'),
                _remove_dialog(),
                dcc.Store(id='admin-remove-go'),
            ],
            gap='md',
        ),
        size='lg',
        px='md',
        py='md',
    )


@callback(
    Output('admin-flash', 'children', allow_duplicate=True),
    Output('admin-roster', 'children', allow_duplicate=True),
    Output('admin-changes', 'children', allow_duplicate=True),
    Output('admin-email', 'value'),
    Input('admin-add', 'n_clicks'),
    State('admin-email', 'value'),
    State('admin-role', 'value'),
    prevent_initial_call=True,
)
def add_account(clicks, email, role):
    if not clicks:
        return no_update, no_update, no_update, no_update
    actor, problem = _guard()
    if problem == 'denied':
        return no_update, no_update, no_update, no_update
    if problem == 'down' or actor is None:
        return error_alert(_SAVE_ERROR), no_update, no_update, no_update
    try:
        code = get_store().add_user(actor, email or '', role or 'member')
    except StoreUnavailable:
        return error_alert(_SAVE_ERROR), no_update, no_update, no_update
    flash, roster, changes = _saved(code)
    cleared = '' if code in ('added', 'updated') else no_update
    return flash, roster, changes, cleared


@callback(
    Output('admin-flash', 'children', allow_duplicate=True),
    Output('admin-roster', 'children', allow_duplicate=True),
    Output('admin-changes', 'children', allow_duplicate=True),
    Input({'type': 'admin-role', 'index': ALL}, 'value'),
    prevent_initial_call=True,
)
def change_role(_values):
    from dash import ctx

    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or triggered.get('type') != 'admin-role':
        return no_update, no_update, no_update
    value = ctx.triggered[0].get('value') if ctx.triggered else None
    if value not in ('member', 'admin'):
        return no_update, no_update, no_update
    actor, problem = _guard()
    if problem == 'denied':
        return no_update, no_update, no_update
    if problem == 'down' or actor is None:
        return error_alert(_SAVE_ERROR), no_update, no_update
    try:
        code = get_store().set_role(actor, triggered.get('index'), value)
    except StoreUnavailable:
        return error_alert(_SAVE_ERROR), no_update, no_update
    if code == 'exists':
        return no_update, no_update, no_update
    return _saved(code)


@callback(
    Output('admin-flash', 'children', allow_duplicate=True),
    Output('admin-roster', 'children', allow_duplicate=True),
    Output('admin-changes', 'children', allow_duplicate=True),
    Output('admin-remove-go', 'data'),
    Input('admin-remove-go', 'data'),
    prevent_initial_call=True,
)
def confirm_remove(email):
    if not email:
        return no_update, no_update, no_update, no_update
    actor, problem = _guard()
    if problem == 'denied':
        return no_update, no_update, no_update, None
    if problem == 'down' or actor is None:
        return error_alert(_SAVE_ERROR), no_update, no_update, None
    try:
        code = get_store().remove_user(actor, email)
    except StoreUnavailable:
        return error_alert(_SAVE_ERROR), no_update, no_update, None
    flash, roster, changes = _saved(code)
    return flash, roster, changes, None
