(function () {
    if (window.splashboardReport) {
        return;
    }

    var IMAGE_MAX_BYTES = 1000000;
    var GRID_COLUMNS = 12;
    var REPORT_FONT_NAME = 'NotoSansTC';
    var REPORT_FONT_URL = '/assets/NotoSansTC-Regular.ttf';
    var ALLOWED_IMAGE_MIMES = {
        'image/jpeg': true,
        'image/png': true,
        'image/webp': true
    };
    var currentPageIndex = 0;
    var spyObserver = null;
    var spyObservedCount = -1;
    var spyRatios = {};

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
        papers.forEach(function (paper, pageIndex) {
            var prevPage = layout.pages[pageIndex] || {};
            var items = paper.querySelectorAll('.grid-stack-item');
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
                    w: parseInt(item.getAttribute('gs-w') || item.getAttribute('data-w') || '6', 10),
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
        resizeNote(activeNoteEl);
        persistLocal(readLayoutFromDom());
    }

    function resizeNote(note) {
        var item = note.closest('.grid-stack-item');
        var gridEl = note.closest('.report-grid');
        var grid = gridEl && gridEl.gridstack;
        if (!item || !grid) {
            return;
        }
        var node = item.gridstackNode || {};
        var currentH = node.h || parseInt(item.getAttribute('gs-h') || item.getAttribute('data-h') || '2', 10);

        var clone = note.cloneNode(true);
        var targetW = note.offsetWidth || item.offsetWidth || 300;
        clone.style.cssText = 'position:absolute;left:-9999px;top:0;width:' + targetW + 'px;height:auto;max-height:none;min-height:0;visibility:hidden;white-space:pre-wrap;';
        document.body.appendChild(clone);
        var contentHeight = clone.scrollHeight || clone.offsetHeight || 0;
        document.body.removeChild(clone);

        var cell = cellPx(grid);
        var needed = Math.max(2, Math.ceil((contentHeight + 12) / cell));
        var maxH = Math.max(2, paperMaxRows(grid) - (node.y || 0));
        var h = Math.min(needed, maxH);
        if (currentH !== h) {
            grid.update(item, { h: h });
            item.setAttribute('gs-h', String(h));
            item.setAttribute('data-h', String(h));
        }
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
                if (event.key === 'Tab') {
                    event.preventDefault();
                    if (event.shiftKey) {
                        document.execCommand('outdent', false, null);
                    } else {
                        document.execCommand('indent', false, null);
                    }
                    resizeNote(note);
                    persistLocal(readLayoutFromDom());
                }
            });

            note.addEventListener('input', function () {
                resizeNote(note);
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

    function initGrids() {
        if (!window.GridStack) {
            window.setTimeout(initGrids, 200);
            return;
        }
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            if (el.dataset.gsInit === '1') {
                return;
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
                grid.on('dragstop', function () {
                    persistLocal(readLayoutFromDom());
                });
                grid.on('resizestop', function () {
                    persistLocal(readLayoutFromDom());
                });
            } catch (err) {
                console.warn('GridStack init failed', err);
            }
        });
        bindTextBlocks();
        var workspace = document.getElementById('report-workspace');
        if (workspace && workspace.dataset.storedApplied !== '1') {
            workspace.dataset.storedApplied = '1';
            var stored = loadStored();
            if (stored && stored.pages && stored.pages.length) {
                applyStoredLayout(stored);
            } else {
                persistLocal(readLayoutFromDom());
                fitAllTableBlocks();
                compactAllGrids();
                persistLocal(readLayoutFromDom());
            }
        }
        initScrollSpy();
    }

    function templateId(block) {
        if (block.type === 'builtin_table') {
            return 'report-tpl-item-table-' + block.table_key;
        }
        return 'report-tpl-item-' + block.type;
    }

    function widgetFromBlock(block) {
        var tpl = document.getElementById(templateId(block));
        if (!tpl) {
            return null;
        }
        var node = tpl.cloneNode(true);
        node.id = 'gs-item-' + block.id;
        node.hidden = false;
        node.classList.remove('report-item-template');
        node.removeAttribute('hidden');
        node.setAttribute('data-gs-id', block.id);
        node.setAttribute('gs-id', block.id);
        node.setAttribute('data-block-type', block.type || '');
        node.setAttribute('data-table-key', block.table_key || '');
        node.setAttribute('data-x', String(block.x || 0));
        node.setAttribute('data-y', String(block.y || 0));
        node.setAttribute('data-w', String(block.w || 6));
        node.setAttribute('data-h', String(block.h || 3));
        var removeBtn = node.querySelector('[data-remove-block]');
        if (removeBtn) {
            removeBtn.setAttribute('data-remove-block', block.id);
        }
        if (block.type === 'text') {
            var body = node.querySelector('.report-block-body');
            if (body) {
                var content = block.content || '';
                var initialP = content.startsWith('<') ? content : (content ? '<p>' + content + '</p>' : '<p></p>');
                body.innerHTML = '<div class="report-text-block" data-text-block="' + block.id + '" data-placeholder="Notes" contenteditable="true">' + initialP + '</div>';
            }
        }
        if (block.type === 'builtin_table') {
            var body = node.querySelector('.report-block-body');
            var existingTable = document.querySelector('#report-papers .grid-stack-item[data-table-key="' + block.table_key + '"] .report-block-body');
            if (body && existingTable && existingTable.innerHTML) {
                body.innerHTML = existingTable.innerHTML;
            }
        }
        if (block.type === 'image') {
            var body = node.querySelector('.report-block-body');
            if (body && block.src) {
                body.innerHTML = '';
                var img = document.createElement('img');
                img.className = 'report-image-block';
                img.setAttribute('src', block.src);
                body.appendChild(img);
            }
        }
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

    function measureContentPx(el) {
        var card = el.querySelector('.report-block-card') || el;
        var clone = card.cloneNode(true);
        clone.className = 'report-block-card';
        clone.style.cssText = '';
        clone.style.position = 'absolute';
        clone.style.left = '-10000px';
        clone.style.top = '0';
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
        var h = Math.max(1, Math.ceil((measureContentPx(node) + 3) / cellPx(grid)));
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
                var h = Math.max(1, Math.ceil((measureContentPx(item) + 3) / cell));
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

    function compactAllGrids() {
        document.querySelectorAll('#report-papers .report-grid').forEach(function (el) {
            if (el.gridstack) {
                compactGrid(el.gridstack);
            }
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

    try {
        if (typeof window !== 'undefined' && window.requestIdleCallback) {
            window.requestIdleCallback(function () {
                loadReportFont().catch(function () {});
            });
        } else if (typeof window !== 'undefined') {
            setTimeout(function () {
                loadReportFont().catch(function () {});
            }, 1000);
        }
    } catch (e) {}

    function registerReportFont(pdf) {
        if (reportFontBinary) {
            pdf.addFileToVFS('NotoSansTC-Regular.ttf', reportFontBinary);
            pdf.addFont('NotoSansTC-Regular.ttf', REPORT_FONT_NAME, 'normal');
            pdf.setFont(REPORT_FONT_NAME, 'normal');
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

    function boxMm(paperRect, el, scale) {
        var r = el.getBoundingClientRect();
        return {
            x: (r.left - paperRect.left) * scale,
            y: (r.top - paperRect.top) * scale,
            w: r.width * scale,
            h: r.height * scale
        };
    }

    function pxToPt(px, scale) {
        return Math.max(5, px * scale * 72 / 25.4);
    }

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
        pdf.setFont(REPORT_FONT_NAME, 'normal');
        try {
            pdf.text(text, x, y, options);
        } catch (err) {
            pdf.setFont('helvetica', 'normal');
            pdf.text(text, x, y, options);
            pdf.setFont(REPORT_FONT_NAME, 'normal');
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
            drawPdfText(pdf, text, box.x + box.w / 2, box.y, {
                baseline: 'top',
                align: 'center'
            });
        });
    }

    function drawTableCell(pdf, cell, paperRect, scale) {
        var box = boxMm(paperRect, cell, scale);
        if (box.y >= 210 || box.x >= 297 || box.w <= 0 || box.h <= 0) {
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
        pdf.setTextColor(color[0], color[1], color[2]);
        pdf.setFontSize(pxToPt(parseFloat(style.fontSize) || 11, scale));
        var pad = 0.5;
        var maxW = Math.max(0.4, box.w - pad * 2);
        var fitted = fitText(pdf, text, maxW);
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
        drawPdfText(pdf, fitted, x, box.y + pad, { baseline: 'top', align: pdfAlign });
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
        var lineH = baseLinePx * scale;
        var ptSize = pxToPt(baseFontPx, scale);
        var maxY = Math.min(210, box.y + box.h);
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
            if (cursorY + lineH * 0.4 > maxY) {
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
                drawPdfText(pdf, span.text, spanX, cursorY, { baseline: 'top' });

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
        if (box.w <= 0 || box.h <= 0 || box.y >= 210) {
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
            pdf.addImage(dataUrl, 'PNG', box.x, box.y, box.w, Math.min(box.h, 210 - box.y));
        } catch (err) {
            console.warn('PDF image skipped', err);
        }
    }

    function drawPaper(pdf, paper) {
        var paperRect = paper.getBoundingClientRect();
        if (!paperRect.width) {
            return;
        }
        var scale = 297 / paperRect.width;
        pdf.setFillColor(255, 255, 255);
        pdf.rect(0, 0, 297, 210, 'F');
        drawHeader(pdf, paper, paperRect, scale);
        paper.querySelectorAll('.grid-stack-item').forEach(function (item) {
            if (item.hidden || item.classList.contains('report-item-template')) {
                return;
            }
            var title = item.querySelector('.report-block-title');
            if (title) {
                var titleText = (title.textContent || '').trim();
                if (titleText) {
                    var tBox = boxMm(paperRect, title, scale);
                    var tStyle = window.getComputedStyle(title);
                    var tColor = parseRgb(tStyle.color) || [30, 58, 138];
                    pdf.setTextColor(tColor[0], tColor[1], tColor[2]);
                    pdf.setFontSize(pxToPt(parseFloat(tStyle.fontSize) || 12, scale));
                    drawPdfText(pdf, titleText, tBox.x, tBox.y, { baseline: 'top' });
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
        if (!papers.length || !window.jspdf || !window.jspdf.jsPDF) {
            window.print();
            return Promise.resolve();
        }
        var JsPDF = window.jspdf.jsPDF;
        setPdfBusy(true);
        return loadReportFont().then(function () {
            var pdf = new JsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
            registerReportFont(pdf);
            Array.prototype.forEach.call(papers, function (paper, index) {
                if (index > 0) {
                    pdf.addPage('a4', 'landscape');
                }
                try {
                    drawPaper(pdf, paper);
                } catch (drawErr) {
                    console.warn('PDF page draw failed', index, drawErr);
                    throw drawErr;
                }
            });
            var nameEl = document.getElementById('report-pdf-filename');
            var filename = (nameEl && (nameEl.textContent || '').trim()) || 'splashboard-report.pdf';
            pdf.save(filename);
        }).catch(function (err) {
            console.warn('PDF export failed, using print()', err && (err.message || String(err)));
            window.print();
        }).then(function () {
            setPdfBusy(false);
        });
    }

    var dialogResolve = null;

    function closeDialog(result) {
        var root = document.getElementById('report-dialog');
        if (root) {
            root.hidden = true;
        }
        var resolve = dialogResolve;
        dialogResolve = null;
        if (resolve) {
            resolve(!!result);
        }
    }

    function askConfirm(message, okLabel) {
        return new Promise(function (resolve) {
            var root = document.getElementById('report-dialog');
            var msg = document.getElementById('report-dialog-message');
            var ok = document.getElementById('report-dialog-ok');
            if (!root || !msg || !ok) {
                resolve(window.confirm(message));
                return;
            }
            msg.textContent = message;
            ok.textContent = okLabel || 'OK';
            dialogResolve = resolve;
            root.hidden = false;
        });
    }

    function addEmptyPaper() {
        var host = document.getElementById('report-papers');
        var first = host && host.querySelector('.report-paper');
        if (!host || !first) {
            return null;
        }
        var paper = document.createElement('div');
        paper.className = 'report-paper';
        paper.id = 'report-paper-' + uniqueId('page');
        paper.appendChild(makePageDeleteButton(paperCount()));
        var header = first.querySelector('.report-header');
        if (header) {
            paper.appendChild(header.cloneNode(true));
        }
        var grid = document.createElement('div');
        grid.className = 'grid-stack report-grid';
        grid.id = 'report-grid-' + uniqueId('grid');
        paper.appendChild(grid);
        host.appendChild(paper);
        spyObservedCount = -1;
        return paper;
    }

    function refreshPageChrome() {
        var papers = document.querySelectorAll('#report-papers .report-paper');
        var n = papers.length;
        papers.forEach(function (paper, index) {
            paper.setAttribute('data-page-index', String(index));
            var del = paper.querySelector('.report-page-delete');
            if (!del) {
                del = makePageDeleteButton(index);
                paper.insertBefore(del, paper.firstChild);
            }
            del.setAttribute('data-delete-page', String(index));
            del.classList.toggle('is-disabled', n <= 1);
            del.disabled = n <= 1;
            var num = paper.querySelector('.report-page-number');
            if (num) {
                num.remove();
            }
        });
        var list = document.getElementById('report-page-list');
        if (!list) {
            setCurrentPage(currentPageIndex);
            return;
        }
        var addBtn = document.getElementById('report-add-page');
        var active = clampPageIndex(currentPageIndex);
        Array.prototype.slice.call(list.querySelectorAll('.report-page-btn[data-page-index]')).forEach(function (btn) {
            btn.remove();
        });
        Array.prototype.slice.call(list.querySelectorAll('.report-page-remove')).forEach(function (btn) {
            btn.remove();
        });
        for (var i = 0; i < n; i++) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'report-page-btn' + (i === active ? ' is-active' : '');
            btn.setAttribute('data-page-index', String(i));
            btn.textContent = String(i + 1);
            list.insertBefore(btn, addBtn);
        }
        setCurrentPage(active);
    }

    function applyStoredLayout(stored, compact) {
        var host = document.getElementById('report-papers');
        if (!host || !stored.pages.length) {
            return;
        }
        while (document.querySelectorAll('#report-papers .report-paper').length < stored.pages.length) {
            addEmptyPaper();
        }
        while (document.querySelectorAll('#report-papers .report-paper').length > stored.pages.length) {
            var last = host.querySelector('.report-paper:last-child');
            var lastGrid = last && last.querySelector('.report-grid');
            if (lastGrid && lastGrid.gridstack) {
                lastGrid.gridstack.destroy(false);
            }
            if (last) {
                last.remove();
            }
        }
        spyObservedCount = -1;
        initGrids();
        stored.pages.forEach(function (page, index) {
            var paper = document.querySelectorAll('#report-papers .report-paper')[index];
            var gridEl = paper && paper.querySelector('.report-grid');
            var grid = gridEl && gridEl.gridstack;
            if (!grid) {
                return;
            }
            grid.removeAll();
            (page.blocks || []).forEach(function (block) {
                var node = widgetFromBlock(block);
                if (node) {
                    grid.addWidget(node, {
                        id: block.id,
                        x: block.x || 0,
                        y: block.y || 0,
                        w: block.w || 6,
                        h: block.h || 3
                    });
                }
            });
        });
        refreshPageChrome();
        bindTextBlocks();
        fitAllTableBlocks();
        if (compact) {
            compactAllGrids();
        }
        initScrollSpy();
        persistLocal(readLayoutFromDom());
    }

    function addWidgetToActive(block) {
        var node = widgetFromBlock(block);
        var grid = activeGrid();
        if (!grid || !node) {
            return;
        }
        var w = block.w || 6;
        var h = measureBlockH(block, grid, node);
        var slot = findFit(grid, w, h, paperMaxRows(grid));
        if (!slot) {
            addEmptyPaper();
            initGrids();
            var papers = document.querySelectorAll('#report-papers .report-paper');
            setCurrentPage(papers.length - 1);
            refreshPageChrome();
            initScrollSpy();
            grid = activeGrid();
            if (!grid) {
                return;
            }
            slot = findFit(grid, w, h, paperMaxRows(grid)) || { x: 0, y: 0 };
            if (papers[papers.length - 1]) {
                papers[papers.length - 1].scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
        grid.addWidget(node, {
            id: block.id,
            x: slot.x,
            y: slot.y,
            w: w,
            h: h
        });
        bindTextBlocks(node);
        persistLocal(readLayoutFromDom());
    }

    window.splashboardReport = {
        loadStored: loadStored,
        readLayoutFromDom: readLayoutFromDom,
        persist: persistLocal,
        addPage: function () {
            var paper = addEmptyPaper();
            initGrids();
            var papers = document.querySelectorAll('#report-papers .report-paper');
            setCurrentPage(papers.length - 1);
            refreshPageChrome();
            initScrollSpy();
            persistLocal(readLayoutFromDom());
            if (paper) {
                paper.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            return readLayoutFromDom();
        },
        removePage: function (index) {
            var host = document.getElementById('report-papers');
            var papers = host ? host.querySelectorAll('.report-paper') : [];
            if (papers.length <= 1) {
                return readLayoutFromDom();
            }
            if (typeof index !== 'number' || isNaN(index)) {
                index = currentPageIndex;
            }
            if (index < 0 || index >= papers.length) {
                return readLayoutFromDom();
            }
            var paper = papers[index];
            var gridEl = paper.querySelector('.report-grid');
            if (gridEl && gridEl.gridstack) {
                gridEl.gridstack.destroy(false);
            }
            paper.remove();
            spyObservedCount = -1;
            if (currentPageIndex === index) {
                setCurrentPage(index > 0 ? index - 1 : 0);
            } else if (currentPageIndex > index) {
                setCurrentPage(currentPageIndex - 1);
            }
            refreshPageChrome();
            initScrollSpy();
            persistLocal(readLayoutFromDom());
            var remaining = document.querySelectorAll('#report-papers .report-paper')[currentPageIndex];
            if (remaining) {
                remaining.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            return readLayoutFromDom();
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
            addWidgetToActive({
                id: uniqueId('image'),
                type: 'image',
                src: src,
                w: 6,
                h: 5
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
        }
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
            toggleTableMenu();
            return;
        }
        if (!event.target.closest('.report-table-picker')) {
            closeTableMenu();
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
        var deletePage = event.target.closest('[data-delete-page]');
        if (deletePage && !deletePage.disabled && !deletePage.classList.contains('is-disabled')) {
            var deleteIndex = parseInt(deletePage.getAttribute('data-delete-page'), 10);
            askConfirm('Delete this page?', 'Delete').then(function (ok) {
                if (ok) {
                    window.splashboardReport.removePage(deleteIndex);
                }
            });
            return;
        }
        if (event.target.closest('#btn-export-pdf')) {
            window.splashboardReport.exportPdf();
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

    var observer = new MutationObserver(function () {
        initGrids();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initGrids);
    } else {
        initGrids();
    }
})();

// AG-Grid custom cell renderers for Dash AG-Grid
var dagFuncs = window.dashAgGridFunctions = window.dashAgGridFunctions || {};
var dagComponentFuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

dagComponentFuncs.ScheduleStatusBadge = function (props) {
    var status = (props.value || '').trim() || 'UNKNOWN';
    var bucket = (props.data && props.data.statusBucket) || 'unplayed';
    var cls = 'schedule-badge schedule-badge-' + bucket;
    return React.createElement('span', { className: cls }, status);
};

dagComponentFuncs.ScheduleScoreLink = function (props) {
    var row = props.data || {};
    var fixtureId = row.fixtureId || '';
    var text = props.value || '—';
    if (!row.scoreClickable) {
        return React.createElement('span', { className: 'schedule-score-plain' }, text);
    }
    return React.createElement('a', {
        href: '/game/' + fixtureId,
        className: 'schedule-score-link',
        onClick: function(e) {
            e.stopPropagation();
        }
    }, text);
};

dagComponentFuncs.PlusMinusCell = function (props) {
    var val = props.value;
    if (val === null || val === undefined || val === '') {
        return React.createElement('span', null, '');
    }
    var num = parseFloat(val);
    if (isNaN(num)) {
        return React.createElement('span', null, String(val));
    }
    var intVal = Math.round(num);
    var style = {
        textAlign: 'center',
        display: 'inline-block',
        width: '100%'
    };
    if (intVal > 0) {
        style.color = '#0077b6';
        style.fontWeight = '700';
    } else if (intVal < 0) {
        style.color = '#e63946';
        style.fontWeight = '700';
    } else {
        style.color = '#64748b';
        style.fontWeight = '400';
    }
    return React.createElement('span', { style: style }, String(intVal));
};

dagComponentFuncs.StarterCell = function (props) {
    var val = (props.value || '').trim();
    if (!val) {
        return React.createElement('span', null, '');
    }
    var style = {
        textAlign: 'center',
        display: 'inline-block',
        width: '100%',
        color: '#1e293b',
        fontWeight: '900',
        fontSize: '16px',
        lineHeight: '1',
    };
    return React.createElement('span', { style: style }, '○');
};

// Global AG Grid sort column cell background updater for B.LEAGUE sorting
(function () {
    function updateSortedColHighlight(gridWrap) {
        if (!gridWrap) return;
        var sortedHeaders = gridWrap.querySelectorAll(
            '.ag-header-cell[aria-sort="ascending"], .ag-header-cell[aria-sort="descending"], .ag-header-cell.ag-header-cell-sorted-asc, .ag-header-cell.ag-header-cell-sorted-desc'
        );
        var activeColIds = Array.from(sortedHeaders).map(function (h) {
            return h.getAttribute('col-id');
        }).filter(Boolean);

        var allCells = gridWrap.querySelectorAll('.ag-cell');
        allCells.forEach(function (cell) {
            var colId = cell.getAttribute('col-id');
            if (colId && activeColIds.indexOf(colId) !== -1) {
                cell.classList.add('ag-sorted-col-bg');
            } else {
                cell.classList.remove('ag-sorted-col-bg');
            }
        });
    }

    document.addEventListener('click', function (e) {
        var header = e.target.closest('.ag-header-cell');
        if (header) {
            var gridWrap = header.closest('.braves-grid-wrap, .ag-theme-alpine');
            setTimeout(function () {
                updateSortedColHighlight(gridWrap);
            }, 30);
            setTimeout(function () {
                updateSortedColHighlight(gridWrap);
            }, 120);
        }
    }, true);
})();

(function bindTablePan() {
    var MOVE_PX = 4;

    function scrollerFor(host) {
        if (host.classList.contains('braves-table-scroll')) {
            return host;
        }
        return host.querySelector('.ag-center-cols-viewport');
    }

    function updateScrollable(host, scroller) {
        if (!host || !scroller) {
            return;
        }
        var on = scroller.scrollWidth > scroller.clientWidth + 1;
        host.classList.toggle('is-scrollable', on);
        scroller.classList.toggle('is-scrollable', on);
    }

    function bindHost(host) {
        if (!host || host.closest('.report-paper, .report-workspace')) {
            return;
        }
        var scroller = scrollerFor(host);
        if (!scroller) {
            return;
        }
        if (host.dataset.tablePanBound === '1') {
            updateScrollable(host, scroller);
            return;
        }
        host.dataset.tablePanBound = '1';
        var dragging = false;
        var moved = false;
        var startX = 0;
        var startScroll = 0;
        updateScrollable(host, scroller);

        host.addEventListener('mousedown', function (event) {
            if (event.button !== 0) {
                return;
            }
            if (!host.classList.contains('is-scrollable')) {
                return;
            }
            if (event.target.closest('.ag-header, .ag-header-cell-resize, button, input, textarea, [contenteditable="true"]')) {
                return;
            }
            dragging = true;
            moved = false;
            startX = event.clientX;
            startScroll = scroller.scrollLeft;
            host.classList.add('is-dragging');
            scroller.classList.add('is-dragging');
            event.preventDefault();
        });

        window.addEventListener('mousemove', function (event) {
            if (!dragging) {
                return;
            }
            var dx = event.clientX - startX;
            if (Math.abs(dx) >= MOVE_PX) {
                moved = true;
            }
            scroller.scrollLeft = startScroll - dx;
            if (moved) {
                event.preventDefault();
            }
        });

        window.addEventListener('mouseup', function () {
            if (!dragging) {
                return;
            }
            dragging = false;
            host.classList.remove('is-dragging');
            scroller.classList.remove('is-dragging');
            if (moved) {
                host.dataset.panMoved = '1';
            }
        });

        host.addEventListener('click', function (event) {
            if (host.dataset.panMoved === '1') {
                event.preventDefault();
                event.stopPropagation();
                host.dataset.panMoved = '';
            }
        }, true);
    }

    function scan() {
        document.querySelectorAll('.braves-table-scroll').forEach(bindHost);
        document.querySelectorAll('.ag-theme-alpine.braves-clean-ag-grid').forEach(bindHost);
    }

    var observer = new MutationObserver(scan);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    var resizeTimer = null;
    window.addEventListener('resize', function () {
        if (resizeTimer) {
            clearTimeout(resizeTimer);
        }
        resizeTimer = setTimeout(scan, 200);
    });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scan);
    } else {
        scan();
    }
})();

