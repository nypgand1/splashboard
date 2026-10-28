// Keep Box Score and AG Grid headers in view while the page scrolls.
// Report paper tables (.report-js-table) scroll away with the paper.
// Horizontal pan lives on an overflow container, which blocks position:sticky
// from reaching the viewport, so the header is shifted inside that box.
(function () {
    var paused = false;
    var frame = 0;

    function stickOffset() {
        var report = document.getElementById('wrap-report');
        if (!report) {
            return 0;
        }
        var reportBox = report.getBoundingClientRect();
        if (reportBox.width < 1 || reportBox.height < 1) {
            return 0;
        }
        var bar = report.querySelector('.report-toolbar');
        if (!bar) {
            return 0;
        }
        var rect = bar.getBoundingClientRect();
        if (rect.width < 1 || rect.height < 1 || rect.bottom <= 0) {
            return 0;
        }
        return Math.max(0, rect.bottom);
    }

    function paintShift(el, shift) {
        var next = shift > 0.5 ? String(Math.round(shift)) : '';
        if ((el.getAttribute('data-stick-shift') || '') === next) {
            return;
        }
        if (next) {
            el.style.transform = 'translateY(' + next + 'px)';
            el.setAttribute('data-stick-shift', next);
            el.classList.add('is-header-stuck');
        } else {
            el.style.transform = '';
            el.removeAttribute('data-stick-shift');
            el.classList.remove('is-header-stuck');
        }
    }

    function appliedShift(el) {
        var raw = el ? el.getAttribute('data-stick-shift') : '';
        var value = raw ? parseFloat(raw) : 0;
        return value || 0;
    }

    function stickTable(table, top) {
        var thead = table.tHead;
        if (!thead) {
            return;
        }
        var sample = thead.querySelector('th');
        if (!sample) {
            return;
        }
        var rect = table.getBoundingClientRect();
        var headH = thead.offsetHeight || 0;
        var naturalTop = sample.getBoundingClientRect().top - appliedShift(sample);
        var shift = 0;
        if (headH > 0 && naturalTop < top && rect.bottom - headH > top) {
            shift = top - naturalTop;
        }
        var cells = thead.querySelectorAll('th');
        for (var i = 0; i < cells.length; i++) {
            paintShift(cells[i], shift);
        }
    }

    function stickGrid(grid, top) {
        var header = grid.querySelector('.ag-header');
        if (!header) {
            return;
        }
        var rect = grid.getBoundingClientRect();
        var headH = header.offsetHeight || 0;
        var naturalTop = header.getBoundingClientRect().top - appliedShift(header);
        var shift = 0;
        if (headH > 0 && naturalTop < top && rect.bottom - headH > top) {
            shift = top - naturalTop;
        }
        paintShift(header, shift);
    }

    function clearAll() {
        var stuck = document.querySelectorAll('[data-stick-shift]');
        for (var i = 0; i < stuck.length; i++) {
            paintShift(stuck[i], 0);
        }
    }

    function refresh() {
        if (paused) {
            return;
        }
        var top = stickOffset();
        var tables = document.querySelectorAll('.braves-clean-table');
        for (var i = 0; i < tables.length; i++) {
            stickTable(tables[i], top);
        }
        var grids = document.querySelectorAll('.braves-clean-ag-grid');
        for (var j = 0; j < grids.length; j++) {
            stickGrid(grids[j], top);
        }
    }

    function schedule() {
        if (frame) {
            return;
        }
        frame = window.requestAnimationFrame(function () {
            frame = 0;
            refresh();
        });
    }

    window.addEventListener('scroll', schedule, true);
    window.addEventListener('resize', schedule);
    window.splashboardTableStick = {
        pause: function () {
            paused = true;
            clearAll();
        },
        resume: function () {
            paused = false;
            schedule();
        },
        refresh: refresh,
    };

    var root = document.getElementById('app-shell') || document.body;
    var observer = new MutationObserver(schedule);
    observer.observe(root, {childList: true, subtree: true});
    schedule();
})();
