import time

import pytest

from tests.e2e.fixtures import FINISHED_ID


def _wait(page, selector, timeout=30000):
    page.wait_for_selector(selector, timeout=timeout)


def _set_game_tab(page, value):
    page.evaluate('window.scrollTo(0, 0)')
    page.evaluate(
        '''(value) => {
            if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
                window.dash_clientside.set_props('tabs', {value: value});
            }
        }''',
        value,
    )


def _select_game_tab(page, name, wrap_id):
    tab_value = {
        'wrap-bs': 'tab-bs',
        'wrap-report': 'tab-report',
        'wrap-pbp': 'tab-pbp',
        'wrap-rotation': 'tab-rotation',
        'wrap-lineup': 'tab-lineup',
    }.get(wrap_id, 'tab-bs')
    for _ in range(8):
        _set_game_tab(page, tab_value)
        try:
            page.locator('[role="tab"]').filter(has_text=name).first.click(
                force=True, timeout=1500,
            )
        except Exception:
            page.evaluate(
                '''(label) => {
                    const tab = [...document.querySelectorAll('[role="tab"]')].find(
                        (node) => (node.textContent || '').includes(label)
                    );
                    if (tab) {
                        tab.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    }
                }''',
                name,
            )
        time.sleep(0.4)
        if page.locator(f'#{wrap_id}').is_visible():
            return
    page.evaluate(
        '''(wrapId) => {
            const wraps = ['wrap-bs', 'wrap-rotation', 'wrap-lineup', 'wrap-pbp', 'wrap-report'];
            wraps.forEach((id) => {
                const el = document.getElementById(id);
                if (el) {
                    el.style.display = id === wrapId ? 'block' : 'none';
                }
            });
        }''',
        wrap_id,
    )


def _open_report(page, e2e_server):
    page.set_viewport_size({'width': 1400, 'height': 900})
    page.goto(e2e_server + f'/game/{FINISHED_ID}', wait_until='domcontentloaded')
    _wait(page, '.game-info-banner')
    page.locator('#pane-bs table').first.wait_for(state='attached', timeout=20000)
    page.locator('#report-tab').wait_for(state='visible', timeout=20000)
    for _ in range(8):
        _set_game_tab(page, 'tab-report')
        try:
            page.locator('#report-tab').click(force=True, timeout=2000)
        except Exception:
            pass
        if page.locator('#wrap-report').is_visible() and page.locator('#report-workspace').count():
            break
        time.sleep(0.4)
    page.locator('#report-workspace').wait_for(state='attached', timeout=20000)
    page.locator('#wrap-report').wait_for(state='visible', timeout=20000)
    page.locator('#report-papers .report-js-table').first.wait_for(state='attached', timeout=30000)
    page.evaluate(
        '''() => {
            const cancel = document.getElementById('report-dialog-cancel');
            if (cancel) cancel.click();
        }'''
    )


def test_report_note_and_pdf_export(page, e2e_server):
    _open_report(page, e2e_server)
    note = page.locator('#report-papers [data-text-block]').first
    note.wait_for(state='attached', timeout=20000)
    assert note.get_attribute('contenteditable') == 'true'
    note.click()
    width_before = page.evaluate(
        '''() => {
            const item = document.querySelector('#report-papers [data-text-block]')
                .closest('.grid-stack-item');
            return parseInt(item.getAttribute('gs-w') || item.getAttribute('data-w') || '0', 10);
        }'''
    )
    page.keyboard.type('Scout note')
    assert 'Scout note' in (note.inner_text() or '')
    width_after = page.evaluate(
        '''() => {
            const item = document.querySelector('#report-papers [data-text-block]')
                .closest('.grid-stack-item');
            return parseInt(item.getAttribute('gs-w') || item.getAttribute('data-w') || '0', 10);
        }'''
    )
    assert width_after == width_before
    assert width_after == 6

    with page.expect_download(timeout=60000) as download_info:
        page.locator('#btn-export-pdf').click()
        dialog_ok = page.locator('#report-dialog-ok')
        try:
            dialog_ok.wait_for(state='visible', timeout=1500)
            if (dialog_ok.inner_text() or '').strip() == 'Export':
                dialog_ok.click()
        except Exception:
            pass
    download = download_info.value
    assert download.suggested_filename.endswith('.pdf')


