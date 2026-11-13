// Report workspace & GridStack layout engine: localStorage persistence & v3->v4 migration,
// GridStack init/hydration/hug/compact/overflow, Note rich-text editor, page lifecycle, and toolbar listeners.
(function () {
    var R = window.splashboardReport = window.splashboardReport || {};
    if (R._canvasBooted) {
        return;
    }
    R._canvasBooted = true;
    var state = R._state = R._state || {
        pairLayoutLock: false,
        pdfMeasurer: null,
        pdfHeaderPxCache: {},
        pdfFontOk: false,
        reportFontBinary: null
    };

    var IMAGE_MAX_BYTES = 1000000;
    var GRID_COLUMNS = 12;
    var LAYOUT_VERSION = 4;
    var DESKTOP_MIN_PX = 1280;
    var GRIDSTACK_CSS = '/assets/gridstack.min.css';
    var GRIDSTACK_JS = '/assets/gridstack-all.js';
    var JSPDF_JS = '/assets/jspdf.umd.min.js';
    var ALLOWED_IMAGE_MIMES = {
        'image/jpeg': true,
        'image/png': true,
        'image/webp': true
    };
    var libsPromise = null;
    var hydrateLocks = {};
    var currentPageIndex = 0;
    var spyObserver = null;
    var spyObservedCount = -1;
    var spyRatios = {};
    var hydrating = false;
    var lastStickyKey = '';
    var activeNoteEl = null;
    var tableResizeLock = false;
    var imageSnapLock = false;
    var dialogResolve = null;
    var csvImportMode = 'plain';

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
            layout = { version: LAYOUT_VERSION, pages: [] };
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
                if (block.type === 'csv_table') {
                    var csv = (R.readCsvStore && R.readCsvStore(item)) || {};
                    block.title = csv.title || prev.title || R.CSV_TITLE_FALLBACK;
                    block.coloring = (csv.coloring || prev.coloring) === 'ppp' ? 'ppp' : 'plain';
                    block.columns = csv.columns || prev.columns || [];
                    block.rows = csv.rows || prev.rows || [];
                    delete block.table_key;
                }
                blocks.push(block);
            });
            pages.push({
                id: prevPage.id || paper.id || ('page-' + (pageIndex + 1)),
                blocks: blocks
            });
        });
        layout.pages = pages;
        layout.version = LAYOUT_VERSION;
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
        var maxH = notePaperMaxH(note);
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
                        var needed = parseInt(item.getAttribute('data-min-h') || '1', 10);
                        var maxH = notePaperMaxH(note);
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

            note.addEventListener('paste', function () {
                requestAnimationFrame(function () {
                    if (R.stripReportInvisibleIn) {
                        R.stripReportInvisibleIn(note);
                    }
                    resizeNote(note);
                });
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

    function bindCsvTitles(root) {
        (root || document).querySelectorAll('.report-csv-title').forEach(function (title) {
            if (title.dataset.bound === '1') {
                return;
            }
            title.dataset.bound = '1';
            title.addEventListener('focus', function () {
                title.dataset.prevTitle = title.textContent || '';
            });
            title.addEventListener('keydown', function (event) {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    title.blur();
                } else if (event.key === 'Escape') {
                    event.preventDefault();
                    title.textContent = title.dataset.prevTitle || R.CSV_TITLE_FALLBACK;
                    title.blur();
                }
            });
            title.addEventListener('paste', function (event) {
                event.preventDefault();
                var text = (event.clipboardData || window.clipboardData).getData('text') || '';
                text = text.replace(/[\r\n]+/g, ' ');
                document.execCommand('insertText', false, text);
            });
            title.addEventListener('beforeinput', function (event) {
                if (event.inputType === 'insertParagraph' || event.inputType === 'insertLineBreak') {
                    event.preventDefault();
                }
            });
            title.addEventListener('blur', function () {
                var next = (title.textContent || '').replace(/[\r\n]+/g, ' ').trim();
                if (!next) {
                    next = (title.dataset.prevTitle || '').trim() || R.CSV_TITLE_FALLBACK;
                }
                title.textContent = next;
                var item = title.closest('.grid-stack-item');
                if (item && R.readCsvStore && R.writeCsvStore) {
                    var stored = R.readCsvStore(item) || {};
                    stored.title = next;
                    R.writeCsvStore(item, stored);
                }
                persistLocal(readLayoutFromDom());
            });
        });
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
            grid.on('resizestart', function (event, itemEl) {
                var item = itemEl && itemEl.getAttribute ? itemEl : null;
                if (!item || !R.isReportTable(item.getAttribute('data-block-type'))) {
                    return;
                }
                var node = item.gridstackNode || {};
                item.setAttribute('data-resize-start-h', String(node.h || 1));
                item.setAttribute('data-min-h', '1');
                item.setAttribute('data-min-w', '1');
                grid.update(item, gridBox(item, { minH: 1, minW: 1 }));
            });
            grid.on('resize', function (event, itemEl) {
                if (tableResizeLock) {
                    return;
                }
                var item = itemEl && itemEl.getAttribute ? itemEl : null;
                if (!item || item.getAttribute('data-block-type') !== 'csv_table') {
                    return;
                }
                R.applyCsvColumns(item, false);
            });
            grid.on('resizestop', function (event, itemEl) {
                if (tableResizeLock) {
                    return;
                }
                var gs = el.gridstack;
                var item = itemEl && itemEl.getAttribute ? itemEl : null;
                if (item && item.getAttribute('data-block-type') === 'image' && gs) {
                    snapImageAspect(gs, item);
                }
                if (item && R.pairForKey(item.getAttribute('data-table-key'))) {
                    item.setAttribute('data-resize-commit', '1');
                    R.schedulePairWidths(item.getAttribute('data-table-key'));
                    clampItemToPaper(grid, item);
                    return;
                }
                if (item && R.isReportTable(item.getAttribute('data-block-type'))) {
                    commitTableResize(grid, item);
                    return;
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
                if (!(page.blocks || []).length) {
                    var idx = Array.prototype.indexOf.call(
                        document.querySelectorAll('#report-papers .report-paper'),
                        paper
                    );
                    var fallback = (layout.pages && layout.pages[idx])
                        || layoutPageForPaper(parseLayoutJson('report-default-layout-json') || { pages: [] }, paper);
                    if (fallback && (fallback.blocks || []).length) {
                        page = fallback;
                    }
                }
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
                        var widgetOpts = {
                            id: block.id,
                            x: block.x || 0,
                            y: block.y || 0,
                            w: block.w || 6,
                            h: block.h || 3
                        };
                        if (R.locksResize(block.type)) {
                            widgetOpts.noResize = true;
                        }
                        grid.addWidget(node, widgetOpts);
                    } else if (gridEl) {
                        gridEl.appendChild(node);
                    }
                });
                paper.setAttribute('data-hydrated', '1');
                bindTextBlocks(paper);
                bindCsvTitles(paper);
                return R.paintRotationBlocks(paper).then(function () {
                    return R.paintShotChartBlocks(paper);
                }).then(function () {
                    var originY = snapshotNodeYs(grid);
                    if (grid && grid.el) {
                        grid.el._splashboardOriginY = originY;
                    }
                    fitAllTableBlocks();
                    fitAllRotationBlocks();
                    fitAllShotChartBlocks();
                    if (grid) {
                        resolveOverlaps(grid, originY);
                    }
                    if (opts.compact && grid) {
                        compactGrid(grid);
                        syncPageOneSideNote(grid);
                    }
                }).then(function () {
                    hydrating = false;
                    window.setTimeout(function () {
                        clampGridToPaper(grid);
                        if (grid && grid.el) {
                            resolveOverlaps(grid, grid.el._splashboardOriginY || {});
                        }
                        markPaperOverflow();
                        syncPageListSticky();
                    }, 300);
                }, function () {
                    hydrating = false;
                });
            } catch (err) {
                hydrating = false;
                throw err;
            }
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

    function swapPairYs(blocks) {
        (R.STACK_PAIRS || []).forEach(function (pair) {
            var homes = blocks.filter(function (block) {
                return block && block.table_key === pair[0];
            });
            var aways = blocks.filter(function (block) {
                return block && block.table_key === pair[1];
            });
            var used = [];
            homes.sort(function (a, b) {
                return (a.y || 0) - (b.y || 0);
            });
            homes.forEach(function (home) {
                var below = aways.filter(function (away) {
                    return used.indexOf(away) === -1 && (away.y || 0) > (home.y || 0);
                });
                if (!below.length) {
                    return;
                }
                below.sort(function (a, b) {
                    return (a.y || 0) - (b.y || 0);
                });
                var away = below[0];
                used.push(away);
                var homeY = home.y;
                home.y = away.y;
                away.y = homeY;
            });
        });
    }

    function migrateV3Layout(layout) {
        var pages = (layout.pages || []).map(function (page) {
            var blocks = ((page && page.blocks) || []).map(function (block) {
                return Object.assign({}, block);
            });
            swapPairYs(blocks);
            var migrated = Object.assign({}, page || {});
            migrated.blocks = blocks;
            return migrated;
        });
        return { version: LAYOUT_VERSION, pages: pages };
    }

    function bootReport() {
        var workspace = document.getElementById('report-workspace');
        if (!workspace) {
            return;
        }
        applyReportTabViewport();
        if (workspace.dataset.booted === '1') {
            restoreVisiblePage();
            R.refreshPairWidthsIfStale();
            return;
        }
        workspace.dataset.booted = '1';
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('report-pane-ready', { data: '1' });
        }
        var stored = loadStored();
        if (stored && stored.version === 3) {
            stored = migrateV3Layout(stored);
        } else if (stored && stored.version !== LAYOUT_VERSION) {
            stored = null;
        }
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
        if (R.locksResize(block.type)) {
            node.setAttribute('gs-no-resize', 'true');
        }
        node.setAttribute('data-table-key', block.table_key || '');
        if (block.aspect) {
            node.setAttribute('data-aspect', String(block.aspect));
        }
        node.setAttribute('data-x', String(block.x || 0));
        node.setAttribute('data-y', String(block.y || 0));
        node.setAttribute('data-w', String(block.w || 6));
        node.setAttribute('data-h', String(block.h || 3));
        var card = document.createElement('div');
        var isBuiltin = block.type === 'builtin_table';
        var isCsv = block.type === 'csv_table';
        var isTable = isBuiltin || isCsv;
        var isRotation = block.type === 'rotation';
        var isShotChart = block.type === 'shot_chart';
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
            if (isCsv) {
                title.classList.add('report-csv-title');
                title.setAttribute('contenteditable', 'true');
                title.setAttribute('spellcheck', 'false');
                title.setAttribute('aria-label', 'Table title');
                title.textContent = block.title || R.CSV_TITLE_FALLBACK;
            } else {
                R.fillBlockTitle(title, block.table_key);
            }
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
        } else if (isRotation) {
            var rotHost = document.createElement('div');
            rotHost.className = 'report-rotation-host';
            body.appendChild(rotHost);
        } else if (isShotChart) {
            var shotHost = document.createElement('div');
            shotHost.className = 'report-shot-chart-host';
            body.appendChild(shotHost);
        } else if (isBuiltin) {
            var tblHost = document.createElement('div');
            tblHost.className = 'report-table-host';
            tblHost.setAttribute('data-table-host', block.table_key || '');
            body.appendChild(tblHost);
            R.paintTable(tblHost, block.table_key, node);
        } else if (isCsv) {
            var csvHost = document.createElement('div');
            csvHost.className = 'report-table-host';
            body.appendChild(csvHost);
            R.paintCsvTable(csvHost, block);
            R.writeCsvStore(node, block);
        }
        card.appendChild(body);
        node.appendChild(card);
        return node;
    }

    function cellPx(grid) {
        if (grid && grid.opts && grid.opts.cellHeight) {
            return grid.opts.cellHeight;
        }
        if (grid && grid.getCellHeight) {
            return grid.getCellHeight(true) || 36;
        }
        return 36;
    }

    function gridContentInsetY(grid) {
        var opts = (grid && grid.opts) || {};
        var top = parseFloat(opts.marginTop);
        var bottom = parseFloat(opts.marginBottom);
        if (isNaN(top)) {
            top = parseFloat(opts.margin);
        }
        if (isNaN(bottom)) {
            bottom = parseFloat(opts.margin);
        }
        if (isNaN(top)) {
            top = 6;
        }
        if (isNaN(bottom)) {
            bottom = 6;
        }
        return top + bottom;
    }

    function tableBodyPadY(item) {
        var body = item && item.querySelector('.report-block-body');
        if (!body) {
            return 0;
        }
        var cs = window.getComputedStyle(body);
        return (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    }

    function tableHugH(grid, item) {
        var cell = cellPx(grid);
        var needed = measureTableBlockPx(item) + tableBodyPadY(item) + gridContentInsetY(grid);
        return Math.max(1, Math.ceil(needed / cell));
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
        var blockType = item.getAttribute('data-block-type');
        var oversized = minH > maxRows || h > maxRows;
        if (oversized) {
            x = Math.min(Math.max(0, x), Math.max(0, GRID_COLUMNS - w));
            y = 0;
            h = Math.max(h, minH);
            w = Math.min(Math.max(minW, w), GRID_COLUMNS);
            var oversizedBox = {
                x: x,
                y: y,
                w: w,
                h: h,
                minW: minW,
                minH: minH,
                maxW: GRID_COLUMNS - x,
                maxH: h
            };
            if (R.isReportTable(blockType)) {
                oversizedBox.noResize = true;
            }
            grid.update(item, oversizedBox);
            return;
        }
        w = Math.min(Math.max(minW, w), GRID_COLUMNS);
        h = Math.min(Math.max(minH, h), maxRows);
        x = Math.min(Math.max(0, x), GRID_COLUMNS - w);
        y = Math.min(Math.max(0, y), maxRows - h);
        var fittedBox = {
            x: x,
            y: y,
            w: w,
            h: h,
            minW: minW,
            minH: minH,
            maxW: GRID_COLUMNS - x,
            maxH: maxRows - y
        };
        if (R.isReportTable(blockType)) {
            fittedBox.noResize = true;
        }
        grid.update(item, fittedBox);
    }

    function clampGridToPaper(grid) {
        if (!grid || !grid.el) {
            return;
        }
        grid.el.querySelectorAll('.grid-stack-item').forEach(function (item) {
            if (R.isReportTable(item.getAttribute('data-block-type')) && item.gridstackNode) {
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

    function measureTableBlockPx(item) {
        var table = item.querySelector('.report-js-table');
        if (!table) {
            return measureContentPx(item);
        }
        var title = item.querySelector('.report-block-title-row');
        var titleH = title ? (title.getBoundingClientRect().height || title.offsetHeight || 0) : 0;
        var clone = table.cloneNode(true);
        var liveW = Math.max(table.getBoundingClientRect().width || 0, table.offsetWidth || 0, 400);
        var layout = clone.querySelector('colgroup') ? 'fixed' : 'auto';
        clone.style.cssText = 'position:absolute;left:-10000px;top:0;width:' + liveW + 'px;max-width:none;height:auto;max-height:none;table-layout:' + layout + ';visibility:hidden;overflow:visible;';
        document.body.appendChild(clone);
        var cloneH = Math.max(clone.scrollHeight || 0, clone.offsetHeight || 0);
        document.body.removeChild(clone);
        var liveH = Math.max(table.getBoundingClientRect().height || 0, table.scrollHeight || 0);
        var headH = 0;
        Array.prototype.forEach.call(table.querySelectorAll('thead tr'), function (tr) {
            headH += tr.getBoundingClientRect().height || 0;
        });
        var bodySample = table.querySelector('tbody tr');
        var bodyH = bodySample ? (bodySample.getBoundingClientRect().height || 0) : 0;
        var nBody = table.querySelectorAll('tbody tr').length;
        var fromRows = headH + bodyH * nBody;
        return titleH + Math.max(cloneH, liveH, fromRows);
    }

    function measureBlockH(block, grid, node) {
        var fallback = block.h || 3;
        if (grid && block.type === 'rotation') {
            return Math.max(1, Math.ceil((R.rotationNativeHeightPx() * R.ROTATION_FONT_SCALE + 8) / cellPx(grid)));
        }
        if (grid && block.type === 'shot_chart') {
            return Math.max(1, Math.ceil((R.shotChartEstimatePx(grid) + 8) / cellPx(grid)));
        }
        if (!grid || !R.isReportTable(block.type)) {
            return fallback;
        }
        var host = grid.el;
        node.style.position = 'absolute';
        node.style.visibility = 'hidden';
        node.style.pointerEvents = 'none';
        node.style.left = '0';
        node.style.top = '0';
        var blockW = Math.max(1, Math.min(GRID_COLUMNS, block.w || GRID_COLUMNS));
        var cellW = grid.cellWidth ? grid.cellWidth() : (host.clientWidth / GRID_COLUMNS);
        node.style.width = Math.max(1, Math.round(cellW * blockW)) + 'px';
        host.appendChild(node);
        if (block.type === 'csv_table') {
            R.applyCsvColumns(node, true);
        }
        var h = tableHugH({ opts: grid.opts, getCellHeight: grid.getCellHeight }, node);
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

    function gridBox(item, extra) {
        var node = (item && item.gridstackNode) || {};
        var box = {
            x: node.x || 0,
            y: node.y || 0,
            w: node.w || 1,
            h: node.h || 1
        };
        if (extra) {
            Object.keys(extra).forEach(function (key) {
                box[key] = extra[key];
            });
        }
        return box;
    }

    function fitTableBlocksOnGrid(grid) {
        if (!grid || !grid.el) {
            return;
        }
        if (!state.pairLayoutLock) {
            var seenPairs = {};
            grid.el.querySelectorAll('.report-table-host[data-table-host]').forEach(function (host) {
                var pair = R.pairForKey(host.getAttribute('data-table-host'));
                if (!pair || seenPairs[pair[0]]) {
                    return;
                }
                seenPairs[pair[0]] = 1;
                R.syncPairColumnWidths(pair);
            });
        }
        grid.el.querySelectorAll('.grid-stack-item[data-block-type="csv_table"]').forEach(function (item) {
            R.applyCsvColumns(item, true);
        });
        var updates = [];
        var grew = false;
        var origin = snapshotNodeYs(grid);
        grid.el.querySelectorAll('.grid-stack-item[data-block-type="builtin_table"], .grid-stack-item[data-block-type="csv_table"]').forEach(function (item) {
            var node = item.gridstackNode || {};
            var currentH = node.h || parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '3', 10);
            var h = tableHugH(grid, item);
            if (h > currentH) {
                grew = true;
            }
            if (h !== currentH) {
                updates.push({ item: item, h: h });
            }
        });
        updates.forEach(function (u) {
            u.item.setAttribute('data-min-h', String(u.h));
            u.item.setAttribute('data-min-w', '1');
            grid.update(u.item, gridBox(u.item, { h: u.h, minH: u.h, minW: 1, noResize: true }));
        });
        if (grew) {
            resolveOverlaps(grid, origin);
        }
    }

    function commitTableResize(grid, item) {
        if (tableResizeLock || !grid || !item || !R.isReportTable(item.getAttribute('data-block-type'))) {
            return;
        }
        tableResizeLock = true;
        try {
            var startH = parseInt(item.getAttribute('data-resize-start-h') || '', 10);
            if (!startH) {
                startH = (item.gridstackNode && item.gridstackNode.h) || 1;
            }
            item.removeAttribute('data-resize-commit');
            item.removeAttribute('data-resize-start-h');
            if (item.getAttribute('data-block-type') === 'csv_table') {
                R.applyCsvColumns(item, true);
            }
            var origin = snapshotNodeYs(grid);
            var h = tableHugH(grid, item);
            item.setAttribute('data-min-h', String(h));
            item.setAttribute('data-min-w', '1');
            grid.update(item, gridBox(item, { h: h, minH: h, minW: 1, noResize: true }));
            if (h > startH) {
                resolveOverlaps(grid, origin);
            }
            clampItemToPaper(grid, item);
            persistLocal(readLayoutFromDom());
            window.setTimeout(markPaperOverflow, 0);
        } finally {
            tableResizeLock = false;
        }
    }

    function fitAllTableBlocks() {
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            fitTableBlocksOnGrid(el.gridstack);
        });
    }

    function fitRotationBlocksOnGrid(grid) {
        if (!grid || !grid.el) {
            return;
        }
        var cell = cellPx(grid);
        var updates = [];
        grid.el.querySelectorAll('.grid-stack-item[data-block-type="rotation"]').forEach(function (item) {
            var node = item.gridstackNode || {};
            var currentH = node.h || parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '3', 10);
            var frame = item.querySelector('.report-rotation-scale');
            var plotH = frame
                ? frame.offsetHeight
                : Math.round(R.rotationNativeHeightPx() * R.ROTATION_FONT_SCALE);
            var h = Math.max(1, Math.ceil((plotH + 8) / cell));
            if (h !== currentH) {
                updates.push({ item: item, h: h });
            }
            item.setAttribute('data-min-h', String(h));
            item.setAttribute('data-min-w', String(node.w || GRID_COLUMNS));
        });
        updates.forEach(function (u) {
            grid.update(u.item, { h: u.h, noResize: true, minH: u.h });
        });
    }

    function fitAllRotationBlocks() {
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            fitRotationBlocksOnGrid(el.gridstack);
        });
    }

    function fitShotChartBlocksOnGrid(grid) {
        if (!grid || !grid.el) {
            return;
        }
        var cell = cellPx(grid);
        var updates = [];
        grid.el.querySelectorAll('.grid-stack-item[data-block-type="shot_chart"]').forEach(function (item) {
            var node = item.gridstackNode || {};
            var currentH = node.h || parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '3', 10);
            var host = item.querySelector('.report-shot-chart-host');
            var contentH = host && host.offsetHeight ? host.offsetHeight : R.shotChartEstimatePx(grid);
            var h = Math.max(1, Math.ceil((contentH + tableBodyPadY(item) + gridContentInsetY(grid)) / cell));
            item.setAttribute('data-min-h', String(h));
            item.setAttribute('data-min-w', String(node.w || GRID_COLUMNS));
            if (h !== currentH) {
                updates.push({ item: item, h: h });
            }
        });
        updates.forEach(function (u) {
            grid.update(u.item, { h: u.h, noResize: true, minH: u.h });
        });
    }

    function fitAllShotChartBlocks() {
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            fitShotChartBlocksOnGrid(el.gridstack);
        });
    }

    function snapshotNodeYs(grid) {
        var origin = {};
        if (!grid || !grid.engine) {
            return origin;
        }
        (grid.engine.nodes || []).forEach(function (n, i) {
            var key = nodeOriginKey(n, i);
            origin[key] = n.y || 0;
        });
        return origin;
    }

    function nodeOriginKey(n, i) {
        if (n.el) {
            return n.el.getAttribute('gs-id') || n.el.id || String(i);
        }
        return n.id || String(i);
    }

    function resolveOverlaps(grid, originY) {
        if (!grid || !grid.engine) {
            return;
        }
        originY = originY || {};
        var nodes = (grid.engine.nodes || []).slice().sort(function (a, b) {
            var ay = originY[nodeOriginKey(a, 0)];
            var by = originY[nodeOriginKey(b, 1)];
            if (ay === undefined) {
                ay = a.y || 0;
            }
            if (by === undefined) {
                by = b.y || 0;
            }
            return ay - by || (a.x || 0) - (b.x || 0);
        });
        var placed = [];
        var moves = [];
        nodes.forEach(function (n, i) {
            var x = n.x || 0;
            var key = nodeOriginKey(n, i);
            var y = originY[key];
            if (y === undefined) {
                y = n.y || 0;
            }
            var w = n.w || 1;
            var h = Math.max(1, n.h || 1);
            var guard = 0;
            var moved = true;
            while (moved && guard < 64) {
                moved = false;
                guard += 1;
                for (var j = 0; j < placed.length; j++) {
                    var p = placed[j];
                    if (x < p.x + p.w && x + w > p.x && y < p.y + p.h && y + h > p.y) {
                        y = p.y + p.h;
                        moved = true;
                    }
                }
            }
            if (n.el) {
                moves.push({ el: n.el, y: y });
            }
            placed.push({ x: x, y: y, w: w, h: h });
        });
        moves.sort(function (a, b) {
            return b.y - a.y;
        });
        moves.forEach(function (m) {
            grid.update(m.el, { y: m.y });
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

    function columnPx(grid) {
        var el = grid && grid.el;
        var width = el ? el.clientWidth : 0;
        return (width || 1) / GRID_COLUMNS;
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
        var cancel = document.getElementById('report-dialog-cancel');
        var dialog = document.getElementById('report-dialog');
        if (cancel) {
            cancel.style.display = '';
        }
        if (dialog) {
            dialog.classList.remove('report-dialog-alert');
        }
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('report-dialog-opened', { data: false });
        }
        var resolve = dialogResolve;
        dialogResolve = null;
        if (resolve) {
            resolve(!!result);
        }
    }

    function askConfirm(message, okLabel, hideCancel) {
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
                var cancel = document.getElementById('report-dialog-cancel');
                var dialog = document.getElementById('report-dialog');
                if (msg) {
                    msg.textContent = message;
                }
                if (ok) {
                    ok.textContent = okLabel || 'OK';
                }
                if (cancel) {
                    cancel.style.display = hideCancel ? 'none' : '';
                }
                if (dialog) {
                    dialog.classList.toggle('report-dialog-alert', !!hideCancel);
                }
            }, 0);
        });
    }

    function askAlert(message) {
        return askConfirm(message, 'OK', true);
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

    function paintPlacedBlock(node, block) {
        if (!node || !block) {
            return Promise.resolve();
        }
        if (block.type === 'rotation') {
            return R.paintRotation(node.querySelector('.report-rotation-host')).then(function () {
                fitAllRotationBlocks();
            });
        }
        if (block.type === 'shot_chart') {
            return R.paintShotChart(node.querySelector('.report-shot-chart-host')).then(function () {
                fitAllShotChartBlocks();
            });
        }
        return Promise.resolve();
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
                        var newOpts = {
                            id: block.id,
                            x: slot.x,
                            y: slot.y,
                            w: w,
                            h: h,
                            minW: R.blockLocksSize(block.type) ? w : 1,
                            minH: block.type === 'image' ? 1 : (block.type === 'text' ? 1 : h)
                        };
                        if (R.locksResize(block.type)) {
                            newOpts.noResize = true;
                        }
                        grid.addWidget(node, newOpts);
                        bindTextBlocks(node);
                        bindCsvTitles(node);
                        node.setAttribute('data-min-h', String(block.type === 'text' || block.type === 'image' ? 1 : h));
                        node.setAttribute('data-min-w', R.blockLocksSize(block.type) ? String(w) : '1');
                        var afterNew = paintPlacedBlock(node, block);
                        return afterNew.then(function () {
                            if (R.isReportTable(block.type)) {
                                node.setAttribute('data-resize-start-h', String((node.gridstackNode && node.gridstackNode.h) || h));
                                commitTableResize(grid, node);
                            } else {
                                clampItemToPaper(grid, node);
                                persistLocal(readLayoutFromDom());
                                window.setTimeout(markPaperOverflow, 0);
                            }
                            if (paper) {
                                paper.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            }
                        });
                    });
                });
            }
            var placeOpts = {
                id: block.id,
                x: slot.x,
                y: slot.y,
                w: w,
                h: h,
                minW: R.blockLocksSize(block.type) ? w : 1,
                minH: block.type === 'image' ? 1 : (block.type === 'text' ? 1 : h)
            };
            if (R.locksResize(block.type)) {
                placeOpts.noResize = true;
            }
            grid.addWidget(node, placeOpts);
            bindTextBlocks(node);
            bindCsvTitles(node);
            node.setAttribute('data-min-h', String(block.type === 'text' || block.type === 'image' ? 1 : h));
            node.setAttribute('data-min-w', R.blockLocksSize(block.type) ? String(w) : '1');
            var afterPlace = paintPlacedBlock(node, block);
            afterPlace.then(function () {
                if (R.isReportTable(block.type)) {
                    node.setAttribute('data-resize-start-h', String((node.gridstackNode && node.gridstackNode.h) || h));
                    commitTableResize(grid, node);
                } else {
                    clampItemToPaper(grid, node);
                    persistLocal(readLayoutFromDom());
                    window.setTimeout(markPaperOverflow, 0);
                }
            });
        });
    }

    Object.assign(R, {
        ensureReportLibs: ensureReportLibs,
        hydratePage: hydratePage,
        fitTableBlocksOnGrid: fitTableBlocksOnGrid,
        fitRotationBlocksOnGrid: fitRotationBlocksOnGrid,
        fitShotChartBlocksOnGrid: fitShotChartBlocksOnGrid,
        commitTableResize: commitTableResize,
        snapshotNodeYs: snapshotNodeYs,
        resolveOverlaps: resolveOverlaps,
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
        addCsvTable: function (block) {
            if (!block || !block.columns || !block.columns.length) {
                return readLayoutFromDom();
            }
            addWidgetToActive({
                id: block.id || uniqueId('csv'),
                type: 'csv_table',
                title: block.title || R.CSV_TITLE_FALLBACK,
                coloring: block.coloring === 'ppp' ? 'ppp' : 'plain',
                columns: block.columns,
                rows: block.rows || [],
                w: block.w || R.csvDefaultW(block.coloring),
                h: block.h || 4
            });
            return readLayoutFromDom();
        },
        addRotation: function () {
            addWidgetToActive({
                id: uniqueId('rotation'),
                type: 'rotation',
                w: 12,
                h: 11
            });
            return readLayoutFromDom();
        },
        addShotChart: function () {
            addWidgetToActive({
                id: uniqueId('shot'),
                type: 'shot_chart',
                w: 12,
                h: 10
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
        markOverflow: markPaperOverflow,
        syncSticky: syncPageListSticky
    });

    function validateImageFile(file) {
        if (!file || !ALLOWED_IMAGE_MIMES[file.type]) {
            return false;
        }
        if (!file.size || file.size > IMAGE_MAX_BYTES) {
            return false;
        }
        return true;
    }

    function ensureCsvInput() {
        var input = document.getElementById('report-csv-upload');
        if (input) {
            return input;
        }
        input = document.createElement('input');
        input.type = 'file';
        input.id = 'report-csv-upload';
        input.accept = '.csv,text/csv';
        input.className = 'report-csv-upload';
        input.setAttribute('aria-hidden', 'true');
        input.tabIndex = -1;
        (document.body || document.documentElement).appendChild(input);
        return input;
    }

    function importCsvFile(file, coloring) {
        if (!file) {
            askAlert(R.CSV_ERR_EMPTY);
            return;
        }
        if (!file.size) {
            askAlert(R.CSV_ERR_EMPTY);
            return;
        }
        if (file.size > R.CSV_MAX_BYTES) {
            askAlert(R.CSV_ERR_BYTES);
            return;
        }
        var reader = new FileReader();
        reader.onerror = function () {
            askAlert(R.CSV_ERR_READ);
        };
        reader.onload = function () {
            var text;
            try {
                text = new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(reader.result));
            } catch (err) {
                askAlert(R.CSV_ERR_UTF8);
                return;
            }
            var parsed;
            try {
                parsed = R.parseCsvTable(text);
            } catch (err) {
                askAlert(err && err.message ? err.message : R.CSV_ERR_READ);
                return;
            }
            window.splashboardReport.addCsvTable({
                title: R.csvBlockTitle(file.name, coloring),
                coloring: coloring,
                columns: parsed.columns,
                rows: parsed.rows
            });
        };
        reader.readAsArrayBuffer(file);
    }

    document.addEventListener('click', function (event) {
        var csvItem = event.target.closest('[data-csv-import]');
        if (csvItem) {
            event.preventDefault();
            csvImportMode = csvItem.getAttribute('data-csv-import') === 'ppp' ? 'ppp' : 'plain';
            closeTableMenu();
            var csvInput = ensureCsvInput();
            if (csvInput) {
                csvInput.value = '';
                csvInput.click();
            }
            window.setTimeout(function () {
                var opener = document.getElementById('report-add-table');
                if (opener && opener.getAttribute('aria-expanded') === 'true') {
                    opener.click();
                }
            }, 0);
            return;
        }
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
        if (event.target.closest('#report-add-rotation')) {
            window.splashboardReport.addRotation();
            return;
        }
        if (event.target.closest('#report-add-shot-chart')) {
            window.splashboardReport.addShotChart();
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
                    if (ok && window.splashboardReport.exportPdf) {
                        window.splashboardReport.exportPdf();
                    }
                });
            } else if (window.splashboardReport.exportPdf) {
                window.splashboardReport.exportPdf();
            }
            return;
        }
        var pageBtn = event.target.closest('.report-page-btn[data-page-index]');
        if (pageBtn) {
            var index = parseInt(pageBtn.getAttribute('data-page-index'), 10);
            var paperList = document.querySelectorAll('#report-papers .report-paper');
            if (paperList[index]) {
                setCurrentPage(index);
                paperList[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        var csvUpload = event.target.closest('#report-csv-upload');
        if (csvUpload && csvUpload.files && csvUpload.files[0]) {
            var csvFile = csvUpload.files[0];
            var csvMode = csvImportMode;
            csvUpload.value = '';
            importCsvFile(csvFile, csvMode);
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
    window.addEventListener('resize', function () {
        applyReportTabViewport();
        if (R.refreshPairWidthsIfStale) {
            R.refreshPairWidthsIfStale();
        }
    });
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
            if (R.PAIR_WIDTHS && R.syncPairColumnWidths) {
                R.PAIR_WIDTHS.forEach(R.syncPairColumnWidths);
            }
        });
    }
    applyReportTabViewport();
    window.setInterval(function () {
        applyReportTabViewport();
        var workspace = document.getElementById('report-workspace');
        if (!workspace) {
            return;
        }
        if (workspace.dataset.booted === '1') {
            restoreVisiblePage();
            if (R.refreshPairWidthsIfStale) {
                R.refreshPairWidthsIfStale();
            }
            return;
        }
        bootReport();
    }, 400);
})();
