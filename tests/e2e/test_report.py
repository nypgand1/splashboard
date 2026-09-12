import time

from tests.e2e.fixtures import FINISHED_ID


def _wait(page, selector, timeout=30000):
    page.wait_for_selector(selector, timeout=timeout)


def _select_game_tab(page, name, wrap_id):
    page.evaluate('window.scrollTo(0, 0)')
    for _ in range(8):
        if wrap_id == 'wrap-report':
            page.locator('#report-tab').click()
        else:
            page.evaluate(
                '''(label) => {
                    const tabs = document.querySelectorAll('[role="tab"]');
                    const tab = [...tabs].find(
                        (node) => (node.textContent || '').includes(label)
                    );
                    if (tab) {
                        tab.click();
                    }
                }''',
                name,
            )
        time.sleep(0.4)
        if page.locator(f'#{wrap_id}').is_visible():
            return
        page.evaluate('window.scrollTo(0, 0)')


def _open_report(page, e2e_server):
    page.set_viewport_size({'width': 1400, 'height': 900})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    page.locator('#pane-bs table').first.wait_for(state='attached', timeout=20000)
    report_tab = page.locator('#report-tab')
    report_tab.wait_for(state='visible', timeout=20000)
    report_tab.click()
    for _ in range(6):
        selected = page.evaluate(
            '''() => {
                const t = document.querySelector('#report-tab');
                return !!(t && (t.getAttribute('aria-selected') === 'true' || t.getAttribute('data-active') === 'true'));
            }'''
        )
        wrap_on = page.locator('#wrap-report').is_visible()
        if selected and wrap_on:
            break
        report_tab.click()
        time.sleep(0.4)
    page.locator('#report-workspace').wait_for(state='attached', timeout=20000)
    page.locator('#wrap-report').wait_for(state='visible', timeout=20000)
    page.locator('#report-papers .report-js-table').first.wait_for(state='attached', timeout=30000)


def test_report_note_and_pdf_export(page, e2e_server):
    _open_report(page, e2e_server)
    note = page.locator('#report-papers [data-text-block]').first
    note.wait_for(state='attached', timeout=20000)
    assert note.get_attribute('contenteditable') == 'true'
    note.click()
    page.keyboard.type('Scout note')
    assert 'Scout note' in (note.inner_text() or '')

    with page.expect_download(timeout=60000) as download_info:
        page.locator('#btn-export-pdf').click()
    download = download_info.value
    assert download.suggested_filename.endswith('.pdf')


def test_report_survives_leaving_and_returning_to_tab(page, e2e_server):
    _open_report(page, e2e_server)
    first = page.locator('#report-papers .report-paper').first
    assert first.locator('.report-js-table').count() >= 1
    assert 'Score' in (first.inner_text() or '')
    _select_game_tab(page, 'Box Score', 'wrap-bs')
    page.locator('#wrap-bs').wait_for(state='visible', timeout=15000)
    page.locator('#wrap-report').wait_for(state='hidden', timeout=15000)

    _select_game_tab(page, 'Report', 'wrap-report')
    page.locator('#wrap-report').wait_for(state='visible', timeout=15000)
    page.locator('#report-papers .report-js-table').first.wait_for(
        state='attached', timeout=20000,
    )
    first = page.locator('#report-papers .report-paper').first
    assert first.locator('.report-js-table').count() >= 1
    assert 'Score' in (first.inner_text() or '')


def test_report_toolbar_sticks_and_pm_is_plain(page, e2e_server):
    _open_report(page, e2e_server)
    page.locator('.report-page-btn[data-page-index="2"]').click()
    page.wait_for_timeout(800)
    page.locator('#report-papers .report-js-table').first.wait_for(state='attached', timeout=20000)

    pm = page.evaluate(
        '''() => {
            const pmHeader = [...document.querySelectorAll('#report-papers th')]
                .find((th) => (th.textContent || '').trim() === 'PM');
            if (!pmHeader) return { found: false };
            const idx = [...pmHeader.parentElement.children].indexOf(pmHeader);
            const td = [...document.querySelectorAll('#report-papers tbody tr')]
                .map((tr) => tr.children[idx])
                .find((cell) => cell && (cell.textContent || '').trim());
            if (!td) return { found: false };
            return { found: true, color: getComputedStyle(td).color };
        }'''
    )
    if pm.get('found'):
        assert pm['color'] != 'rgb(0, 119, 182)'
        assert pm['color'] != 'rgb(230, 57, 70)'

    page.evaluate('document.querySelector("#report-papers .report-paper:last-child").scrollIntoView()')
    page.wait_for_timeout(400)
    box = page.locator('#report-toolbar').bounding_box()
    assert box is not None
    assert box['y'] < 40


