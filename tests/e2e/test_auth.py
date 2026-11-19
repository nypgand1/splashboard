# -*- coding: utf-8 -*-
from tests.e2e.auth_env import E2E_EMAIL


def test_authenticated_home_and_account_menu(page, e2e_server):
    page.goto(e2e_server + '/', wait_until='domcontentloaded')
    assert '/login' not in page.url

    header = page.locator('header.app-navbar')
    header.wait_for(state='visible', timeout=15000)
    box = header.bounding_box()
    assert box is not None and round(box['height']) == 72

    account_btn = page.get_by_role('button', name='Account', exact=True)
    account_btn.wait_for(state='visible', timeout=15000)
    account_btn.locator('svg').wait_for(state='visible', timeout=15000)
    box = account_btn.bounding_box()
    assert box is not None
    assert round(box['width']) == 34
    assert round(box['height']) == 34
    styles = account_btn.evaluate(
        "el => { const cs = getComputedStyle(el); "
        "return { pad: cs.paddingTop, lh: cs.lineHeight, "
        "border: cs.borderTopWidth, bg: cs.backgroundColor }; }"
    )
    assert styles['pad'] == '8px'
    assert styles['lh'] == '0px'
    assert styles['border'] == '0px'
    assert styles['bg'] in ('rgba(0, 0, 0, 0)', 'transparent')
    icon = account_btn.locator('.app-account-icon')
    assert icon.get_attribute('aria-hidden') == 'true'
    assert account_btn.locator('svg').count() == 1

    account_btn.click()
    dropdown = page.locator('.app-account-dropdown')
    dropdown.wait_for(state='visible', timeout=10000)
    assert E2E_EMAIL in dropdown.inner_text()
    assert dropdown.locator('.app-account-admin').inner_text().strip() == 'Admin'
    logout_btn = dropdown.locator('form[action="/logout"][method="post"] button.app-account-logout')
    assert logout_btn.inner_text().strip() == 'Logout'


def test_authenticated_admin_page(page, e2e_server):
    page.goto(e2e_server + '/admin', wait_until='domcontentloaded')
    body = page.locator('.app-main-content')
    body.wait_for(state='visible', timeout=15000)
    page.get_by_text('Allowlist', exact=False).wait_for(state='visible', timeout=15000)
    assert "You don't have access to this page." not in body.inner_text()


def test_anonymous_redirects_to_login(context, page, e2e_server):
    context.clear_cookies()
    page.goto(e2e_server + '/', wait_until='domcontentloaded')
    assert '/login' in page.url
    btn = page.get_by_role('button', name='Continue with Google')
    btn.wait_for(state='visible', timeout=10000)

    styles = btn.evaluate(
        "el => { const cs = getComputedStyle(el); "
        "return { bg: cs.backgroundColor, borderTop: cs.borderTopColor, "
        "borderRight: cs.borderRightColor, borderBottom: cs.borderBottomColor, "
        "borderLeft: cs.borderLeftColor }; }"
    )
    assert styles['bg'] == 'rgb(255, 255, 255)'
    for side in ('borderTop', 'borderRight', 'borderBottom', 'borderLeft'):
        assert styles[side] == 'rgb(116, 119, 117)'

    btn_box = btn.bounding_box()
    assert btn_box is not None and btn_box['height'] == 40

    svg_box = btn.locator('svg').bounding_box()
    assert svg_box is not None and svg_box['width'] == 20 and svg_box['height'] == 20


def test_logout_posts_and_lands_on_login(page, e2e_server):
    page.goto(e2e_server + '/', wait_until='domcontentloaded')
    account_btn = page.get_by_role('button', name='Account', exact=True)
    account_btn.wait_for(state='visible', timeout=15000)
    account_btn.click()

    logout_btn = page.locator('form[action="/logout"][method="post"] button.app-account-logout')
    logout_btn.wait_for(state='visible', timeout=10000)
    logout_btn.click()

    page.wait_for_url('**/login*', timeout=10000)
    page.get_by_role('button', name='Continue with Google').wait_for(state='visible', timeout=10000)
