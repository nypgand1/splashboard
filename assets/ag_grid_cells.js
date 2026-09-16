// AG-Grid custom cell renderers for Dash AG-Grid
var dagFuncs = window.dashAgGridFunctions = window.dashAgGridFunctions || {};
var dagComponentFuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

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