def _hydrate_report_page(page, index):
    page.locator(f'#report-page-list [data-page-index="{index}"]').click()
    page.wait_for_timeout(700)


def test_report_delete_x_removes_that_a4_sheet(page, e2e_server):
    """The × on a paper deletes that sheet's content, not a neighbor."""
    _open_report(page, e2e_server)
    _hydrate_report_page(page, 0)
    _hydrate_report_page(page, 1)
    _hydrate_report_page(page, 2)
    page.wait_for_timeout(400)

    team_paper = page.locator('#report-paper-page-2')
    player_paper = page.locator('#report-paper-page-3')
    team_paper.wait_for(state='attached')
    player_paper.wait_for(state='attached')
    assert 'Team Stats' in (team_paper.inner_text() or '')
    assert 'Player Stats' in (player_paper.inner_text() or '')

    native = []
    page.on('dialog', lambda dialog: native.append(dialog.message) or dialog.dismiss())
    team_paper.locator('.report-page-delete').click()
    page.locator('#report-dialog-ok').wait_for(state='visible', timeout=10000)
    page.locator('#report-dialog-ok').click()
    page.wait_for_function(
        'document.getElementById("report-paper-page-2") === null',
        timeout=15000,
    )
    assert native == []
    assert page.locator('#report-paper-page-1').count() == 1
    assert page.locator('#report-paper-page-3').count() == 1

    _hydrate_report_page(page, 1)
    moved = page.locator('#report-paper-page-3')
    text = moved.inner_text() or ''
    assert 'Player Stats' in text
    assert 'Team Stats' not in text


def test_report_delete_page_keeps_other_papers(page, e2e_server):
    _open_report(page, e2e_server)
    assert page.locator('#report-page-list [data-page-index]').count() == 6
    native = []
    page.on('dialog', lambda dialog: native.append(dialog.message) or dialog.dismiss())
    target = page.locator('#report-papers .report-paper').nth(2)
    target_id = target.get_attribute('id')
    first_id = page.locator('#report-papers .report-paper').first.get_attribute('id')
    target.locator('.report-page-delete').click()
    page.locator('#report-dialog-ok').wait_for(state='visible', timeout=10000)
    page.locator('#report-dialog-ok').click()
    page.wait_for_function(
        'document.querySelectorAll("#report-papers .report-paper").length === 5',
        timeout=15000,
    )
    assert native == []
    assert page.locator(f'#{target_id}').count() == 0
    assert page.locator(f'#{first_id}').count() == 1
    assert page.locator('#report-page-list [data-page-index]').count() == 5
    nested = page.evaluate(
        'document.querySelectorAll("#report-page-list .report-page-list").length'
    )
    assert nested == 0
    remaining = page.locator('#report-papers .report-js-table').first.inner_text()
    assert remaining.strip()


def test_report_reset_uses_modal_not_native_confirm(page, e2e_server):
    _open_report(page, e2e_server)
    native = []
    page.on('dialog', lambda dialog: native.append(dialog.message) or dialog.dismiss())
    page.locator('#report-reset-layout').click()
    page.locator('#report-dialog-ok').wait_for(state='visible', timeout=10000)
    page.locator('#report-dialog-cancel').click()
    assert native == []


def test_report_toolbar_matches_paper_and_icon_size(page, e2e_server):
    _open_report(page, e2e_server)
    geom = page.evaluate(
        '''() => {
            const toolbar = document.getElementById('report-toolbar');
            const paper = document.querySelector('.report-paper');
            const icon = document.getElementById('report-add-text');
            const tb = toolbar.getBoundingClientRect();
            const pb = paper.getBoundingClientRect();
            const ib = icon.getBoundingClientRect();
            return { tw: tb.width, pw: pb.width, iw: ib.width, ih: ib.height };
        }'''
    )
    assert geom['tw'] <= geom['pw'] + 1
    assert 34 <= geom['iw'] <= 40
    assert 34 <= geom['ih'] <= 40


def test_report_thead_has_no_brand_rule(page, e2e_server):
    _open_report(page, e2e_server)
    border = page.evaluate(
        '''() => {
            const th = document.querySelector('.report-js-table thead th');
            if (!th) return null;
            return getComputedStyle(th).borderBottomColor;
        }'''
    )
    assert border is not None
    assert border != 'rgb(0, 180, 216)'
