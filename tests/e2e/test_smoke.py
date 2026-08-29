import time

from tests.e2e.fixtures import (
    AWAY,
    CANCELLED_ID,
    FINISHED_ID,
    HOME,
    LIVE_ID,
    UPCOMING_ID,
)


def _wait(page, selector, timeout=30000):
    page.wait_for_selector(selector, timeout=timeout)


def _reveal_loading(page, wrap_id):
    page.evaluate(
        """(wrapId) => {
            const wrap = document.getElementById(wrapId);
            if (!wrap) return;
            wrap.style.display = 'block';
            wrap.style.visibility = 'visible';
            wrap.querySelectorAll('*').forEach((el) => {
                el.style.visibility = 'visible';
            });
        }""",
        wrap_id,
    )


def _click_show(page, label):
    page.locator('#home-show').get_by_text(label, exact=True).click()
    time.sleep(0.4)


def test_home_schedule_filters_and_links(page, e2e_server):
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(e2e_server + '/', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    _wait(page, '#home-show')

    assert page.locator('.ag-root').count() == 0
    hero = page.locator('.game-info-banner').inner_text()
    assert AWAY in hero
    assert HOME in hero
    assert 'IN_PROGRESS' in hero

    type_wrap = page.locator('#home-game-type-wrap')
    assert type_wrap.count() == 1
    assert type_wrap.evaluate('el => getComputedStyle(el).display') != 'none'
    type_text = page.locator('#home-game-type').inner_text()
    assert 'Regular' in type_text
    assert 'Playoff' in type_text

    assert page.locator('#home-show').inner_text().find('Upcoming') != -1
    hrefs = page.eval_on_selector_all(
        'a.home-schedule-row-clickable',
        'els => els.map(a => a.getAttribute("href"))',
    )
    assert f'/game/{LIVE_ID}' in hrefs
    assert f'/game/{FINISHED_ID}' not in hrefs

    list_text = page.locator('.home-schedule-list').inner_text()
    assert '2026-03-01' in list_text
    assert '19:00' in list_text
    assert 'T19:' not in list_text
    assert 'T17:' not in list_text

    _click_show(page, 'All')
    hrefs = page.eval_on_selector_all(
        'a.home-schedule-row-clickable',
        'els => els.map(a => a.getAttribute("href"))',
    )
    assert f'/game/{FINISHED_ID}' in hrefs
    assert f'/game/{LIVE_ID}' in hrefs
    static_hrefs = page.eval_on_selector_all(
        '.home-schedule-row-static',
        'els => els.map(el => el.getAttribute("href"))',
    )
    assert page.locator(f'a[href="/game/{CANCELLED_ID}"]').count() == 0
    assert page.locator(f'a[href="/game/{UPCOMING_ID}"]').count() == 0
    assert page.locator('.home-schedule-row-static').count() >= 1
    assert all(h in (None, '') for h in static_hrefs)

    path0 = page.url
    page.locator('.home-schedule-row-static').first.click()
    time.sleep(0.3)
    assert page.url == path0

    page.locator(f'a[href="/game/{FINISHED_ID}"]').first.click()
    page.wait_for_url(f'**/game/{FINISHED_ID}', timeout=15000)


def test_home_viewports(page, e2e_server):
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(e2e_server + '/', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    box = page.locator('.game-info-banner').bounding_box()
    assert box and box['width'] > 200
    overflow = page.evaluate(
        'document.documentElement.scrollWidth > document.documentElement.clientWidth + 4'
    )
    assert page.locator('.ag-root').count() == 0
    assert overflow is False

    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(e2e_server + '/', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    assert page.locator('#home-show').count() == 1


def _select_tab(page, name):
    page.locator('[role="tab"]').filter(has_text=name).first.click()
    time.sleep(0.5)


def test_game_tabs_and_rotation_paper(page, e2e_server):
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    banner = page.locator('.game-info-banner').inner_text()
    assert HOME in banner
    assert 'FINISHED' in banner

    tabs = page.locator('[role="tab"]')
    labels = [tabs.nth(i).inner_text().strip() for i in range(tabs.count())]
    assert labels[:4] == ['Box Score', 'Rotation', 'Lineup Stats', 'Play-By-Play']

    for name in ('Box Score', 'Lineup Stats', 'Play-By-Play', 'Rotation'):
        _select_tab(page, name)
        time.sleep(0.3)

    _reveal_loading(page, 'wrap-rotation')
    page.locator('#rotation-graph, .js-plotly-plot').first.wait_for(state='attached', timeout=20000)
    page.wait_for_timeout(1500)
    rot = page.evaluate(
        '''() => {
            const graph = document.querySelector('#rotation-graph')
                || document.querySelector('.js-plotly-plot');
            if (!graph) return {missing: true};
            const paper = graph.closest('.braves-card-wrapper, .mantine-Paper-root');
            const wrap = document.querySelector('#wrap-rotation');
            const rect = graph.getBoundingClientRect();
            const cs = paper ? getComputedStyle(paper) : {};
            const badges = [...document.querySelectorAll('#wrap-rotation .mantine-Badge-root')];
            return {
                lastUpdate: !!(wrap && wrap.textContent.includes('Last Update')),
                hasPaper: !!paper,
                border: cs.borderTopWidth || '',
                graphW: Math.round(rect.width),
                graphH: Math.round(rect.height),
                vw: window.innerWidth,
                tableScroll: !!(graph.closest('.braves-table-scroll')),
                badgesCount: badges.length,
                badgesText: badges.map(b => b.textContent),
            };
        }'''
    )
    assert not rot.get('missing')
    assert rot['hasPaper'] is True
    assert rot['lastUpdate'] is True
    assert rot['tableScroll'] is False
    assert rot['badgesCount'] >= 1
    assert any('Run' in b for b in rot['badgesText'])
    assert rot['graphW'] != 1220
    assert rot['graphW'] > 400
    assert rot['graphH'] > 200


    page.set_viewport_size({'width': 375, 'height': 812})
    page.wait_for_timeout(800)
    narrow = page.evaluate(
        '''() => {
            const graph = document.querySelector('#rotation-graph')
                || document.querySelector('.js-plotly-plot');
            if (!graph) return {missing: true};
            return {graphW: Math.round(graph.getBoundingClientRect().width), vw: window.innerWidth};
        }'''
    )
    assert not narrow.get('missing')
    assert narrow['graphW'] != 1220
    assert narrow['graphW'] < 400


def test_box_score_paint_and_table_pan(page, e2e_server):
    page.set_viewport_size({'width': 500, 'height': 900})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    _select_tab(page, 'Box Score')
    page.locator('#pane-bs table').first.wait_for(state='attached', timeout=20000)
    _reveal_loading(page, 'wrap-bs')
    page.evaluate('window.dispatchEvent(new Event("resize"))')
    page.wait_for_timeout(500)
    paint = page.evaluate(
        '''() => {
            const cells = [...document.querySelectorAll('#pane-bs .ag-cell')];
            const pmPos = cells.find(c =>
                c.getAttribute('col-id') === '+/-' && c.textContent.trim() === '5');
            const pmNeg = cells.find(c =>
                c.getAttribute('col-id') === '+/-' && c.textContent.trim() === '-3');
            const starter = cells.find(c =>
                c.getAttribute('col-id') === 'S' && (c.textContent || '').includes('○'));
            const player = cells.find(c => c.getAttribute('col-id') === 'Player');
            const colorOf = el => {
                if (!el) return null;
                const inner = el.querySelector('span') || el;
                return getComputedStyle(inner).color;
            };
            return {
                cellCount: cells.length,
                pmPos: colorOf(pmPos),
                pmNeg: colorOf(pmNeg),
                starter: starter ? starter.textContent.trim() : '',
                playerAlign: player ? getComputedStyle(player).textAlign : null,
            };
        }'''
    )
    if paint['cellCount'] > 10:
        assert paint['pmPos'] == 'rgb(0, 119, 182)'
        assert paint['pmNeg'] == 'rgb(230, 57, 70)'
        assert '○' in paint['starter']
        assert paint['playerAlign'] == 'center'

    pan_900 = page.evaluate(
        '''() => {
            const hosts = [...document.querySelectorAll('.ag-center-cols-viewport, .braves-table-scroll')];
            const host = hosts.find(el => el.scrollWidth > el.clientWidth + 2) || hosts[0];
            if (!host) return {missing: true};
            const cs = getComputedStyle(host);
            return {
                overflow: host.scrollWidth > host.clientWidth + 2,
                scrollbar: cs.scrollbarWidth,
                clientW: host.clientWidth,
                scrollW: host.scrollWidth,
            };
        }'''
    )
    assert not pan_900.get('missing')
    assert pan_900['scrollbar'] == 'none'
    if pan_900['clientW'] > 50:
        assert pan_900['overflow'] is True

    page.set_viewport_size({'width': 1280, 'height': 900})
    page.wait_for_timeout(400)
    pan_1280 = page.evaluate(
        '''() => {
            const host = document.querySelector('.ag-center-cols-viewport')
                || document.querySelector('.braves-table-scroll');
            if (!host) return {missing: true};
            const cs = getComputedStyle(host);
            return {
                overflow: host.scrollWidth > host.clientWidth + 2,
                scrollbar: cs.scrollbarWidth,
            };
        }'''
    )
    assert not pan_1280.get('missing')
    assert pan_1280['scrollbar'] == 'none'
