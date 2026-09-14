(function () {
    if (window.splashboardReport) {
        return;
    }

    var IMAGE_MAX_BYTES = 1000000;
    var GRID_COLUMNS = 12;
    var DESKTOP_MIN_PX = 1280;
    var A4_WIDTH_MM = 210;
    var A4_HEIGHT_MM = 297;
    var GRIDSTACK_CSS = '/assets/gridstack.min.css';
    var GRIDSTACK_JS = '/assets/gridstack-all.js';
    var JSPDF_JS = '/assets/jspdf.umd.min.js';
    var REPORT_FONT_NAME = 'NotoSansTC';
    var REPORT_FONT_URL = '/assets/NotoSansTC-Regular.ttf';
    var TABLE_TITLES = {
        score_group: 'Score',
        t_adv_df: 'Pace, PPP & Four Factors',
        t_df: 'Team Stats',
        k_df: 'Key Stats',
        p_df_home: 'Home Player Stats',
        p_df_away: 'Away Player Stats',
        lineup_home: 'Home Lineup Stats',
        lineup_away: 'Away Lineup Stats'
    };
    var LOWER_BETTER = { Foul: 1, PF: 1, TO: 1, TOV: 1, 'TOV%': 1 };
    var COL_GROUPS = [
        { name: '2PT', keys: ['2M', '2A', '2FG%'], subs: ['M', 'A', '%'] },
        { name: '3PT', keys: ['3M', '3A', '3FG%'], subs: ['M', 'A', '%'] },
        { name: 'FT', keys: ['FTM', 'FTA', 'FT%'], subs: ['M', 'A', '%'] },
        { name: 'REB', keys: ['OR', 'DR', 'REB'], subs: ['O', 'D', 'T'] },
        { name: 'PIP', keys: ['PIPM', 'PIPA', 'PIP'], subs: ['M', 'A', 'PTS'] },
        { name: 'SCP', keys: ['SCPM', 'SCPA', 'SCP'], subs: ['M', 'A', 'PTS'] }
    ];
    var FF_KEYS = ['eFG%', 'TOV%', 'ORB%', 'FT-R'];
    var libsPromise = null;
    var hydrateLocks = {};
    var ALLOWED_IMAGE_MIMES = {
        'image/jpeg': true,
        'image/png': true,
        'image/webp': true
    };
    var currentPageIndex = 0;
    var spyObserver = null;
    var spyObservedCount = -1;
    var spyRatios = {};
    var hydrating = false;
    var lastStickyKey = '';

    function gameId() {
        var el = document.getElementById('report-game-id') || document.getElementById('game_id');
        return el ? (el.textContent || '').trim() : '';
    }

    function storageKey(id) {
        return 'splashboard.report.layout.' + id;
    }

    function readLayoutFromDom() {
        var jsonEl = document.getElementById('report-layout-json');
        var layout = null;
        if (jsonEl && jsonEl.textContent) {
            try {
                layout = JSON.parse(jsonEl.textContent);
            } catch (err) {
                layout = null;
            }
        }
        if (!layout || !layout.pages) {
            layout = { version: 1, pages: [] };
        }
        var papers = document.querySelectorAll('#report-papers .report-paper');
        var pages = [];
        var prevById = {};
        (layout.pages || []).forEach(function (prev) {
            if (prev && prev.id) {
                prevById[prev.id] = prev;
            }
        });
        papers.forEach(function (paper, pageIndex) {
            var pid = paperPageId(paper) || ('page-' + (pageIndex + 1));
            var prevPage = prevById[pid] || {};
            var items = paper.querySelectorAll('.grid-stack-item');
            if (paper.getAttribute('data-hydrated') !== '1' || !items.length) {
                pages.push({
                    id: pid,
                    blocks: prevPage.blocks || []
                });
                return;
            }
            var blocks = [];
            items.forEach(function (item) {
                var blockId = item.getAttribute('gs-id') || item.getAttribute('data-gs-id');
                var prev = (prevPage.blocks || []).find(function (b) {
                    return b.id === blockId;
                }) || {};
                var note = item.querySelector('[data-text-block]');
                var img = item.querySelector('img.report-image-block');
                var block = {
                    id: blockId,
                    type: item.getAttribute('data-block-type') || prev.type,
                    table_key: item.getAttribute('data-table-key') || prev.table_key,
                    x: parseInt(item.getAttribute('gs-x') || item.getAttribute('data-x') || '0', 10),
                    y: parseInt(item.getAttribute('gs-y') || item.getAttribute('data-y') || '0', 10),
                    w: parseInt(item.getAttribute('gs-w') || item.getAttribute('data-w') || prev.w || '6', 10),
                    h: parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '3', 10)
                };
                if (block.type === 'text') {
                    block.content = note ? note.innerHTML : (prev.content || '');
                }
                if (block.type === 'image') {
                    block.src = img ? img.getAttribute('src') : (prev.src || '');
                }
                blocks.push(block);
            });
            pages.push({
                id: prevPage.id || paper.id || ('page-' + (pageIndex + 1)),
                blocks: blocks
            });
        });
        layout.pages = pages;
        layout.version = 1;
        return layout;
    }

    function persistLocal(layout) {
        var id = gameId();
        if (!id || !layout) {
            return layout;
        }
        var wrap = document.getElementById('wrap-report');
        if (wrap && wrap.style.display === 'none') {
            return loadStored() || layout;
        }
        var hasDomBlocks = !!document.querySelector('#report-papers .grid-stack-item');
        var hydrated = document.querySelector('#report-papers .report-paper[data-hydrated="1"]');
        if (!hydrated || !hasDomBlocks) {
            var existing = loadStored();
            if (existing && existing.pages && existing.pages.some(function (page) {
                return page && page.blocks && page.blocks.length;
            })) {
                return existing;
            }
        }
        try {
            var data = JSON.stringify(layout);
            localStorage.setItem(storageKey(id), data);
            var jsonEl = document.getElementById('report-layout-json');
            if (jsonEl) {
                jsonEl.textContent = data;
            }
        } catch (err) {
            console.warn('Report layout was not saved', err);
        }
        return layout;
    }

    function loadStored() {
        var id = gameId();
        if (!id) {
            return null;
        }
        try {
            var raw = localStorage.getItem(storageKey(id));
            return raw ? JSON.parse(raw) : null;
        } catch (err) {
            return null;
        }
    }

    function uniqueId(prefix) {
        return prefix + '-' + Date.now().toString(36) + '-' + Math.floor(Math.random() * 10000);
    }

    function loadStyle(href) {
        if (document.querySelector('link[data-report-lib="' + href + '"]')) {
            return Promise.resolve();
        }
        return new Promise(function (resolve, reject) {
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.setAttribute('data-report-lib', href);
            link.onload = function () { resolve(); };
            link.onerror = reject;
            document.head.appendChild(link);
        });
    }

    function loadScript(src) {
        if (document.querySelector('script[data-report-lib="' + src + '"]')) {
            return Promise.resolve();
        }
        return new Promise(function (resolve, reject) {
            var el = document.createElement('script');
            el.src = src;
            el.async = false;
            el.setAttribute('data-report-lib', src);
            el.onload = function () { resolve(); };
            el.onerror = reject;
            document.head.appendChild(el);
        });
    }

    function ensureReportLibs() {
        if (window.GridStack && window.jspdf && window.jspdf.jsPDF) {
            return Promise.resolve();
        }
        if (libsPromise) {
            return libsPromise;
        }
        libsPromise = loadStyle(GRIDSTACK_CSS).then(function () {
            return loadScript(GRIDSTACK_JS);
        }).then(function () {
            return loadScript(JSPDF_JS);
        });
        return libsPromise;
    }

    function parseSplit(payload) {
        if (!payload) {
            return null;
        }
        var obj = payload;
        if (typeof payload === 'string') {
            try {
                obj = JSON.parse(payload);
            } catch (err) {
                return null;
            }
        }
        if (!obj || !obj.columns || !obj.data) {
            return null;
        }
        var rows = obj.data.map(function (row) {
            var rec = {};
            obj.columns.forEach(function (col, i) {
                rec[col] = row[i];
            });
            return rec;
        });
        return { columns: obj.columns.slice(), rows: rows };
    }

    function tablePayload() {
        var el = document.getElementById('report-table-data');
        if (!el || !el.textContent) {
            return {};
        }
        try {
            return JSON.parse(el.textContent) || {};
        } catch (err) {
            return {};
        }
    }

    function numVal(v) {
        if (v === null || v === undefined || v === '') {
            return null;
        }
        var n = parseFloat(String(v).replace('%', ''));
        return isNaN(n) ? null : n;
    }

    function isBlankZero(col, val) {
        if (col === '+/-') {
            return false;
        }
        if (typeof val === 'string' && val.indexOf('%') !== -1) {
            return false;
        }
        if (val === 0 || val === '0' || val === '0.0') {
            return true;
        }
        return false;
    }

    function formatCell(col, val) {
        if (val === null || val === undefined || val === '') {
            return '';
        }
        if (col === 'S' && String(val).trim()) {
            return '○';
        }
        if (isBlankZero(col, val)) {
            return '';
        }
        return String(val);
    }

    function plusMinusStyle(val) {
        var n = numVal(val);
        if (n === null) {
            return { color: '#1e293b', fontWeight: '400' };
        }
        if (n > 0) {
            return { color: '#0077b6', fontWeight: '700' };
        }
        if (n < 0) {
            return { color: '#e63946', fontWeight: '700' };
        }
        return { color: '#64748b', fontWeight: '400' };
    }

    function winnerIndex(rows, columns, tableKey) {
        if (!rows || rows.length !== 2) {
            return {};
        }
        if (tableKey !== 't_df' && tableKey !== 't_adv_df' && tableKey !== 'k_df' && tableKey !== 'score_group') {
            return {};
        }
        var map = {};
        columns.forEach(function (col) {
            if (col === 'Team' || col === 'Min') {
                return;
            }
            var a = numVal(rows[0][col]);
            var b = numVal(rows[1][col]);
            if (a === null || b === null || a === b) {
                return;
            }
            var lower = !!LOWER_BETTER[col];
            map[col] = lower ? (a < b ? 0 : 1) : (a > b ? 0 : 1);
        });
        return map;
    }

    function skipFourFactorsGroup(tableKey) {
        return tableKey === 'p_df_home' || tableKey === 'p_df_away'
            || tableKey === 'lineup_home' || tableKey === 'lineup_away';
    }

    function groupedHeader(columns, tableKey) {
        var used = {};
        var top = [];
        var sub = [];
        var hasGroup = COL_GROUPS.some(function (g) {
            return g.keys.some(function (k) { return columns.indexOf(k) !== -1; });
        });
        var ff = skipFourFactorsGroup(tableKey)
            ? []
            : FF_KEYS.filter(function (k) { return columns.indexOf(k) !== -1; });
        if (!hasGroup && !ff.length) {
            return null;
        }
        columns.forEach(function (col) {
            if (used[col]) {
                return;
            }
            var group = COL_GROUPS.filter(function (g) { return g.keys.indexOf(col) !== -1; })[0];
            if (group) {
                var present = group.keys.filter(function (k) { return columns.indexOf(k) !== -1; });
                present.forEach(function (k) { used[k] = 1; });
                top.push({ text: group.name, span: present.length });
                present.forEach(function (k) {
                    sub.push(group.subs[group.keys.indexOf(k)] || k);
                });
                return;
            }
            if (ff.indexOf(col) !== -1 && !used['__ff']) {
                used['__ff'] = 1;
                ff.forEach(function (k) { used[k] = 1; });
                top.push({ text: '4 FACTORS', span: ff.length });
                ff.forEach(function (k) { sub.push(k); });
                return;
            }
            if (used[col]) {
                return;
            }
            used[col] = 1;
            top.push({ text: col, span: 1, rowSpan: 2 });
        });
        return { top: top, sub: sub };
    }

    function paintTable(host, tableKey, item) {
        if (!host) {
            return;
        }
        var parsed = parseSplit(tablePayload()[tableKey]);
        host.innerHTML = '';
        if (!parsed || !parsed.rows.length) {
            host.textContent = '—';
            host.className = 'report-table-host';
            return;
        }
        var columns = parsed.columns;
        var rows = parsed.rows;
        var winners = winnerIndex(rows, columns, tableKey);
        var grouped = groupedHeader(columns, tableKey);
        var table = document.createElement('table');
        table.className = 'text-nowrap report-js-table';
        var thead = document.createElement('thead');
        if (grouped) {
            var tr1 = document.createElement('tr');
            grouped.top.forEach(function (cell) {
                var th = document.createElement('th');
                th.textContent = cell.text;
                if (cell.span > 1) {
                    th.colSpan = cell.span;
                }
                if (cell.rowSpan) {
                    th.rowSpan = cell.rowSpan;
                }
                tr1.appendChild(th);
            });
            thead.appendChild(tr1);
            if (grouped.sub.length) {
                var tr2 = document.createElement('tr');
                grouped.sub.forEach(function (label) {
                    var th = document.createElement('th');
                    th.textContent = label;
                    tr2.appendChild(th);
                });
                thead.appendChild(tr2);
            }
        } else {
            var tr = document.createElement('tr');
            columns.forEach(function (col) {
                var th = document.createElement('th');
                th.textContent = col;
                tr.appendChild(th);
            });
            thead.appendChild(tr);
        }
        table.appendChild(thead);
        var tbody = document.createElement('tbody');
        rows.forEach(function (row, rIdx) {
            var tr = document.createElement('tr');
            var dnp = String(row.Min || '') === 'DNP';
            columns.forEach(function (col, cIdx) {
                if (dnp && cIdx > columns.indexOf('Min') && columns.indexOf('Min') !== -1) {
                    return;
                }
                var td = document.createElement('td');
                var text = formatCell(col, row[col]);
                td.textContent = text;
                if (col === 'Player' || col === 'Lineup' || col === 'Lineups') {
                    td.style.fontWeight = '700';
                }
                if (col === '+/-') {
                    var st = plusMinusStyle(row[col]);
                    td.style.color = st.color;
                    td.style.fontWeight = st.fontWeight;
                }
                if (winners[col] === rIdx) {
                    td.style.color = '#0077b6';
                    td.style.fontWeight = '700';
                }
                if (cIdx === 0 && (col === 'Team' || tableKey === 't_df' || tableKey === 't_adv_df' || tableKey === 'k_df' || tableKey === 'score_group') && rows.length === 2) {
                    td.style.borderLeft = rIdx === 0 ? '3.5px solid #0077b6' : '3.5px solid #94a3b8';
                }
                if (dnp && col === 'Min') {
                    td.colSpan = Math.max(1, columns.length - cIdx);
                    td.style.fontWeight = '700';
                    td.style.color = '#94a3b8';
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        host.appendChild(table);
        host.className = 'report-table-host';
    }

    function tableHeading(tableKey) {
        var match = (tablePayload().match) || {};
        var name = '';
        var kind = '';
        var side = '';
        if (tableKey === 'p_df_home' || tableKey === 'lineup_home') {
            name = match.home_team || 'Home';
            kind = tableKey === 'p_df_home' ? 'Player Stats' : 'Lineup Stats';
            side = 'home';
        } else if (tableKey === 'p_df_away' || tableKey === 'lineup_away') {
            name = match.away_team || 'Away';
            kind = tableKey === 'p_df_away' ? 'Player Stats' : 'Lineup Stats';
            side = 'away';
        } else {
            return TABLE_TITLES[tableKey] || '';
        }
        return { name: name, kind: kind, side: side };
    }

    function fillBlockTitle(titleEl, tableKey) {
        if (!titleEl) {
            return;
        }
        titleEl.textContent = '';
        var heading = tableHeading(tableKey);
        if (typeof heading === 'string') {
            titleEl.textContent = heading;
            return;
        }
        var dot = document.createElement('span');
        dot.className = 'report-block-title-dot';
        dot.style.backgroundColor = heading.side === 'home' ? '#00b4d8' : '#94a3b8';
        titleEl.appendChild(dot);
        titleEl.appendChild(document.createTextNode(heading.name + ' | ' + heading.kind));
    }

    function parseLayoutJson(id) {
        var el = document.getElementById(id);
        if (!el || !el.textContent) {
            return null;
        }
        try {
            return JSON.parse(el.textContent);
        } catch (err) {
            return null;
        }
    }

    function writeLayoutJson(layout) {
        var el = document.getElementById('report-layout-json');
        if (el) {
            el.textContent = JSON.stringify(layout);
        }
    }

    function applyReportTabViewport() {
        var tab = document.getElementById('report-tab');
        if (!tab) {
            return;
        }
        var desktop = window.innerWidth >= DESKTOP_MIN_PX;
        tab.classList.toggle('report-tab-narrow', !desktop);
        if (desktop) {
            return;
        }
        var selected = tab.getAttribute('aria-selected') === 'true' || tab.getAttribute('data-active') === 'true';
        if (!selected) {
            return;
        }
        var first = document.querySelector('.braves-clean-tabs [role="tab"]');
        if (first && first !== tab) {
            first.click();
        }
    }

    function paperCount() {
        return document.querySelectorAll('#report-papers .report-paper').length;
    }

    function clampPageIndex(index) {
        var n = paperCount();
        if (!n) {
            return 0;
        }
        if (isNaN(index) || index < 0) {
            return 0;
        }
        if (index >= n) {
            return n - 1;
        }
        return index;
    }

    function setCurrentPage(index) {
        index = clampPageIndex(index);
        currentPageIndex = index;
        document.querySelectorAll('#report-papers .report-paper').forEach(function (paper, i) {
            paper.classList.toggle('is-current', i === index);
        });
        document.querySelectorAll('.report-page-btn[data-page-index]').forEach(function (btn) {
            var btnIndex = parseInt(btn.getAttribute('data-page-index'), 10);
            btn.classList.toggle('is-active', btnIndex === index);
        });
        hydratePage(index);
    }

    function activePageIndex() {
        return clampPageIndex(currentPageIndex);
    }

    function activeGrid() {
        var papers = document.querySelectorAll('#report-papers .report-paper');
        var paper = papers[activePageIndex()];
        var el = paper && paper.querySelector('.report-grid');
        return el && el.gridstack ? el.gridstack : null;
    }

    function closeTableMenu() {
        var picker = document.querySelector('.report-table-picker');
        if (picker) {
            picker.classList.remove('is-open');
        }
        var btn = document.getElementById('report-add-table');
        if (btn) {
            btn.setAttribute('aria-expanded', 'false');
        }
    }

    function toggleTableMenu() {
        var picker = document.querySelector('.report-table-picker');
        if (!picker) {
            return;
        }
        var open = !picker.classList.contains('is-open');
        picker.classList.toggle('is-open', open);
        var btn = document.getElementById('report-add-table');
        if (btn) {
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
    }

    var activeNoteEl = null;

    function showNoteToolbar(show) {
        var tb = document.getElementById('report-note-toolbar');
        if (tb) {
            tb.style.display = show ? 'flex' : 'none';
        }
        window.setTimeout(syncPageListSticky, 0);
    }

    function toggleColorMenu(mode, open) {
        var menu = document.getElementById('report-rte-' + mode + '-menu');
        var btn = document.querySelector('[data-rte-toggle-menu="' + mode + '"]');
        if (!menu) return;
        var shouldOpen = (open !== undefined) ? open : menu.hasAttribute('hidden');
        
        // Close other color menus first
        ['color', 'highlight'].forEach(function (m) {
            if (m !== mode) {
                var otherMenu = document.getElementById('report-rte-' + m + '-menu');
                var otherBtn = document.querySelector('[data-rte-toggle-menu="' + m + '"]');
                if (otherMenu) otherMenu.setAttribute('hidden', '');
                if (otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
            }
        });

        if (shouldOpen) {
            menu.removeAttribute('hidden');
            if (btn) btn.setAttribute('aria-expanded', 'true');
        } else {
            menu.setAttribute('hidden', '');
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }
    }

    function closeAllColorMenus() {
        ['color', 'highlight'].forEach(function (m) {
            var menu = document.getElementById('report-rte-' + m + '-menu');
            var btn = document.querySelector('[data-rte-toggle-menu="' + m + '"]');
            if (menu) menu.setAttribute('hidden', '');
            if (btn) btn.setAttribute('aria-expanded', 'false');
        });
    }

    function updateColorIndicator(mode, color) {
        var ind = document.getElementById('report-rte-' + mode + '-indicator');
        if (ind) {
            ind.style.backgroundColor = color;
        }
    }

    function execNoteCommand(cmd, value) {
        if (!activeNoteEl) {
            return;
        }
        activeNoteEl.focus();
        if (cmd === 'color') {
            document.execCommand('foreColor', false, value);
            updateColorIndicator('color', value);
            closeAllColorMenus();
        } else if (cmd === 'highlight') {
            document.execCommand('hiliteColor', false, value || '#f1c40f');
            updateColorIndicator('highlight', value || '#f1c40f');
            closeAllColorMenus();
        } else if (cmd === 'bold') {
            document.execCommand('bold', false, null);
        } else if (cmd === 'italic') {
            document.execCommand('italic', false, null);
        } else if (cmd === 'underline') {
            document.execCommand('underline', false, null);
        } else if (cmd === 'strikethrough') {
            document.execCommand('strikeThrough', false, null);
        } else if (cmd === 'bulletList') {
            document.execCommand('insertUnorderedList', false, null);
        } else if (cmd === 'orderedList') {
            document.execCommand('insertOrderedList', false, null);
        }
        if (!resizeNote(activeNoteEl)) {
            document.execCommand('undo', false, null);
            return;
        }
        persistLocal(readLayoutFromDom());
    }

    function resizeNote(note) {
        var item = note.closest('.grid-stack-item');
        var gridEl = note.closest('.report-grid');
        var grid = gridEl && gridEl.gridstack;
        if (!item || !grid) {
            return false;
        }
        var node = item.gridstackNode || {};
        var currentH = node.h || parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '2', 10);
        var currentW = node.w || parseInt(item.getAttribute('gs-w') || item.getAttribute('data-w') || '6', 10);

        var clone = note.cloneNode(true);
        var targetW = note.offsetWidth || item.offsetWidth || 300;
        clone.style.cssText = 'position:absolute;left:-9999px;top:0;width:' + targetW + 'px;height:auto;max-height:none;min-height:0;visibility:hidden;white-space:pre-wrap;';
        document.body.appendChild(clone);
        var contentHeight = clone.scrollHeight || clone.offsetHeight || 0;
        document.body.removeChild(clone);

        var cell = cellPx(grid);
        var needed = Math.max(1, Math.ceil((contentHeight + 12) / cell));
        var maxH = Math.max(1, paperMaxRows(grid) - (node.y || 0));
        if (needed > maxH) {
            return false;
        }
        item.setAttribute('data-min-h', String(needed));
        item.setAttribute('gs-w', String(currentW));
        item.setAttribute('data-w', String(currentW));
        if (currentH !== needed) {
            grid.update(item, {
                h: needed,
                minH: needed,
                maxH: maxH,
                w: currentW
            });
            item.setAttribute('gs-h', String(needed));
            item.setAttribute('data-h', String(needed));
            item.setAttribute('gs-w', String(currentW));
            item.setAttribute('data-w', String(currentW));
        }
        markPaperOverflow();
        return true;
    }

    function notePaperMaxH(note) {
        var item = note.closest('.grid-stack-item');
        var gridEl = note.closest('.report-grid');
        var grid = gridEl && gridEl.gridstack;
        if (!item || !grid) {
            return 1;
        }
        var node = item.gridstackNode || {};
        return Math.max(1, paperMaxRows(grid) - (node.y || 0));
    }

    function bindTextBlocks(root) {
        (root || document).querySelectorAll('#report-papers [data-text-block]').forEach(function (note) {
            if (note.dataset.bound === '1') {
                return;
            }
            note.dataset.bound = '1';
            note.setAttribute('contentEditable', 'true');
            note.setAttribute('spellCheck', 'false');

            note.addEventListener('focus', function () {
                activeNoteEl = note;
                showNoteToolbar(true);
            });
            note.addEventListener('focusin', function () {
                activeNoteEl = note;
                showNoteToolbar(true);
            });

            note.addEventListener('keydown', function (event) {
                if (event.key === 'Enter') {
                    var item = note.closest('.grid-stack-item');
                    var gridEl = note.closest('.report-grid');
                    var grid = gridEl && gridEl.gridstack;
                    if (item && grid && resizeNote(note) === false) {
                        event.preventDefault();
                        return;
                    }
                    if (item && grid) {
                        var node = item.gridstackNode || {};
                        var needed = parseInt(item.getAttribute('data-min-h') || '1', 10);
                        var maxH = Math.max(1, paperMaxRows(grid) - (node.y || 0));
                        if (needed >= maxH) {
                            event.preventDefault();
                            return;
                        }
                    }
                }
                if (event.key === 'Tab') {
                    event.preventDefault();
                    if (event.shiftKey) {
                        document.execCommand('outdent', false, null);
                    } else {
                        document.execCommand('indent', false, null);
                    }
                    if (!resizeNote(note)) {
                        document.execCommand('undo', false, null);
                        return;
                    }
                    persistLocal(readLayoutFromDom());
                }
            });

            note.addEventListener('beforeinput', function () {
                note.dataset.savedHtml = note.innerHTML;
            });

            note.addEventListener('input', function () {
                if (!resizeNote(note)) {
                    note.innerHTML = note.dataset.savedHtml || '';
                    resizeNote(note);
                    return;
                }
            });
            note.addEventListener('blur', function () {
                resizeNote(note);
                persistLocal(readLayoutFromDom());
                setTimeout(function () {
                    if (document.activeElement && (document.activeElement.closest('[data-text-block]') || document.activeElement.closest('#report-note-toolbar'))) {
                        return;
                    }
                    showNoteToolbar(false);
                }, 200);
            });
        });
    }

    function makePageDeleteButton(index) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'report-page-delete no-print';
        btn.setAttribute('data-delete-page', String(index));
        btn.setAttribute('aria-label', 'Delete page');
        btn.title = 'Delete page';
        btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>';
        return btn;
    }

    function initScrollSpy() {
        var papers = document.querySelectorAll('#report-papers .report-paper');
        if (!window.IntersectionObserver) {
            return;
        }
        if (papers.length === spyObservedCount && spyObserver) {
            return;
        }
        if (spyObserver) {
            spyObserver.disconnect();
        }
        spyRatios = {};
        spyObservedCount = papers.length;
        spyObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                var idx = parseInt(entry.target.getAttribute('data-page-index'), 10);
                if (!isNaN(idx)) {
                    spyRatios[idx] = entry.intersectionRatio;
                }
            });
            var bestIdx = currentPageIndex;
            var bestRatio = -1;
            Object.keys(spyRatios).forEach(function (key) {
                var idx = parseInt(key, 10);
                var ratio = spyRatios[key];
                if (ratio > bestRatio) {
                    bestRatio = ratio;
                    bestIdx = idx;
                }
            });
            if (bestRatio > 0) {
                setCurrentPage(bestIdx);
            }
        }, {
            root: null,
            threshold: [0, 0.1, 0.25, 0.4, 0.55, 0.75, 1]
        });
        papers.forEach(function (paper) {
            spyObserver.observe(paper);
        });
    }

    function initOneGrid(paper) {
        var el = paper && paper.querySelector('.report-grid');
        if (!el || !window.GridStack) {
            return el && el.gridstack;
        }
        if (el.dataset.gsInit === '1') {
            return el.gridstack;
        }
        el.querySelectorAll('.grid-stack-item').forEach(function (item) {
            item.setAttribute('gs-id', item.getAttribute('data-gs-id') || '');
            item.setAttribute('gs-x', item.getAttribute('data-x') || '0');
            item.setAttribute('gs-y', item.getAttribute('data-y') || '0');
            item.setAttribute('gs-w', item.getAttribute('data-w') || '6');
            item.setAttribute('gs-h', item.getAttribute('data-h') || '3');
        });
        try {
            var grid = GridStack.init({
                column: 12,
                cellHeight: 36,
                float: true,
                margin: 6,
                handle: '.grid-stack-item-handle',
                disableOneColumnMode: true
            }, el);
            el.dataset.gsInit = '1';
            grid.on('dragstop', function (event, itemEl) {
                var item = itemEl && itemEl.getAttribute ? itemEl : null;
                if (item) {
                    clampItemToPaper(grid, item);
                } else {
                    clampGridToPaper(grid);
                }
                persistLocal(readLayoutFromDom());
                window.setTimeout(markPaperOverflow, 0);
            });
            grid.on('resizestop', function (event, itemEl) {
                var gs = el.gridstack;
                var item = itemEl && itemEl.getAttribute ? itemEl : null;
                if (item && item.getAttribute('data-block-type') === 'image' && gs) {
                    snapImageAspect(gs, item);
                }
                if (item) {
                    clampItemToPaper(grid, item);
                } else {
                    clampGridToPaper(grid);
                }
                persistLocal(readLayoutFromDom());
                window.setTimeout(markPaperOverflow, 0);
            });
            return grid;
        } catch (err) {
            console.warn('GridStack init failed', err);
            return null;
        }
    }

    function hydratePage(index, opts) {
        opts = opts || {};
        var papers = document.querySelectorAll('#report-papers .report-paper');
        var paper = papers[index];
        if (!paper) {
            return Promise.resolve();
        }
        var lockKey = paperPageId(paper) || String(index);
        if (hydrateLocks[lockKey]) {
            return hydrateLocks[lockKey];
        }
        hydrateLocks[lockKey] = ensureReportLibs().then(function () {
            if (paper.getAttribute('data-hydrated') === '1') {
                initOneGrid(paper);
                return;
            }
            hydrating = true;
            try {
            var layout = parseLayoutJson('report-layout-json') || { pages: [] };
            var page = layoutPageForPaper(layout, paper);
            var grid = initOneGrid(paper);
            var gridEl = paper.querySelector('.report-grid');
            if (grid) {
                grid.removeAll();
            }
            (page.blocks || []).forEach(function (block) {
                var node = widgetFromBlock(block);
                if (!node) {
                    return;
                }
                if (grid) {
                    grid.addWidget(node, {
                        id: block.id,
                        x: block.x || 0,
                        y: block.y || 0,
                        w: block.w || 6,
                        h: block.h || 3
                    });
                } else if (gridEl) {
                    gridEl.appendChild(node);
                }
            });
            paper.setAttribute('data-hydrated', '1');
            bindTextBlocks(paper);
            fitAllTableBlocks();
            if (opts.compact && grid) {
                compactGrid(grid);
                syncPageOneSideNote(grid);
            }
            } finally {
                hydrating = false;
            }
            window.setTimeout(function () {
                clampGridToPaper(grid);
                markPaperOverflow();
                syncPageListSticky();
            }, 300);
        });
        return hydrateLocks[lockKey];
    }

    function restoreVisiblePage() {
        var wrap = document.getElementById('wrap-report');
        if (!wrap || wrap.style.display === 'none') {
            return;
        }
        var index = activePageIndex();
        var paper = paperNodes()[index];
        if (!paper || paper.querySelector('.grid-stack-item')) {
            return;
        }
        if (hydrating) {
            return;
        }
        paper.setAttribute('data-hydrated', '0');
        var gridEl = paper.querySelector('.report-grid');
        if (gridEl && !gridEl.gridstack) {
            delete gridEl.dataset.gsInit;
        }
        delete hydrateLocks[paperPageId(paper) || String(index)];
        hydratePage(index);
    }

    function bootReport() {
        var workspace = document.getElementById('report-workspace');
        if (!workspace) {
            return;
        }
        applyReportTabViewport();
        if (workspace.dataset.booted === '1') {
            restoreVisiblePage();
            return;
        }
        workspace.dataset.booted = '1';
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('report-pane-ready', { data: '1' });
        }
        var stored = loadStored();
        if (stored && stored.pages && stored.pages.length) {
            applyStoredLayout(stored);
        } else {
            hydratePage(0, { compact: true }).then(function () {
                persistLocal(readLayoutFromDom());
                initScrollSpy();
                window.setTimeout(function () {
                    markPaperOverflow();
                    syncPageListSticky();
                }, 300);
            });
        }
    }

    function widgetFromBlock(block) {
        var node = document.createElement('div');
        node.className = 'grid-stack-item';
        node.id = 'gs-item-' + block.id;
        node.setAttribute('data-gs-id', block.id);
        node.setAttribute('gs-id', block.id);
        node.setAttribute('data-block-type', block.type || '');
        node.setAttribute('data-table-key', block.table_key || '');
        if (block.aspect) {
            node.setAttribute('data-aspect', String(block.aspect));
        }
        node.setAttribute('data-x', String(block.x || 0));
        node.setAttribute('data-y', String(block.y || 0));
        node.setAttribute('data-w', String(block.w || 6));
        node.setAttribute('data-h', String(block.h || 3));
        var card = document.createElement('div');
        var isTable = block.type === 'builtin_table';
        card.className = 'grid-stack-item-content report-block-card' + (isTable ? ' report-block-card-table' : '');
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'report-block-remove no-print';
        remove.setAttribute('data-remove-block', block.id);
        remove.textContent = '×';
        card.appendChild(remove);
        var handle = document.createElement('div');
        handle.className = 'grid-stack-item-handle no-print';
        handle.title = 'Drag';
        handle.textContent = '⋮⋮';
        if (isTable) {
            var row = document.createElement('div');
            row.className = 'report-block-title-row';
            var title = document.createElement('div');
            title.className = 'report-block-title';
            fillBlockTitle(title, block.table_key);
            row.appendChild(handle);
            row.appendChild(title);
            card.appendChild(row);
        } else {
            card.appendChild(handle);
        }
        var body = document.createElement('div');
        body.className = 'report-block-body';
        if (block.type === 'text') {
            var content = block.content || '';
            var initialP = content.indexOf('<') === 0 ? content : (content ? '<p>' + content + '</p>' : '<p></p>');
            var note = document.createElement('div');
            note.className = 'report-text-block';
            note.setAttribute('data-text-block', block.id);
            note.setAttribute('data-placeholder', 'Notes');
            note.setAttribute('contenteditable', 'true');
            note.innerHTML = initialP;
            body.appendChild(note);
        } else if (block.type === 'image') {
            if (block.src) {
                var img = document.createElement('img');
                img.className = 'report-image-block';
                img.setAttribute('src', block.src);
                body.appendChild(img);
            } else {
                body.textContent = 'Drop an image here from Add image';
                body.className += ' report-image-placeholder';
            }
        } else if (isTable) {
            var host = document.createElement('div');
            host.className = 'report-table-host';
            host.setAttribute('data-table-host', block.table_key || '');
            body.appendChild(host);
            paintTable(host, block.table_key, node);
        }
        card.appendChild(body);
        node.appendChild(card);
        return node;
    }

    function cellPx(grid) {
        if (grid && grid.getCellHeight) {
            return grid.getCellHeight(true) || 42;
        }
        if (grid && grid.opts && grid.opts.cellHeight) {
            return grid.opts.cellHeight + 6;
        }
        return 42;
    }

    function paperMaxRows(grid) {
        var el = grid && grid.el;
        if (!el) {
            return 1;
        }
        var height = el.clientHeight;
        if (height < 80) {
            var paper = el.closest('.report-paper');
            var header = paper && paper.querySelector('.report-header');
            if (paper) {
                height = paper.clientHeight - (header ? header.offsetHeight : 0);
            }
        }
        return Math.max(1, Math.floor(height / cellPx(grid)));
    }

    function itemMinH(item, h) {
        var stored = parseInt(item.getAttribute('data-min-h') || '', 10);
        if (stored >= 1) {
            return stored;
        }
        var type = item.getAttribute('data-block-type');
        if (type === 'text' || type === 'image') {
            return 1;
        }
        return Math.max(1, h);
    }

    function itemMinW(item) {
        var stored = parseInt(item.getAttribute('data-min-w') || '', 10);
        if (stored >= 1) {
            return stored;
        }
        return 1;
    }

    function clampItemToPaper(grid, item) {
        if (!grid || !item || !item.gridstackNode || hydrating) {
            return;
        }
        var node = item.gridstackNode;
        var maxRows = paperMaxRows(grid);
        var w = Math.max(1, node.w || 1);
        var h = Math.max(1, node.h || 1);
        var x = node.x || 0;
        var y = node.y || 0;
        var minH = itemMinH(item, h);
        var minW = itemMinW(item);
        var oversized = minH > maxRows || h > maxRows;
        if (oversized) {
            x = Math.min(Math.max(0, x), Math.max(0, GRID_COLUMNS - w));
            y = 0;
            h = Math.max(h, minH);
            w = Math.min(Math.max(minW, w), GRID_COLUMNS);
            grid.update(item, {
                x: x,
                y: y,
                w: w,
                h: h,
                minW: minW,
                minH: minH,
                maxW: GRID_COLUMNS - x,
                maxH: h
            });
            return;
        }
        w = Math.min(Math.max(minW, w), GRID_COLUMNS);
        h = Math.min(Math.max(minH, h), maxRows);
        x = Math.min(Math.max(0, x), GRID_COLUMNS - w);
        y = Math.min(Math.max(0, y), maxRows - h);
        grid.update(item, {
            x: x,
            y: y,
            w: w,
            h: h,
            minW: minW,
            minH: minH,
            maxW: GRID_COLUMNS - x,
            maxH: maxRows - y
        });
    }

    function clampGridToPaper(grid) {
        if (!grid || !grid.el) {
            return;
        }
        grid.el.querySelectorAll('.grid-stack-item').forEach(function (item) {
            if (item.getAttribute('data-block-type') === 'builtin_table' && item.gridstackNode) {
                item.setAttribute('data-min-h', String(item.gridstackNode.h || 1));
            }
            clampItemToPaper(grid, item);
        });
    }

    function measureContentPx(el) {
        var card = el.querySelector('.report-block-card') || el;
        var clone = card.cloneNode(true);
        var measureClass = 'report-block-card';
        if (card.classList && card.classList.contains('report-block-card-table')) {
            measureClass += ' report-block-card-table';
        }
        clone.className = measureClass;
        clone.style.cssText = '';
        clone.style.position = 'absolute';
        clone.style.inset = 'auto';
        clone.style.left = '-10000px';
        clone.style.top = '0';
        clone.style.right = 'auto';
        clone.style.bottom = 'auto';
        clone.style.visibility = 'hidden';
        clone.style.height = 'auto';
        clone.style.maxHeight = 'none';
        clone.style.minHeight = '0';
        clone.style.overflow = 'visible';
        clone.style.width = (card.offsetWidth || el.offsetWidth || 400) + 'px';
        var cloneBody = clone.querySelector('.report-block-body');
        if (cloneBody) {
            cloneBody.style.height = 'auto';
            cloneBody.style.maxHeight = 'none';
            cloneBody.style.overflow = 'visible';
        }
        document.body.appendChild(clone);
        var height = clone.scrollHeight;
        document.body.removeChild(clone);
        return height;
    }

    function measureBlockH(block, grid, node) {
        var fallback = block.h || 3;
        if (!grid || block.type !== 'builtin_table') {
            return fallback;
        }
        var host = grid.el;
        node.style.position = 'absolute';
        node.style.visibility = 'hidden';
        node.style.pointerEvents = 'none';
        node.style.left = '0';
        node.style.top = '0';
        node.style.width = host.clientWidth + 'px';
        host.appendChild(node);
        var h = Math.max(1, Math.ceil(measureContentPx(node) / cellPx(grid)));
        host.removeChild(node);
        node.style.position = '';
        node.style.visibility = '';
        node.style.pointerEvents = '';
        node.style.left = '';
        node.style.top = '';
        node.style.width = '';
        return h;
    }

    function findFit(grid, w, h, maxRows) {
        var nodes = (grid.engine && grid.engine.nodes) || [];
        if (h > maxRows) {
            if (nodes.length) {
                return null;
            }
            return { x: 0, y: 0, clip: true };
        }
        function overlaps(x, y) {
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                if (x < n.x + n.w && x + w > n.x && y < n.y + n.h && y + h > n.y) {
                    return true;
                }
            }
            return false;
        }
        for (var y = 0; y <= maxRows - h; y++) {
            for (var x = 0; x <= GRID_COLUMNS - w; x++) {
                if (!overlaps(x, y)) {
                    return { x: x, y: y };
                }
            }
        }
        return null;
    }

    function fitAllTableBlocks() {
        var updates = [];
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            var grid = el.gridstack;
            if (!grid) {
                return;
            }
            var cell = cellPx(grid);
            el.querySelectorAll('.grid-stack-item[data-block-type="builtin_table"]').forEach(function (item) {
                var node = item.gridstackNode || {};
                var currentH = node.h || parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '3', 10);
                var h = Math.max(1, Math.ceil(measureContentPx(item) / cell));
                if (h !== currentH) {
                    updates.push({ grid: grid, item: item, h: h });
                }
            });
        });
        updates.forEach(function (u) {
            u.grid.update(u.item, { h: u.h });
        });
    }

    function compactGrid(grid) {
        var nodes = ((grid.engine && grid.engine.nodes) || []).slice().sort(function (a, b) {
            return a.y - b.y || a.x - b.x;
        });
        var placed = [];
        function overlaps(x, y, w, h) {
            for (var i = 0; i < placed.length; i++) {
                var n = placed[i];
                if (x < n.x + n.w && x + w > n.x && y < n.y + n.h && y + h > n.y) {
                    return true;
                }
            }
            return false;
        }
        nodes.forEach(function (n) {
            var y = 0;
            while (overlaps(n.x, y, n.w, n.h)) {
                y += 1;
            }
            if (n.el && y !== n.y) {
                grid.update(n.el, { y: y });
            }
            placed.push({ x: n.x, y: y, w: n.w, h: n.h });
        });
    }

    function syncPageOneSideNote(grid) {
        if (!grid || !grid.el) {
            return;
        }
        var noteItem = null;
        grid.el.querySelectorAll('.grid-stack-item[data-block-type="text"]').forEach(function (item) {
            var node = item.gridstackNode || {};
            if ((node.x || 0) >= GRID_COLUMNS / 2) {
                noteItem = item;
            }
        });
        if (!noteItem) {
            return;
        }
        var noteNode = noteItem.gridstackNode || {};
        var leftBottom = 0;
        grid.el.querySelectorAll('.grid-stack-item[data-block-type="builtin_table"]').forEach(function (item) {
            var node = item.gridstackNode || {};
            if ((node.x || 0) !== 0) {
                return;
            }
            leftBottom = Math.max(leftBottom, (node.y || 0) + (node.h || 1));
        });
        var noteY = noteNode.y || 0;
        var noteW = noteNode.w || parseInt(noteItem.getAttribute('gs-w') || '6', 10);
        var targetH = Math.max(1, leftBottom - noteY);
        if (!leftBottom) {
            return;
        }
        if ((noteNode.h || 0) !== targetH) {
            grid.update(noteItem, { h: targetH, w: noteW, y: 0, x: noteNode.x || GRID_COLUMNS / 2 });
        }
        noteItem.setAttribute('gs-w', String(noteW));
        noteItem.setAttribute('data-w', String(noteW));
        noteItem.setAttribute('gs-h', String(targetH));
        noteItem.setAttribute('data-h', String(targetH));
    }

    function compactAllGrids() {
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            if (el.gridstack) {
                compactGrid(el.gridstack);
            }
        });
    }

    function columnPx(grid) {
        var el = grid && grid.el;
        var width = el ? el.clientWidth : 0;
        return (width || 1) / GRID_COLUMNS;
    }

    function measureTableMaxContentWidth(item) {
        var table = item.querySelector('.report-js-table');
        if (!table) {
            return 0;
        }
        var clone = table.cloneNode(true);
        clone.style.cssText = 'position:absolute;left:-10000px;top:0;width:auto;max-width:none;table-layout:auto;visibility:hidden;';
        document.body.appendChild(clone);
        var width = clone.scrollWidth || clone.offsetWidth || 0;
        document.body.removeChild(clone);
        return width;
    }

    function contentFloor(grid, item) {
        var type = item.getAttribute('data-block-type');
        var cell = cellPx(grid);
        var col = columnPx(grid);
        var minH = 1;
        var minW = 1;
        if (type === 'builtin_table') {
            minH = Math.max(1, Math.ceil(measureContentPx(item) / cell));
            var nodeX = (item.gridstackNode && item.gridstackNode.x) || 0;
            minW = Math.max(1, Math.min(
                GRID_COLUMNS - nodeX,
                GRID_COLUMNS,
                Math.ceil(measureTableMaxContentWidth(item) / Math.max(col, 1))
            ));
        } else if (type === 'text') {
            minH = Math.max(1, Math.ceil((measureContentPx(item) + 12) / cell));
            minW = 1;
        } else if (type === 'image') {
            minH = 1;
            minW = 1;
        }
        return { minW: minW, minH: minH };
    }

    function applyContentFloors(grid) {
        if (!grid || !grid.el) {
            return;
        }
        grid.el.querySelectorAll('.grid-stack-item').forEach(function (item) {
            var node = item.gridstackNode || {};
            var type = item.getAttribute('data-block-type');
            var minH = node.h || 1;
            var minW = node.w || 1;
            if (type === 'text') {
                minH = Math.max(1, minH);
                minW = 1;
            } else if (type === 'image') {
                minH = 1;
                minW = 1;
            } else if (type === 'builtin_table') {
                minH = Math.max(1, node.h || 1);
                minW = Math.max(1, node.w || 1);
            }
            grid.update(item, { minW: minW, minH: minH });
        });
    }

    function paperHasOverflow(paper) {
        if (!paper || paper.getAttribute('data-hydrated') !== '1') {
            return false;
        }
        var pr = paper.getBoundingClientRect();
        if (pr.width < 2 || pr.height < 2) {
            return false;
        }
        var items = paper.querySelectorAll('.grid-stack-item');
        for (var i = 0; i < items.length; i++) {
            var r = items[i].getBoundingClientRect();
            if (r.width < 1 || r.height < 1) {
                continue;
            }
            if (r.left < pr.left - 4 || r.right > pr.right + 4 || r.top < pr.top - 4 || r.bottom > pr.bottom + 4) {
                return true;
            }
        }
        return false;
    }

    function markPaperOverflow() {
        document.querySelectorAll('#report-papers .report-paper').forEach(function (paper, index) {
            var overflow = paperHasOverflow(paper);
            paper.classList.toggle('is-overflowing', overflow);
            var btn = document.querySelector('#report-page-list .report-page-btn[data-page-index="' + index + '"]');
            if (btn) {
                btn.classList.toggle('is-overflowing', overflow);
            }
        });
    }

    function anyPaperOverflowing() {
        markPaperOverflow();
        return !!document.querySelector('#report-papers .report-paper.is-overflowing');
    }

    function syncPageListSticky() {
        var toolbar = document.getElementById('report-toolbar');
        var list = document.getElementById('report-page-list');
        if (!toolbar || !list) {
            return;
        }
        var height = toolbar.offsetHeight || 0;
        if (height < 8) {
            return;
        }
        var mb = parseFloat(window.getComputedStyle(toolbar).marginBottom);
        var gap = isNaN(mb) ? 16 : mb;
        var offset = height + gap;
        var key = String(Math.round(offset));
        if (key === lastStickyKey) {
            return;
        }
        lastStickyKey = key;
        list.style.marginTop = offset + 'px';
        list.style.top = (8 + offset) + 'px';
    }

    function bindPageListSticky() {
        var toolbar = document.getElementById('report-toolbar');
        var workspace = document.getElementById('report-workspace');
        if (!toolbar || !workspace) {
            return;
        }
        workspace.dataset.stickyBound = '1';
        syncPageListSticky();
    }

    function imageAspect(item) {
        var raw = parseFloat(item.getAttribute('data-aspect') || '');
        if (raw && isFinite(raw) && raw > 0) {
            return raw;
        }
        var img = item.querySelector('img.report-image-block');
        if (img && img.naturalWidth && img.naturalHeight) {
            return img.naturalWidth / img.naturalHeight;
        }
        return 1;
    }

    var imageSnapLock = false;

    function snapImageAspect(grid, item) {
        if (!grid || !item || imageSnapLock) {
            return;
        }
        var node = item.gridstackNode || {};
        var w = node.w || parseInt(item.getAttribute('gs-w') || '1', 10);
        var h = node.h || parseInt(item.getAttribute('gs-h') || '1', 10);
        var aspect = imageAspect(item);
        var col = columnPx(grid);
        var cell = cellPx(grid);
        var fromW = Math.max(1, Math.round((w * col) / aspect / cell));
        imageSnapLock = true;
        if (fromW !== h) {
            grid.update(item, { h: fromW });
        }
        imageSnapLock = false;
    }

    function sizeImageForGrid(grid, natW, natH, maxRows) {
        var col = columnPx(grid);
        var cell = cellPx(grid);
        var aspect = natW / Math.max(1, natH);
        function fits(w, h) {
            if (h > maxRows || w > GRID_COLUMNS) {
                return false;
            }
            var slot = findFit(grid, w, h, maxRows);
            return !!(slot && !slot.clip);
        }
        var origW = Math.min(GRID_COLUMNS, Math.max(1, Math.round(natW / col)));
        var origH = Math.max(1, Math.round((origW * col) / aspect / cell));
        if (fits(origW, origH)) {
            return { w: origW, h: origH };
        }
        var w;
        for (w = GRID_COLUMNS; w >= 1; w--) {
            var h = Math.max(1, Math.round((w * col) / aspect / cell));
            if (fits(w, h)) {
                return { w: w, h: h };
            }
        }
        return null;
    }

    function loadImageNaturalSize(src) {
        return new Promise(function (resolve) {
            var img = new Image();
            img.onload = function () {
                resolve({
                    w: Math.max(1, img.naturalWidth || 1),
                    h: Math.max(1, img.naturalHeight || 1)
                });
            };
            img.onerror = function () {
                resolve({ w: 1, h: 1 });
            };
            img.src = src;
        });
    }

    var reportFontBinary = null;
    var reportFontLoading = null;

    function arrayBufferToBase64(buffer) {
        var binary = '';
        var bytes = new Uint8Array(buffer);
        var len = bytes.byteLength;
        for (var i = 0; i < len; i += 0x8000) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + 0x8000, len)));
        }
        return window.btoa(binary);
    }

    function loadReportFont() {
        if (reportFontBinary) {
            return Promise.resolve(reportFontBinary);
        }
        if (reportFontLoading) {
            return reportFontLoading;
        }
        reportFontLoading = fetch(REPORT_FONT_URL).then(function (res) {
            if (!res.ok) {
                throw new Error('font ' + res.status);
            }
            return res.arrayBuffer();
        }).then(function (buf) {
            reportFontBinary = arrayBufferToBase64(buf);
            return reportFontBinary;
        }).catch(function (err) {
            reportFontLoading = null;
            throw err;
        });
        return reportFontLoading;
    }

    var pdfFontOk = false;

    function registerReportFont(pdf) {
        pdfFontOk = false;
        if (!reportFontBinary) {
            pdf.setFont('helvetica', 'normal');
            return;
        }
        pdf.addFileToVFS('NotoSansTC-Regular.ttf', reportFontBinary);
        pdf.addFont('NotoSansTC-Regular.ttf', REPORT_FONT_NAME, 'normal');
        try {
            pdf.setFont(REPORT_FONT_NAME, 'normal');
            pdfFontOk = pdf.getTextWidth('Score') > 0;
        } catch (err) {
            pdfFontOk = false;
        }
        if (!pdfFontOk) {
            pdf.setFont('helvetica', 'normal');
        }
    }

    function parseRgb(color) {
        if (!color || color === 'transparent' || color === 'rgba(0, 0, 0, 0)') {
            return null;
        }
        var s = String(color).trim();
        if (s.indexOf('#') === 0) {
            var hex = s.slice(1);
            if (hex.length === 3) {
                hex = hex.split('').map(function (c) { return c + c; }).join('');
            }
            if (hex.length === 6) {
                return [
                    parseInt(hex.slice(0, 2), 16),
                    parseInt(hex.slice(2, 4), 16),
                    parseInt(hex.slice(4, 6), 16)
                ];
            }
        }
        var m = s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!m) {
            return null;
        }
        return [Number(m[1]), Number(m[2]), Number(m[3])];
    }

    function paperScale(paperRect) {
        return {
            x: paperRect.width ? (A4_WIDTH_MM / paperRect.width) : 1,
            y: paperRect.height ? (A4_HEIGHT_MM / paperRect.height) : 1
        };
    }

    function paperOffsheet(box) {
        return box.y >= A4_HEIGHT_MM || box.x >= A4_WIDTH_MM || box.w <= 0 || box.h <= 0;
    }

    function scaleXY(scale) {
        if (scale && typeof scale === 'object') {
            return { x: scale.x || 1, y: scale.y || 1 };
        }
        var n = Number(scale) || 1;
        return { x: n, y: n };
    }

    function boxMm(paperRect, el, scale) {
        var s = scaleXY(scale);
        var r = el.getBoundingClientRect();
        return {
            x: (r.left - paperRect.left) * s.x,
            y: (r.top - paperRect.top) * s.y,
            w: r.width * s.x,
            h: r.height * s.y
        };
    }

    function pxToPt(px, scale) {
        var s = scaleXY(scale);
        return Math.max(5, px * ((s.x + s.y) / 2) * 72 / 25.4);
    }

    function fontWeightNum(style) {
        if (!style || style.fontWeight == null) {
            return 400;
        }
        var w = style.fontWeight;
        if (w === 'bold' || w === 'bolder') {
            return 700;
        }
        if (w === 'normal' || w === 'lighter') {
            return 400;
        }
        var n = parseInt(w, 10);
        return isNaN(n) ? 400 : n;
    }

    var PDF_FAKE_BOLD_MM = 0.15;

    function fitText(pdf, text, maxW) {
        if (!text) {
            return '';
        }
        if (pdf.getTextWidth(text) <= maxW) {
            return text;
        }
        var s = text;
        while (s.length && pdf.getTextWidth(s + '…') > maxW) {
            s = s.slice(0, -1);
        }
        return s ? s + '…' : '';
    }

    function isMostlyWhite(rgb) {
        return rgb && rgb[0] >= 248 && rgb[1] >= 248 && rgb[2] >= 248;
    }

    function drawPdfText(pdf, text, x, y, opts) {
        var options = opts || {};
        var bold = !!options.bold;
        var pdfOpts = {};
        Object.keys(options).forEach(function (key) {
            if (key !== 'bold') {
                pdfOpts[key] = options[key];
            }
        });
        try {
            pdf.setFont(pdfFontOk ? REPORT_FONT_NAME : 'helvetica', 'normal');
        } catch (err) {
            pdf.setFont('helvetica', 'normal');
        }
        function paint(dx) {
            try {
                pdf.text(text, x + dx, y, pdfOpts);
            } catch (err) {
                pdf.setFont('helvetica', 'normal');
                pdf.text(text, x + dx, y, pdfOpts);
            }
        }
        paint(0);
        if (bold) {
            paint(PDF_FAKE_BOLD_MM);
        }
    }

    function drawHeader(pdf, paper, paperRect, scale) {
        var title = paper.querySelector('.report-header-title');
        var meta = paper.querySelector('.report-header-meta');
        [title, meta].forEach(function (el) {
            if (!el) {
                return;
            }
            var text = (el.textContent || '').trim();
            if (!text) {
                return;
            }
            var style = window.getComputedStyle(el);
            var box = boxMm(paperRect, el, scale);
            var color = parseRgb(style.color) || [15, 23, 42];
            pdf.setTextColor(color[0], color[1], color[2]);
            pdf.setFontSize(pxToPt(parseFloat(style.fontSize) || 13, scale));
            drawPdfText(pdf, text, box.x + box.w / 2, box.y + box.h / 2, {
                baseline: 'middle',
                align: 'center',
                bold: fontWeightNum(style) >= 600
            });
        });
    }

    function drawFilledCircle(pdf, box, rgb) {
        var radius = Math.min(box.w, box.h) / 2;
        if (radius <= 0) {
            return;
        }
        pdf.setFillColor(rgb[0], rgb[1], rgb[2]);
        pdf.circle(box.x + box.w / 2, box.y + box.h / 2, radius, 'F');
    }

    function drawStarterCircle(pdf, box, rgb) {
        var radius = Math.min(box.w, box.h) * 0.22;
        radius = Math.max(0.35, Math.min(radius, 1.1));
        pdf.setDrawColor(rgb[0], rgb[1], rgb[2]);
        pdf.setLineWidth(0.28);
        pdf.circle(box.x + box.w / 2, box.y + box.h / 2, radius, 'S');
    }

    function isStarterMark(text) {
        return text === '\u25CB' || text === '○';
    }

    function drawTitleDot(pdf, dot, paperRect, scale) {
        var box = boxMm(paperRect, dot, scale);
        if (paperOffsheet(box)) {
            return;
        }
        var style = window.getComputedStyle(dot);
        var fill = parseRgb(style.backgroundColor) || [0, 180, 216];
        drawFilledCircle(pdf, box, fill);
    }

    function drawTableCell(pdf, cell, paperRect, scale) {
        var box = boxMm(paperRect, cell, scale);
        if (paperOffsheet(box)) {
            return;
        }
        var style = window.getComputedStyle(cell);
        var fill = parseRgb(style.backgroundColor);
        if (fill && !isMostlyWhite(fill)) {
            pdf.setFillColor(fill[0], fill[1], fill[2]);
            pdf.rect(box.x, box.y, box.w, box.h, 'F');
        }
        var border = parseRgb(style.borderTopColor) || [222, 226, 230];
        pdf.setDrawColor(border[0], border[1], border[2]);
        pdf.setLineWidth(0.12);
        pdf.rect(box.x, box.y, box.w, box.h, 'S');
        var text = (cell.innerText || '').replace(/\s+/g, ' ').trim();
        if (!text) {
            return;
        }
        var color = parseRgb(style.color) || [15, 23, 42];
        if (isStarterMark(text)) {
            drawStarterCircle(pdf, box, color);
            return;
        }
        pdf.setTextColor(color[0], color[1], color[2]);
        pdf.setFontSize(pxToPt(parseFloat(style.fontSize) || 9, scale));
        var pad = 0.4;
        var maxW = Math.max(0.4, box.w - pad * 2);
        var fitted = fitText(pdf, text, maxW);
        if (!fitted) {
            return;
        }
        var align = style.textAlign;
        var x = box.x + pad;
        var pdfAlign = 'left';
        if (align === 'center') {
            x = box.x + box.w / 2;
            pdfAlign = 'center';
        } else if (align === 'right' || align === 'end') {
            x = box.x + box.w - pad;
            pdfAlign = 'right';
        }
        drawPdfText(pdf, fitted, x, box.y + box.h / 2, {
            baseline: 'middle',
            align: pdfAlign,
            bold: fontWeightNum(style) >= 600
        });
    }

    function toRoman(num) {
        var romans = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'];
        return (num >= 1 && num <= 10) ? romans[num - 1] : String(num);
    }

    function toAlpha(num) {
        var alpha = 'abcdefghijklmnopqrstuvwxyz';
        return (num >= 1 && num <= 26) ? alpha[num - 1] : String(num);
    }

    function drawNote(pdf, note, paperRect, scale) {
        var box = boxMm(paperRect, note, scale);
        var baseStyle = window.getComputedStyle(note);
        var baseFontPx = parseFloat(baseStyle.fontSize) || 13;
        var baseLinePx = parseFloat(baseStyle.lineHeight);
        if (!baseLinePx || isNaN(baseLinePx)) {
            baseLinePx = baseFontPx * 1.45;
        }
        var sy = scaleXY(scale).y;
        var lineH = baseLinePx * sy;
        var ptSize = pxToPt(baseFontPx, scale);
        var maxY = Math.min(A4_HEIGHT_MM, box.y + box.h);
        var cursorY = box.y;

        function collectLines() {
            var lines = [];
            var defaultColor = parseRgb(baseStyle.color) || [15, 23, 42];

            function extractSpans(rootEl, baseInherited) {
                var spans = [];
                function traverse(node, currentStyle) {
                    if (node.nodeType === 3) {
                        var text = node.textContent || '';
                        if (!text) return;
                        pdf.setFontSize(ptSize);
                        var words = text.split(/( +|\n)/);
                        words.forEach(function (w) {
                            if (!w) return;
                            spans.push({
                                text: w,
                                color: currentStyle.color,
                                bgColor: currentStyle.bgColor,
                                bold: currentStyle.bold,
                                italic: currentStyle.italic,
                                underline: currentStyle.underline,
                                strikethrough: currentStyle.strikethrough,
                                width: (w === '\n') ? 0 : pdf.getTextWidth(w)
                            });
                        });
                        return;
                    }
                    if (node.nodeType === 1) {
                        var tag = node.tagName.toLowerCase();
                        if (tag === 'br') {
                            spans.push({ text: '\n', width: 0 });
                            return;
                        }
                        var sColor = currentStyle.color;
                        var sBg = currentStyle.bgColor;
                        var sBold = currentStyle.bold || tag === 'b' || tag === 'strong';
                        var sItalic = currentStyle.italic || tag === 'i' || tag === 'em';
                        var sUnderline = currentStyle.underline || tag === 'u';
                        var sStrike = currentStyle.strikethrough || tag === 's' || tag === 'strike';

                        var nodeColor = null;
                        if (tag === 'font' && node.getAttribute('color')) {
                            nodeColor = parseRgb(node.getAttribute('color'));
                        } else if (node.style && node.style.color) {
                            nodeColor = parseRgb(node.style.color);
                        } else if (node.getAttribute && node.getAttribute('color')) {
                            nodeColor = parseRgb(node.getAttribute('color'));
                        }
                        if (nodeColor) {
                            sColor = nodeColor;
                        }

                        var nodeBg = null;
                        if (node.style && node.style.backgroundColor) {
                            nodeBg = parseRgb(node.style.backgroundColor);
                        } else if (node.getAttribute && node.getAttribute('data-highlight')) {
                            nodeBg = parseRgb(node.getAttribute('data-highlight'));
                        }
                        if (nodeBg) {
                            sBg = nodeBg;
                        }

                        if (node.style && node.style.textDecoration && node.style.textDecoration.indexOf('underline') !== -1) sUnderline = true;
                        if (node.style && node.style.textDecoration && node.style.textDecoration.indexOf('line-through') !== -1) sStrike = true;

                        var nextStyle = {
                            color: sColor,
                            bgColor: sBg,
                            bold: sBold,
                            italic: sItalic,
                            underline: sUnderline,
                            strikethrough: sStrike
                        };

                        Array.from(node.childNodes).forEach(function (child) {
                            traverse(child, nextStyle);
                        });
                    }
                }
                traverse(rootEl, baseInherited);
                return spans;
            }

            function wrapSpansToLines(spans, indentLevel, listType, listIndex) {
                var maxW = Math.max(10, box.w - indentLevel * 5.0);
                var curLine = [];
                var curWidth = 0;
                var isFirst = true;

                spans.forEach(function (span) {
                    if (span.text === '\n') {
                        if (curLine.length > 0) {
                            lines.push({
                                spans: curLine,
                                indentLevel: indentLevel,
                                listType: isFirst ? listType : null,
                                listIndex: isFirst ? listIndex : null
                            });
                            curLine = [];
                            curWidth = 0;
                            isFirst = false;
                        }
                        return;
                    }
                    if (curWidth + span.width > maxW && curLine.length > 0 && span.text.trim()) {
                        lines.push({
                            spans: curLine,
                            indentLevel: indentLevel,
                            listType: isFirst ? listType : null,
                            listIndex: isFirst ? listIndex : null
                        });
                        curLine = [];
                        curWidth = 0;
                        isFirst = false;
                    }
                    curLine.push(span);
                    curWidth += span.width;
                });

                if (curLine.length > 0) {
                    lines.push({
                        spans: curLine,
                        indentLevel: indentLevel,
                        listType: isFirst ? listType : null,
                        listIndex: isFirst ? listIndex : null
                    });
                }
            }

            function getListIndent(el) {
                var level = 0;
                var p = el.parentElement;
                while (p && p !== note) {
                    var pt = p.tagName ? p.tagName.toLowerCase() : '';
                    if (pt === 'ul' || pt === 'ol' || pt === 'blockquote') {
                        level++;
                    }
                    p = p.parentElement;
                }
                return Math.max(1, level);
            }

            function getListIndex(liEl) {
                var idx = 1;
                var prev = liEl.previousElementSibling;
                while (prev) {
                    if (prev.tagName && prev.tagName.toLowerCase() === 'li') idx++;
                    prev = prev.previousElementSibling;
                }
                return idx;
            }

            // Check if note has block children or is raw inline text
            var directBlocks = Array.from(note.children);
            var isComplex = directBlocks.some(function (c) {
                var t = c.tagName ? c.tagName.toLowerCase() : '';
                return t === 'p' || t === 'div' || t === 'ul' || t === 'ol' || t === 'blockquote';
            });

            var initStyle = {
                color: defaultColor,
                bgColor: null,
                bold: false,
                italic: false,
                underline: false,
                strikethrough: false
            };

            if (!isComplex) {
                var allSpans = extractSpans(note, initStyle);
                wrapSpansToLines(allSpans, 0, null, null);
            } else {
                function processBlockNode(node) {
                    if (node.nodeType === 3) {
                        var text = (node.textContent || '').trim();
                        if (text) {
                            var rawSpans = extractSpans(node, initStyle);
                            wrapSpansToLines(rawSpans, 0, null, null);
                        }
                        return;
                    }
                    if (node.nodeType !== 1) return;
                    var tag = node.tagName.toLowerCase();
                    if (tag === 'li') {
                        var parentTag = node.parentElement ? node.parentElement.tagName.toLowerCase() : 'ul';
                        var isUl = (parentTag === 'ul');
                        var level = getListIndent(node);
                        var idx = isUl ? null : getListIndex(node);
                        
                        // Extract spans of only direct text and non-list inline children
                        var liSpans = [];
                        Array.from(node.childNodes).forEach(function (child) {
                            var childTag = (child.nodeType === 1) ? child.tagName.toLowerCase() : '';
                            if (childTag !== 'ul' && childTag !== 'ol' && childTag !== 'blockquote') {
                                extractSpans(child, initStyle).forEach(function (sp) {
                                    liSpans.push(sp);
                                });
                            }
                        });
                        wrapSpansToLines(liSpans, level, isUl ? 'ul' : 'ol', idx);
                        
                        // Process nested lists inside this li
                        Array.from(node.childNodes).forEach(function (child) {
                            var childTag = (child.nodeType === 1) ? child.tagName.toLowerCase() : '';
                            if (childTag === 'ul' || childTag === 'ol' || childTag === 'blockquote') {
                                processBlockNode(child);
                            }
                        });
                    } else if (tag === 'p' || tag === 'div') {
                        var pSpans = [];
                        Array.from(node.childNodes).forEach(function (child) {
                            var childTag = (child.nodeType === 1) ? child.tagName.toLowerCase() : '';
                            if (childTag !== 'ul' && childTag !== 'ol' && childTag !== 'blockquote' && childTag !== 'p' && childTag !== 'div') {
                                extractSpans(child, initStyle).forEach(function (sp) {
                                    pSpans.push(sp);
                                });
                            }
                        });
                        var hasVisibleText = pSpans.some(function (sp) {
                            return sp.text && sp.text.trim().length > 0;
                        });
                        if (hasVisibleText) {
                            wrapSpansToLines(pSpans, 0, null, null);
                        } else {
                            // Blank line for empty paragraph (<p></p>, <p><br></p>, <p>&nbsp;</p>)
                            lines.push({
                                spans: [{ text: ' ', width: 0, color: defaultColor }],
                                indentLevel: 0,
                                listType: null,
                                listIndex: null
                            });
                        }
                        Array.from(node.childNodes).forEach(function (child) {
                            var childTag = (child.nodeType === 1) ? child.tagName.toLowerCase() : '';
                            if (childTag === 'ul' || childTag === 'ol' || childTag === 'blockquote' || childTag === 'p' || childTag === 'div') {
                                processBlockNode(child);
                            }
                        });
                    } else if (tag === 'br') {
                        lines.push({
                            spans: [{ text: ' ', width: 0, color: defaultColor }],
                            indentLevel: 0,
                            listType: null,
                            listIndex: null
                        });
                    } else if (tag === 'ul' || tag === 'ol' || tag === 'blockquote') {
                        Array.from(node.children).forEach(function (child) {
                            processBlockNode(child);
                        });
                    } else {
                        var genericSpans = extractSpans(node, initStyle);
                        wrapSpansToLines(genericSpans, 0, null, null);
                    }
                }

                Array.from(note.childNodes).forEach(function (child) {
                    processBlockNode(child);
                });
            }

            return lines;
        }

        var allLines = collectLines();

        allLines.forEach(function (lineInfo) {
            if (cursorY >= maxY) {
                return;
            }
            var indentX = box.x + (lineInfo.indentLevel || 0) * 5.0;
            var startX = indentX;

            // Draw bullet marker or ordered list number
            if (lineInfo.listType) {
                var level = lineInfo.indentLevel || 1;
                pdf.setFontSize(ptSize);
                pdf.setTextColor(15, 23, 42);
                if (lineInfo.listType === 'ul') {
                    if (level === 1) {
                        // Level 1: solid disc
                        pdf.setFillColor(15, 23, 42);
                        pdf.circle(startX - 2.5, cursorY + lineH * 0.45, 0.6, 'F');
                    } else if (level === 2) {
                        // Level 2: circle (hollow)
                        pdf.setDrawColor(15, 23, 42);
                        pdf.setLineWidth(0.15);
                        pdf.circle(startX - 2.5, cursorY + lineH * 0.45, 0.6, 'S');
                    } else {
                        // Level 3+: square
                        pdf.setFillColor(15, 23, 42);
                        pdf.rect(startX - 3.1, cursorY + lineH * 0.45 - 0.5, 1.0, 1.0, 'F');
                    }
                } else if (lineInfo.listType === 'ol') {
                    var numStr = '';
                    if (level === 1) {
                        numStr = String(lineInfo.listIndex || 1) + '.';
                    } else if (level === 2) {
                        numStr = toAlpha(lineInfo.listIndex || 1) + '.';
                    } else {
                        numStr = toRoman(lineInfo.listIndex || 1) + '.';
                    }
                    drawPdfText(pdf, numStr, startX - pdf.getTextWidth(numStr) - 1.2, cursorY, { baseline: 'top' });
                }
            }

            var spanX = startX;
            lineInfo.spans.forEach(function (span) {
                if (!span.text) return;
                var sWidth = span.width || pdf.getTextWidth(span.text);

                // Draw highlight background rect
                if (span.bgColor) {
                    pdf.setFillColor(span.bgColor[0], span.bgColor[1], span.bgColor[2]);
                    pdf.rect(spanX, cursorY, sWidth, lineH * 0.95, 'F');
                }

                // Text styling
                pdf.setTextColor(span.color[0], span.color[1], span.color[2]);
                pdf.setFontSize(ptSize);
                drawPdfText(pdf, span.text, spanX, cursorY, {
                    baseline: 'top',
                    bold: !!span.bold
                });

                // Underline
                if (span.underline) {
                    pdf.setDrawColor(span.color[0], span.color[1], span.color[2]);
                    pdf.setLineWidth(0.2);
                    pdf.line(spanX, cursorY + lineH * 0.82, spanX + sWidth, cursorY + lineH * 0.82);
                }

                // Strikethrough
                if (span.strikethrough) {
                    pdf.setDrawColor(span.color[0], span.color[1], span.color[2]);
                    pdf.setLineWidth(0.2);
                    pdf.line(spanX, cursorY + lineH * 0.45, spanX + sWidth, cursorY + lineH * 0.45);
                }

                spanX += sWidth;
            });

            cursorY += lineH;
        });
    }

    function drawImageBlock(pdf, img, paperRect, scale) {
        if (!img || !img.src) {
            return;
        }
        var box = boxMm(paperRect, img, scale);
        if (box.w <= 0 || box.h <= 0 || box.y >= A4_HEIGHT_MM) {
            return;
        }
        var dataUrl = img.src;
        try {
            if (dataUrl.indexOf('image/png') === -1) {
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth || Math.max(1, img.width);
                canvas.height = img.naturalHeight || Math.max(1, img.height);
                canvas.getContext('2d').drawImage(img, 0, 0);
                dataUrl = canvas.toDataURL('image/png');
            }
            pdf.addImage(dataUrl, 'PNG', box.x, box.y, box.w, Math.min(box.h, A4_HEIGHT_MM - box.y));
        } catch (err) {
            console.warn('PDF image skipped', err);
        }
    }

    function drawPaper(pdf, paper) {
        var paperRect = paper.getBoundingClientRect();
        if (!paperRect.width) {
            return;
        }
        var scale = paperScale(paperRect);
        pdf.setFillColor(255, 255, 255);
        pdf.rect(0, 0, A4_WIDTH_MM, A4_HEIGHT_MM, 'F');
        drawHeader(pdf, paper, paperRect, scale);
        paper.querySelectorAll('.grid-stack-item').forEach(function (item) {
            if (item.hidden) {
                return;
            }
            var title = item.querySelector('.report-block-title');
            if (title) {
                var titleText = (title.textContent || '').trim();
                var tBox = boxMm(paperRect, title, scale);
                var tStyle = window.getComputedStyle(title);
                var tColor = parseRgb(tStyle.color) || [15, 23, 42];
                var textX = tBox.x;
                var dot = title.querySelector('.report-block-title-dot');
                if (dot) {
                    drawTitleDot(pdf, dot, paperRect, scale);
                    var dBox = boxMm(paperRect, dot, scale);
                    textX = dBox.x + dBox.w + 2;
                }
                if (titleText) {
                    pdf.setTextColor(tColor[0], tColor[1], tColor[2]);
                    pdf.setFontSize(pxToPt(parseFloat(tStyle.fontSize) || 12, scale));
                    drawPdfText(pdf, titleText, textX, tBox.y + tBox.h / 2, {
                        baseline: 'middle',
                        bold: fontWeightNum(tStyle) >= 600
                    });
                }
            }
            item.querySelectorAll('th, td').forEach(function (cell) {
                drawTableCell(pdf, cell, paperRect, scale);
            });
            var note = item.querySelector('[data-text-block]');
            if (note) {
                drawNote(pdf, note, paperRect, scale);
            }
            var img = item.querySelector('img.report-image-block');
            if (img) {
                drawImageBlock(pdf, img, paperRect, scale);
            }
        });
    }

    function setPdfBusy(busy) {
        var btn = document.getElementById('btn-export-pdf');
        if (!btn) {
            return;
        }
        btn.disabled = !!busy;
        if (busy) {
            btn.setAttribute('aria-busy', 'true');
        } else {
            btn.removeAttribute('aria-busy');
        }
    }

    function exportPapersToPdf() {
        var btn = document.getElementById('btn-export-pdf');
        if (btn && btn.getAttribute('aria-busy') === 'true') {
            return Promise.resolve();
        }
        var papers = document.querySelectorAll('#report-papers .report-paper');
        if (!papers.length) {
            window.print();
            return Promise.resolve();
        }
        setPdfBusy(true);
        return ensureReportLibs().then(function () {
            if (!window.jspdf || !window.jspdf.jsPDF) {
                throw new Error('jspdf missing');
            }
            return loadReportFont();
        }).then(function () {
            var JsPDF = window.jspdf.jsPDF;
            var pdf = new JsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
            registerReportFont(pdf);
            var chain = Promise.resolve();
            Array.prototype.forEach.call(papers, function (paper, index) {
                chain = chain.then(function () {
                    return hydratePage(index);
                }).then(function () {
                    if (index > 0) {
                        pdf.addPage('a4', 'portrait');
                    }
                    drawPaper(pdf, paper);
                });
            });
            return chain.then(function () {
                var nameEl = document.getElementById('report-pdf-filename');
                var filename = (nameEl && (nameEl.textContent || '').trim()) || 'splashboard-report.pdf';
                pdf.save(filename);
            });
        }).catch(function (err) {
            console.warn('PDF export failed, using print()', err && (err.message || String(err)));
            window.print();
        }).then(function () {
            setPdfBusy(false);
        });
    }

    var dialogResolve = null;

    function setPageIds(ids) {
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('report-page-ids', { data: ids });
            return true;
        }
        return false;
    }

    function dispatchPageCmd(cmd) {
        if (!window.dash_clientside || typeof window.dash_clientside.set_props !== 'function') {
            return false;
        }
        cmd = cmd || {};
        cmd.t = Date.now();
        if (cmd.ids) {
            window.dash_clientside.set_props('report-page-ids', { data: cmd.ids });
        }
        window.dash_clientside.set_props('report-page-cmd', { data: cmd });
        return true;
    }

    function currentPaperIds() {
        var papers = document.querySelectorAll('#report-papers .report-paper');
        return Array.prototype.map.call(papers, paperPageId);
    }

    function paperPageId(paper) {
        if (!paper) {
            return '';
        }
        var id = paper.getAttribute('id') || '';
        return id.indexOf('report-paper-') === 0 ? id.slice('report-paper-'.length) : id;
    }

    function layoutPageForPaper(layout, paper) {
        var pid = paperPageId(paper);
        var pages = (layout && layout.pages) || [];
        var i;
        for (i = 0; i < pages.length; i++) {
            if (pages[i] && pages[i].id === pid) {
                return pages[i];
            }
        }
        return { id: pid, blocks: [] };
    }

    function paperNodes() {
        return Array.prototype.slice.call(
            document.querySelectorAll('#report-papers .report-paper')
        );
    }

    function waitForPaperCount(n, timeoutMs) {
        return new Promise(function (resolve) {
            var start = Date.now();
            function check() {
                if (paperNodes().length === n) {
                    resolve(true);
                    return;
                }
                if (Date.now() - start > (timeoutMs || 4000)) {
                    resolve(false);
                    return;
                }
                requestAnimationFrame(check);
            }
            check();
        });
    }

    function waitForNewPapers(oldNodes, n, timeoutMs) {
        oldNodes = oldNodes || [];
        return new Promise(function (resolve) {
            var start = Date.now();
            function isReplaced() {
                var papers = paperNodes();
                if (papers.length !== n) {
                    return false;
                }
                if (!oldNodes.length) {
                    return true;
                }
                return papers.every(function (paper) {
                    return oldNodes.indexOf(paper) === -1;
                });
            }
            function check() {
                if (isReplaced()) {
                    resolve(true);
                    return;
                }
                if (Date.now() - start > (timeoutMs || 4000)) {
                    resolve(false);
                    return;
                }
                requestAnimationFrame(check);
            }
            check();
        });
    }

    function closeDialog(result) {
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('report-dialog-opened', { data: false });
        }
        var resolve = dialogResolve;
        dialogResolve = null;
        if (resolve) {
            resolve(!!result);
        }
    }

    function askConfirm(message, okLabel) {
        return new Promise(function (resolve) {
            if (!window.dash_clientside || typeof window.dash_clientside.set_props !== 'function') {
                resolve(false);
                return;
            }
            dialogResolve = resolve;
            window.dash_clientside.set_props('report-dialog-opened', { data: true });
            window.setTimeout(function () {
                var msg = document.getElementById('report-dialog-message');
                var ok = document.getElementById('report-dialog-ok');
                if (msg) {
                    msg.textContent = message;
                }
                if (ok) {
                    ok.textContent = okLabel || 'OK';
                }
            }, 0);
        });
    }

    function addEmptyPaper() {
        var ids = currentPaperIds();
        var newId = uniqueId('page');
        ids.push(newId);
        if (!dispatchPageCmd({ op: 'add', id: newId, ids: ids })) {
            return Promise.resolve(null);
        }
        return waitForPaperCount(ids.length).then(function () {
            spyObservedCount = -1;
            hydrateLocks = {};
            refreshPageChrome();
            return document.querySelector('#report-papers .report-paper:last-child');
        });
    }

    function refreshPageChrome() {
        var papers = document.querySelectorAll('#report-papers .report-paper');
        var n = papers.length;
        papers.forEach(function (paper, index) {
            paper.setAttribute('data-page-index', String(index));
            var del = paper.querySelector('[data-delete-page], .report-page-delete');
            if (del) {
                del.setAttribute('data-delete-page', String(index));
                del.classList.toggle('is-disabled', n <= 1);
            }
        });
        setCurrentPage(clampPageIndex(currentPageIndex));
        markPaperOverflow();
        syncPageListSticky();
    }

    function applyStoredLayout(stored, compact) {
        if (!stored || !stored.pages || !stored.pages.length) {
            return Promise.resolve();
        }
        writeLayoutJson(stored);
        var ids = stored.pages.map(function (page, index) {
            return page.id || ('page-' + (index + 1));
        });
        var oldPapers = paperNodes();
        dispatchPageCmd({ op: 'reset', ids: ids });
        return waitForNewPapers(oldPapers, ids.length).then(function () {
            hydrateLocks = {};
            document.querySelectorAll('#report-papers .report-paper').forEach(function (paper) {
                paper.setAttribute('data-hydrated', '0');
                var gridEl = paper.querySelector('.report-grid');
                if (gridEl && gridEl.gridstack) {
                    gridEl.gridstack.removeAll();
                }
            });
            spyObservedCount = -1;
            var workspace = document.getElementById('report-workspace');
            if (workspace) {
                workspace.dataset.booted = '1';
                workspace.dataset.storedApplied = '1';
            }
            return hydratePage(activePageIndex(), { compact: !!compact }).then(function () {
                refreshPageChrome();
                initScrollSpy();
                persistLocal(readLayoutFromDom());
                window.setTimeout(function () {
                    markPaperOverflow();
                    syncPageListSticky();
                }, 300);
            });
        });
    }

    function addWidgetToActive(block) {
        var index = activePageIndex();
        hydratePage(index).then(function () {
            var node = widgetFromBlock(block);
            var grid = activeGrid();
            if (!grid || !node) {
                return;
            }
            var w = block.w || 6;
            var h = measureBlockH(block, grid, node);
            var slot = findFit(grid, w, h, paperMaxRows(grid));
            if (!slot) {
                persistLocal(readLayoutFromDom());
                return addEmptyPaper().then(function (paper) {
                    var papers = document.querySelectorAll('#report-papers .report-paper');
                    setCurrentPage(papers.length - 1);
                    initScrollSpy();
                    return hydratePage(papers.length - 1).then(function () {
                        grid = activeGrid();
                        if (!grid) {
                            return;
                        }
                        slot = findFit(grid, w, h, paperMaxRows(grid)) || { x: 0, y: 0 };
                        grid.addWidget(node, {
                            id: block.id,
                            x: slot.x,
                            y: slot.y,
                            w: w,
                            h: h,
                            minW: block.type === 'builtin_table' ? w : 1,
                            minH: block.type === 'image' ? 1 : (block.type === 'text' ? 1 : h)
                        });
                        bindTextBlocks(node);
                        node.setAttribute('data-min-h', String(block.type === 'text' || block.type === 'image' ? 1 : h));
                        node.setAttribute('data-min-w', block.type === 'builtin_table' ? String(w) : '1');
                        clampItemToPaper(grid, node);
                        persistLocal(readLayoutFromDom());
                        window.setTimeout(markPaperOverflow, 0);
                        if (paper) {
                            paper.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                    });
                });
            }
            grid.addWidget(node, {
                id: block.id,
                x: slot.x,
                y: slot.y,
                w: w,
                h: h,
                minW: block.type === 'builtin_table' ? w : 1,
                minH: block.type === 'image' ? 1 : (block.type === 'text' ? 1 : h)
            });
            bindTextBlocks(node);
            node.setAttribute('data-min-h', String(block.type === 'text' || block.type === 'image' ? 1 : h));
            node.setAttribute('data-min-w', block.type === 'builtin_table' ? String(w) : '1');
            clampItemToPaper(grid, node);
            persistLocal(readLayoutFromDom());
            window.setTimeout(markPaperOverflow, 0);
        });
    }

    window.splashboardReport = {
        skipFourFactorsGroup: skipFourFactorsGroup,
        groupedHeader: groupedHeader,
        paperScale: paperScale,
        loadStored: loadStored,
        readLayoutFromDom: readLayoutFromDom,
        persist: persistLocal,
        addPage: function () {
            return addEmptyPaper().then(function (paper) {
                var papers = document.querySelectorAll('#report-papers .report-paper');
                setCurrentPage(papers.length - 1);
                initScrollSpy();
                persistLocal(readLayoutFromDom());
                if (paper) {
                    paper.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
                return readLayoutFromDom();
            });
        },
        removePage: function (index, pageId) {
            var ids = currentPaperIds();
            if (ids.length <= 1) {
                return readLayoutFromDom();
            }
            if (pageId) {
                var found = ids.indexOf(pageId);
                if (found !== -1) {
                    index = found;
                }
            }
            if (typeof index !== 'number' || isNaN(index)) {
                index = currentPageIndex;
            }
            if (index < 0 || index >= ids.length) {
                return readLayoutFromDom();
            }
            var removedId = ids[index];
            persistLocal(readLayoutFromDom());
            ids.splice(index, 1);
            if (currentPageIndex === index) {
                currentPageIndex = index > 0 ? index - 1 : 0;
            } else if (currentPageIndex > index) {
                currentPageIndex = currentPageIndex - 1;
            }
            dispatchPageCmd({ op: 'delete', id: removedId, index: index, ids: ids });
            return waitForPaperCount(ids.length).then(function () {
                spyObservedCount = -1;
                hydrateLocks = {};
                document.querySelectorAll('#report-papers .report-paper').forEach(function (paper) {
                    if (paper.getAttribute('data-hydrated') !== '1') {
                        var gridEl = paper.querySelector('.report-grid');
                        if (gridEl) {
                            delete gridEl.dataset.gsInit;
                        }
                    }
                });
                initScrollSpy();
                return hydratePage(currentPageIndex).then(function () {
                    refreshPageChrome();
                    persistLocal(readLayoutFromDom());
                    var remaining = document.querySelectorAll('#report-papers .report-paper')[currentPageIndex];
                    if (remaining) {
                        remaining.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                    return readLayoutFromDom();
                });
            });
        },
        addText: function () {
            addWidgetToActive({
                id: uniqueId('text'),
                type: 'text',
                content: '',
                w: 5,
                h: 2
            });
            return readLayoutFromDom();
        },
        addTable: function (tableKey) {
            if (!tableKey) {
                return readLayoutFromDom();
            }
            addWidgetToActive({
                id: uniqueId('table'),
                type: 'builtin_table',
                table_key: tableKey,
                w: 12,
                h: 4
            });
            return readLayoutFromDom();
        },
        addImage: function (src) {
            if (!src) {
                return readLayoutFromDom();
            }
            loadImageNaturalSize(src).then(function (nat) {
                var index = activePageIndex();
                return hydratePage(index).then(function () {
                    markPaperOverflow();
                    var papers = document.querySelectorAll('#report-papers .report-paper');
                    var paper = papers[activePageIndex()];
                    var goNew = !paper || paperHasOverflow(paper);
                    var place = function () {
                        var grid = activeGrid();
                        if (!grid) {
                            return;
                        }
                        var maxRows = paperMaxRows(grid);
                        var size = sizeImageForGrid(grid, nat.w, nat.h, maxRows);
                        if (!size) {
                            return addEmptyPaper().then(function (newPaper) {
                                papers = document.querySelectorAll('#report-papers .report-paper');
                                setCurrentPage(papers.length - 1);
                                initScrollSpy();
                                return hydratePage(papers.length - 1).then(function () {
                                    grid = activeGrid();
                                    if (!grid) {
                                        return;
                                    }
                                    size = sizeImageForGrid(grid, nat.w, nat.h, paperMaxRows(grid))
                                        || { w: 1, h: 1 };
                                    addWidgetToActive({
                                        id: uniqueId('image'),
                                        type: 'image',
                                        src: src,
                                        w: size.w,
                                        h: size.h,
                                        aspect: nat.w / nat.h
                                    });
                                    if (newPaper) {
                                        newPaper.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                    }
                                });
                            });
                        }
                        addWidgetToActive({
                            id: uniqueId('image'),
                            type: 'image',
                            src: src,
                            w: size.w,
                            h: size.h,
                            aspect: nat.w / nat.h
                        });
                    };
                    if (goNew) {
                        return addEmptyPaper().then(function (newPaper) {
                            papers = document.querySelectorAll('#report-papers .report-paper');
                            setCurrentPage(papers.length - 1);
                            initScrollSpy();
                            return hydratePage(papers.length - 1).then(function () {
                                place();
                                if (newPaper) {
                                    newPaper.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                }
                            });
                        });
                    }
                    return place();
                });
            });
            return readLayoutFromDom();
        },
        resetLayout: function () {
            var el = document.getElementById('report-default-layout-json');
            var stored = null;
            try {
                stored = el && el.textContent ? JSON.parse(el.textContent) : null;
            } catch (err) {
                stored = null;
            }
            if (!stored || !stored.pages) {
                return readLayoutFromDom();
            }
            applyStoredLayout(stored, true);
            return readLayoutFromDom();
        },
        removeBlock: function (blockId) {
            var el = document.getElementById('gs-item-' + blockId);
            if (!el) {
                el = document.querySelector('.grid-stack-item[data-gs-id="' + blockId + '"]');
            }
            if (el) {
                var gridEl = el.closest('.report-grid');
                if (gridEl && gridEl.gridstack) {
                    gridEl.gridstack.removeWidget(el);
                } else {
                    el.remove();
                }
            }
            persistLocal(readLayoutFromDom());
            return readLayoutFromDom();
        },
        ensurePdfFont: function () {
            return loadReportFont();
        },
        exportPdf: function () {
            return exportPapersToPdf();
        },
        markOverflow: markPaperOverflow,
        syncSticky: syncPageListSticky
    };

    function validateImageFile(file) {
        if (!file || !ALLOWED_IMAGE_MIMES[file.type]) {
            return false;
        }
        if (!file.size || file.size > IMAGE_MAX_BYTES) {
            return false;
        }
        return true;
    }

    document.addEventListener('click', function (event) {
        var tableItem = event.target.closest('[data-add-table]');
        if (tableItem) {
            window.splashboardReport.addTable(tableItem.getAttribute('data-add-table'));
            closeTableMenu();
            return;
        }
        if (event.target.closest('#report-add-table')) {
            return;
        }
        if (event.target.closest('#report-add-text')) {
            window.splashboardReport.addText();
            return;
        }
        if (event.target.closest('#report-add-page')) {
            window.splashboardReport.addPage();
            return;
        }
        if (event.target.closest('#report-dialog-cancel')) {
            closeDialog(false);
            return;
        }
        if (event.target.closest('#report-dialog-ok')) {
            closeDialog(true);
            return;
        }
        if (event.target.closest('#report-dialog')) {
            return;
        }
        var rteCmd = event.target.closest('[data-rte-cmd]');
        if (rteCmd) {
            event.preventDefault();
            var cmd = rteCmd.getAttribute('data-rte-cmd');
            execNoteCommand(cmd);
            return;
        }
        var rteToggle = event.target.closest('[data-rte-toggle-menu]');
        if (rteToggle) {
            event.preventDefault();
            var mode = rteToggle.getAttribute('data-rte-toggle-menu');
            toggleColorMenu(mode);
            return;
        }
        var rteColor = event.target.closest('[data-rte-color]');
        if (rteColor) {
            event.preventDefault();
            var col = rteColor.getAttribute('data-rte-color');
            execNoteCommand('color', col);
            return;
        }
        var rteHighlight = event.target.closest('[data-rte-highlight]');
        if (rteHighlight) {
            event.preventDefault();
            var hcol = rteHighlight.getAttribute('data-rte-highlight');
            execNoteCommand('highlight', hcol);
            return;
        }
        if (!event.target.closest('.report-rte-dropdown-wrap')) {
            closeAllColorMenus();
        }
        if (event.target.closest('#report-reset-layout')) {
            askConfirm(
                'Reset to the default layout? This cannot be undone.',
                'Reset'
            ).then(function (ok) {
                if (ok) {
                    window.splashboardReport.resetLayout();
                }
            });
            return;
        }
        var deletePage = event.target.closest('.report-page-delete, [data-delete-page]');
        if (deletePage && !deletePage.disabled && !deletePage.classList.contains('is-disabled')) {
            var paper = deletePage.closest('#report-papers .report-paper');
            var papers = document.querySelectorAll('#report-papers .report-paper');
            var deleteIndex = paper ? Array.prototype.indexOf.call(papers, paper) : -1;
            if (deleteIndex < 0 || papers.length <= 1) {
                return;
            }
            var deleteId = paperPageId(paper);
            askConfirm('Delete this page?', 'Delete').then(function (ok) {
                if (ok) {
                    window.splashboardReport.removePage(deleteIndex, deleteId);
                }
            });
            return;
        }
        if (event.target.closest('#btn-export-pdf')) {
            if (anyPaperOverflowing()) {
                askConfirm(
                    'This export will crop content that sits outside A4.',
                    'Export'
                ).then(function (ok) {
                    if (ok) {
                        window.splashboardReport.exportPdf();
                    }
                });
            } else {
                window.splashboardReport.exportPdf();
            }
            return;
        }
        var pageBtn = event.target.closest('.report-page-btn[data-page-index]');
        if (pageBtn) {
            var index = parseInt(pageBtn.getAttribute('data-page-index'), 10);
            var papers = document.querySelectorAll('#report-papers .report-paper');
            if (papers[index]) {
                setCurrentPage(index);
                papers[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            return;
        }
        var removeBtn = event.target.closest('[data-remove-block]');
        if (removeBtn) {
            window.splashboardReport.removeBlock(removeBtn.getAttribute('data-remove-block'));
        }
    });

    document.addEventListener('change', function (event) {
        var customInput = event.target.closest('#report-custom-color, #report-custom-highlight, [data-rte-custom]');
        if (customInput) {
            var mode = customInput.id === 'report-custom-highlight' ? 'highlight' : 'color';
            var val = customInput.value;
            execNoteCommand(mode, val);
            return;
        }
        var input = event.target.closest('#report-image-upload');
        if (!input && event.target.closest && event.target.closest('.report-image-upload')) {
            input = event.target;
        }
        if (input && input.files && input.files[0]) {
            var file = input.files[0];
            if (!validateImageFile(file)) {
                input.value = '';
                return;
            }
            var reader = new FileReader();
            reader.onload = function () {
                window.splashboardReport.addImage(reader.result);
                input.value = '';
            };
            reader.readAsDataURL(file);
        }
    });

    function attachReportObserver() {
        applyReportTabViewport();
        var host = document.getElementById('wrap-report') || document.getElementById('pane-report');
        if (!host) {
            return false;
        }
        if (host.dataset.reportObs === '1') {
            if (document.getElementById('report-workspace')) {
                bootReport();
            }
            return true;
        }
        host.dataset.reportObs = '1';
        var observer = new MutationObserver(function () {
            applyReportTabViewport();
            if (document.getElementById('report-workspace')) {
                bootReport();
            }
        });
        observer.observe(host, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['style']
        });
        var tab = document.getElementById('report-tab');
        if (tab) {
            observer.observe(tab, { attributes: true, attributeFilter: ['style', 'class'] });
        }
        if (document.getElementById('report-workspace')) {
            bootReport();
        }
        return true;
    }
    if (!attachReportObserver()) {
        var wait = new MutationObserver(function () {
            if (attachReportObserver()) {
                wait.disconnect();
            }
        });
        wait.observe(document.documentElement, { childList: true, subtree: true });
    }
    window.addEventListener('resize', applyReportTabViewport);
    applyReportTabViewport();
    window.setInterval(function () {
        applyReportTabViewport();
        var workspace = document.getElementById('report-workspace');
        if (!workspace) {
            return;
        }
        if (workspace.dataset.booted === '1') {
            restoreVisiblePage();
            return;
        }
        bootReport();
    }, 400);
})();