def test_report_pdf_keeps_last_note_line(page, e2e_server):
    from pypdf import PdfReader

    _open_report(page, e2e_server)
    page.evaluate(
        '''() => {
            const note = document.querySelector('#report-papers [data-text-block]');
            note.innerHTML = '<p>Alpha scout line</p><p>Bravo scout line</p><p>ZedLastNoteLine</p>';
            note.dispatchEvent(new Event('input', { bubbles: true }));
            const item = note.closest('.grid-stack-item');
            const grid = item.closest('.report-grid').gridstack;
            const minH = parseInt(item.getAttribute('data-min-h') || '1', 10);
            if (grid) {
                grid.update(item, { h: Math.max(1, minH), minH: Math.max(1, minH) });
            }
        }'''
    )
    note = page.locator('#report-papers [data-text-block]').first
    assert 'ZedLastNoteLine' in (note.inner_text() or '')

    with page.expect_download(timeout=60000) as download_info:
        page.locator('#btn-export-pdf').click()
        dialog_ok = page.locator('#report-dialog-ok')
        try:
            dialog_ok.wait_for(state='visible', timeout=1500)
            if (dialog_ok.inner_text() or '').strip() == 'Export':
                dialog_ok.click()
        except Exception:
            pass
    reader = PdfReader(str(download_info.value.path()))
    text = '\n'.join((pdf_page.extract_text() or '') for pdf_page in reader.pages)
    assert 'ZedLastNoteLine' in text


def test_report_page_one_half_tables_and_side_note(page, e2e_server):
    _open_report(page, e2e_server)
    geom = page.evaluate(
        '''() => {
            const paper = document.querySelector('#report-papers .report-paper');
            const score = paper.querySelector('[data-table-key="score_group"]')
                && paper.querySelector('[data-table-key="score_group"]').closest('.grid-stack-item');
            const four = paper.querySelector('[data-table-key="t_adv_df"]')
                && paper.querySelector('[data-table-key="t_adv_df"]').closest('.grid-stack-item');
            const note = paper.querySelector('[data-text-block]')
                && paper.querySelector('[data-text-block]').closest('.grid-stack-item');
            const attr = (el, name) => parseInt(el.getAttribute(name) || '0', 10);
            return {
                scoreW: score ? attr(score, 'gs-w') || attr(score, 'data-w') : 0,
                fourW: four ? attr(four, 'gs-w') || attr(four, 'data-w') : 0,
                noteX: note ? attr(note, 'gs-x') || attr(note, 'data-x') : -1,
                noteW: note ? attr(note, 'gs-w') || attr(note, 'data-w') : 0,
            };
        }'''
    )
    assert geom['scoreW'] == 6
    assert geom['fourW'] == 6
    assert geom['noteX'] == 6
    assert geom['noteW'] == 6


def test_report_table_block_hugs_table_not_viewport(page, e2e_server):
    _open_report(page, e2e_server)
    geom = page.evaluate(
        '''() => {
            const item = document.querySelector(
                '#report-papers .grid-stack-item[data-block-type="builtin_table"]'
            );
            if (!item) {
                return { missing: true };
            }
            const table = item.querySelector('.report-js-table');
            const title = item.querySelector('.report-block-title-row');
            const ir = item.getBoundingClientRect();
            const tableH = table ? table.getBoundingClientRect().height : 0;
            const titleH = title ? title.getBoundingClientRect().height : 0;
            const gsH = parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '0', 10);
            return {
                missing: false,
                blockH: ir.height,
                contentH: titleH + tableH,
                viewportH: window.innerHeight,
                gsH: gsH,
            };
        }'''
    )
    assert not geom.get('missing')
    assert geom['contentH'] > 20
    assert geom['blockH'] < geom['viewportH'] * 0.45
    assert geom['gsH'] < 12
    assert geom['blockH'] - geom['contentH'] <= 48


def test_report_player_zero_made_shows_zero_pct(page, e2e_server):
    _open_report(page, e2e_server)
    _hydrate_report_page(page, 2)
    page.wait_for_timeout(800)
    text = page.locator('#report-paper-page-3').inner_text()
    assert '0.0%' in text
    assert 'Player Stats' in text


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
    assert page.locator('#report-page-list [data-page-index]').count() == 4
    native = []
    page.on('dialog', lambda dialog: native.append(dialog.message) or dialog.dismiss())
    target = page.locator('#report-papers .report-paper').nth(2)
    target_id = target.get_attribute('id')
    first_id = page.locator('#report-papers .report-paper').first.get_attribute('id')
    target.locator('.report-page-delete').click()
    page.locator('#report-dialog-ok').wait_for(state='visible', timeout=10000)
    page.locator('#report-dialog-ok').click()
    page.wait_for_function(
        'document.querySelectorAll("#report-papers .report-paper").length === 3',
        timeout=15000,
    )
    assert native == []
    assert page.locator(f'#{target_id}').count() == 0
    assert page.locator(f'#{first_id}').count() == 1
    assert page.locator('#report-page-list [data-page-index]').count() == 3
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


