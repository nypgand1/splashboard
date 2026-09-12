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
    assert labels[:5] == ['Box Score', 'Rotation', 'Lineup Stats', 'Play-By-Play', 'Report']

    for name in ('Box Score', 'Lineup Stats', 'Play-By-Play', 'Rotation'):
        _select_tab(page, name)
        time.sleep(0.3)

    _reveal_loading(page, 'wrap-rotation')
    page.locator('#wrap-rotation .js-plotly-plot').wait_for(state='visible', timeout=20000)
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
            const runs = [...document.querySelectorAll('#wrap-rotation button')].filter(
                (b) => (b.id || '').includes('rotation-run')
            );
            return {
                lastUpdate: !!(wrap && wrap.textContent.includes('Last Update')),
                hasPaper: !!paper,
                hasPeriod: !!(wrap && wrap.textContent.includes('All') && wrap.textContent.includes('1Q')),
                hasDnp: !!(wrap && wrap.textContent.includes('Show DNP')),
                border: cs.borderTopWidth || '',
                graphW: Math.round(rect.width),
                graphH: Math.round(rect.height),
                vw: window.innerWidth,
                tableScroll: !!(graph.closest('.braves-table-scroll')),
                runsCount: runs.length,
                runsText: runs.map(b => b.textContent),
            };
        }'''
    )
    assert not rot.get('missing')
    assert rot['hasPaper'] is True
    assert rot['lastUpdate'] is True
    assert rot['hasPeriod'] is True
    assert rot['hasDnp'] is True
    assert rot['tableScroll'] is False
    assert rot['runsCount'] >= 1
    assert any('10' in t and '2' in t for t in rot['runsText'])
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


def _playhead_t(page):
    return page.evaluate(
        '''() => {
            const gd = document.querySelector('#rotation-graph .js-plotly-plot');
            if (!gd || !gd.layout) return null;
            const shapes = gd.layout.shapes || [];
            const play = shapes.filter((s) => s && s.line && s.line.color === '#0077b6' && s.x0 === s.x1);
            if (play.length) return play[play.length - 1].x0;
            const verts = shapes.filter((s) => s && s.x0 != null && s.x0 === s.x1);
            return verts.length ? verts[verts.length - 1].x0 : null;
        }'''
    )


def _click_rotation_time(page, t, yaxis='yaxis'):
    coords = page.evaluate(
        '''({t, yaxis}) => {
            const gd = document.querySelector('#rotation-graph .js-plotly-plot');
            if (!gd || !gd._fullLayout) return null;
            const xa = gd._fullLayout.xaxis;
            const ya = gd._fullLayout[yaxis] || gd._fullLayout.yaxis;
            const drags = [...gd.querySelectorAll('.nsewdrag')].filter((el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
            if (!xa || !ya || !drags.length) return null;
            const yaTop = gd.getBoundingClientRect().top + ya._offset;
            const yaBot = yaTop + ya._length;
            let box = drags[0].getBoundingClientRect();
            for (const el of drags) {
                const r = el.getBoundingClientRect();
                const mid = (r.top + r.bottom) / 2;
                if (mid >= yaTop && mid <= yaBot) { box = r; break; }
            }
            const frac = (t - xa.range[0]) / (xa.range[1] - xa.range[0]);
            return {
                x: box.left + frac * box.width,
                y: box.top + box.height * 0.4,
            };
        }''',
        {'t': t, 'yaxis': yaxis},
    )
    assert coords, 'rotation plot axes not ready'
    page.mouse.click(coords['x'], coords['y'])
    return coords


def test_rotation_playhead_follows_click_time(page, e2e_server):
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    for name in ('Box Score', 'Lineup Stats', 'Play-By-Play', 'Rotation'):
        _select_tab(page, name)
        time.sleep(0.3)
    _reveal_loading(page, 'wrap-rotation')
    page.locator('#rotation-graph .js-plotly-plot').wait_for(state='attached', timeout=20000)
    page.wait_for_timeout(1500)

    _click_rotation_time(page, 30, 'yaxis')
    page.wait_for_function(
        '''() => {
            const gd = document.querySelector('#rotation-graph .js-plotly-plot');
            if (!gd || !gd.layout) return false;
            const shapes = gd.layout.shapes || [];
            const play = shapes.filter((s) => s && s.line && s.line.color === '#0077b6' && s.x0 === s.x1);
            const t = play.length ? play[play.length - 1].x0 : null;
            return t != null && Math.abs(t - 30) < 4 && Math.abs(t - 60) > 10;
        }''',
        timeout=10000,
    )
    on_bar = _playhead_t(page)
    assert abs(on_bar - 30) < 4
    assert abs(on_bar - 60) > 10

    _click_rotation_time(page, 20, 'yaxis3')
    page.wait_for_function(
        '''() => {
            const gd = document.querySelector('#rotation-graph .js-plotly-plot');
            if (!gd || !gd.layout) return false;
            const shapes = gd.layout.shapes || [];
            const play = shapes.filter((s) => s && s.line && s.line.color === '#0077b6' && s.x0 === s.x1);
            const t = play.length ? play[play.length - 1].x0 : null;
            return t != null && Math.abs(t - 20) < 4;
        }''',
        timeout=10000,
    )
    on_empty = _playhead_t(page)
    assert abs(on_empty - 20) < 4


def test_report_tab_hidden_on_narrow_viewport(page, e2e_server):
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    page.wait_for_timeout(600)
    assert page.locator('#report-tab').is_visible() is False


def test_report_first_paint_on_desktop(page, e2e_server):
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    page.locator('#pane-bs table').first.wait_for(state='attached', timeout=20000)
    report_tab = page.locator('#report-tab')
    report_tab.wait_for(state='visible', timeout=20000)
    assert report_tab.is_visible() is True
    _select_tab(page, 'Report')
    for _ in range(4):
        if page.locator('#wrap-report').is_visible():
            break
        _select_tab(page, 'Report')
        time.sleep(0.4)
    page.locator('#report-workspace').wait_for(state='attached', timeout=20000)
    page.locator('#wrap-report').wait_for(state='visible', timeout=20000)
    page.locator('#report-papers .report-js-table').first.wait_for(state='attached', timeout=30000)
    assert page.locator('#report-page-list .report-page-btn[data-page-index]').count() == 6
    table = page.locator('#report-papers .report-js-table').first
    assert table.locator('th').count() >= 1
    assert table.locator('td').count() >= 1


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