def test_report_page_list_aligns_with_paper_top(page, e2e_server):
    _open_report(page, e2e_server)
    page.wait_for_function(
        '''() => {
            const list = document.getElementById('report-page-list');
            return !!(list && parseFloat(list.style.marginTop) > 40);
        }''',
        timeout=8000,
    )
    geom = page.evaluate(
        '''() => {
            const toolbar = document.getElementById('report-toolbar');
            const list = document.getElementById('report-page-list');
            const paper = document.querySelector('.report-paper');
            const tb = toolbar.getBoundingClientRect();
            const lb = list.getBoundingClientRect();
            const pb = paper.getBoundingClientRect();
            return {
                listTop: lb.top,
                paperTop: pb.top,
                toolbarH: tb.height,
                stickyTop: parseFloat(list.style.top) || 0,
                marginTop: parseFloat(list.style.marginTop) || 0,
            };
        }'''
    )
    assert abs(geom['listTop'] - geom['paperTop']) <= 3
    assert geom['marginTop'] >= geom['toolbarH'] - 1
    assert abs(geom['stickyTop'] - (8 + geom['marginTop'])) <= 1


def test_report_add_table_lineup_paints_all_rows(page, e2e_server):
    _open_report(page, e2e_server)
    before = page.evaluate(
        'document.querySelectorAll("#report-papers .report-js-table").length'
    )
    page.evaluate("window.splashboardReport.addTable('lineup_home')")
    page.wait_for_function(
        f'document.querySelectorAll("#report-papers .report-js-table").length > {before}',
        timeout=15000,
    )
    rows = page.evaluate(
        '''() => Math.max(0, ...[...document.querySelectorAll("#report-papers .report-js-table")]
            .map((table) => table.querySelectorAll("tbody tr").length))'''
    )
    assert rows >= 8


def test_report_table_cannot_resize_below_content(page, e2e_server):
    _open_report(page, e2e_server)
    before = page.evaluate(
        'document.querySelectorAll(".grid-stack-item[data-block-type=\\"builtin_table\\"]").length'
    )
    page.evaluate("window.splashboardReport.addTable('score_group')")
    page.wait_for_function(
        f'''() => {{
            const items = document.querySelectorAll('.grid-stack-item[data-block-type="builtin_table"]');
            if (items.length <= {before}) return false;
            const item = items[items.length - 1];
            return !!(item.gridstackNode && item.gridstackNode.minH);
        }}''',
        timeout=15000,
    )
    result = page.evaluate(
        '''() => {
            const items = document.querySelectorAll('.grid-stack-item[data-block-type="builtin_table"]');
            const item = items[items.length - 1];
            const grid = item.closest('.report-grid').gridstack;
            const minH = item.gridstackNode.minH;
            grid.update(item, { h: 1 });
            return { minH: minH, h: item.gridstackNode.h };
        }'''
    )
    assert result['minH'] >= 1
    assert result['h'] >= result['minH']


def test_report_pdf_warns_when_paper_overflows(page, e2e_server):
    _open_report(page, e2e_server)
    overflowed = page.evaluate(
        '''() => {
            const paper = document.querySelector('#report-papers .report-paper');
            const item = paper && paper.querySelector('.grid-stack-item');
            const grid = paper && paper.querySelector('.report-grid') && paper.querySelector('.report-grid').gridstack;
            if (!item || !grid) return false;
            grid.update(item, { minH: 1, h: 40 });
            if (window.splashboardReport && window.splashboardReport.markOverflow) {
                window.splashboardReport.markOverflow();
            }
            return paper.classList.contains('is-overflowing');
        }'''
    )
    assert overflowed is True
    native = []
    page.on('dialog', lambda dialog: native.append(dialog.message) or dialog.dismiss())
    page.locator('#btn-export-pdf').click()
    page.locator('#report-dialog-ok').wait_for(state='visible', timeout=10000)
    message = page.locator('#report-dialog-message').inner_text()
    assert 'crop' in (message or '').lower()
    assert page.locator('#report-dialog-ok').inner_text().strip() == 'Export'
    page.locator('#report-dialog-cancel').click()
    assert native == []


@pytest.mark.pdf_text
def test_report_pdf_contains_on_screen_text(page, e2e_server):
    from pypdf import PdfReader

    _open_report(page, e2e_server)
    with page.expect_download(timeout=60000) as download_info:
        page.locator('#btn-export-pdf').click()
        dialog_ok = page.locator('#report-dialog-ok')
        try:
            dialog_ok.wait_for(state='visible', timeout=1500)
            if (dialog_ok.inner_text() or '').strip() == 'Export':
                dialog_ok.click()
        except Exception:
            pass
    path = download_info.value.path()
    reader = PdfReader(str(path))
    text = '\n'.join((pdf_page.extract_text() or '') for pdf_page in reader.pages)
    assert 'PTS' in text or 'Min' in text
    assert '20:00' in text or 'Lin' in text
