// Horizontal drag-to-pan for tables & AG-Grid, plus Box Score scroll preservation & reset
(function bindTablePan() {
    var MOVE_PX = 4;

    function findTableScroller(host) {
        if (host.classList.contains('braves-table-scroll')) {
            return host;
        }
        return host.querySelector('.ag-center-cols-viewport');
    }

    function syncTableScrollableState(host, scroller) {
        if (!host || !scroller) {
            return;
        }
        var on = scroller.scrollWidth > scroller.clientWidth + 1;
        host.classList.toggle('is-scrollable', on);
        scroller.classList.toggle('is-scrollable', on);
    }

    function bindScrollableTableHost(host) {
        if (!host || host.closest('.report-paper, .report-workspace')) {
            return;
        }
        var scroller = findTableScroller(host);
        if (!scroller) {
            return;
        }
        if (host.dataset.tablePanBound === '1') {
            syncTableScrollableState(host, scroller);
            return;
        }
        host.dataset.tablePanBound = '1';
        var dragging = false;
        var moved = false;
        var startX = 0;
        var startScroll = 0;
        syncTableScrollableState(host, scroller);

        host.addEventListener('mousedown', function (event) {
            if (event.button !== 0) {
                return;
            }
            if (!host.classList.contains('is-scrollable')) {
                return;
            }
            var sortHit = event.target.closest('.ts-sort-hit');
            if (!sortHit && event.target.closest('.ag-header, .ag-header-cell-resize, button, input, textarea, [contenteditable="true"]')) {
                return;
            }
            dragging = true;
            moved = false;
            startX = event.clientX;
            startScroll = scroller.scrollLeft;
            host.classList.add('is-dragging');
            scroller.classList.add('is-dragging');
            if (!sortHit) {
                event.preventDefault();
            }
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

    function scanScrollableTables() {
        document.querySelectorAll('.braves-table-scroll').forEach(bindScrollableTableHost);
        document.querySelectorAll('.ag-theme-alpine.braves-clean-ag-grid').forEach(bindScrollableTableHost);
    }

    var observer = new MutationObserver(scanScrollableTables);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    var resizeTimer = null;
    window.addEventListener('resize', function () {
        if (resizeTimer) {
            clearTimeout(resizeTimer);
        }
        resizeTimer = setTimeout(scanScrollableTables, 200);
    });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scanScrollableTables);
    } else {
        scanScrollableTables();
    }
})();

(function keepBoxScoreScroll() {
    window.__bsScrollSaved = window.__bsScrollSaved || {};
    if (window.__bsScrollKeep === undefined) {
        window.__bsScrollKeep = true;
    }

    function rememberBoxScoreScroll(el) {
        if (!window.__bsScrollKeep || !el || !el.id || !el.classList) {
            return;
        }
        if (!el.classList.contains('braves-table-scroll') || !el.closest('#pane-bs')) {
            return;
        }
        window.__bsScrollSaved[el.id] = {left: el.scrollLeft, top: el.scrollTop};
    }

    function resetBoxScoreScroll() {
        window.__bsScrollKeep = false;
        window.__bsScrollSaved = {};
        document.querySelectorAll(
            '#bs-matrix-body .braves-table-scroll, #bs-detail-body .braves-table-scroll, #bs-detail-body .braves-grid-wrap'
        ).forEach(function (el) {
            el.scrollLeft = 0;
            el.scrollTop = 0;
        });
        ['bs-player-grid-0', 'bs-player-grid-1'].forEach(function (id) {
            var api = null;
            try {
                api = window.dash_ag_grid && window.dash_ag_grid.getApi && window.dash_ag_grid.getApi(id);
            } catch (err) {
                api = null;
            }
            if (api && !(api.isDestroyed && api.isDestroyed()) && api.resetColumnState) {
                api.resetColumnState();
            }
            var root = document.getElementById(id);
            if (!root) {
                return;
            }
            root.querySelectorAll(
                '.ag-body-viewport, .ag-center-cols-viewport, .ag-body-horizontal-scroll-viewport'
            ).forEach(function (node) {
                node.scrollTop = 0;
                node.scrollLeft = 0;
            });
        });
        window.__bsScrollKeep = true;
    }

    window.splashboardResetBoxScoreScroll = resetBoxScoreScroll;

    document.addEventListener('scroll', function (event) {
        rememberBoxScoreScroll(event.target);
    }, true);

    var observer = new MutationObserver(function () {
        if (!window.__bsScrollKeep) {
            window.__bsScrollSaved = {};
            return;
        }
        Object.keys(window.__bsScrollSaved).forEach(function (id) {
            var el = document.getElementById(id);
            var pos = window.__bsScrollSaved[id];
            if (!el || !pos) {
                return;
            }
            if (el.scrollLeft !== pos.left) {
                el.scrollLeft = pos.left;
            }
            if (el.scrollTop !== pos.top) {
                el.scrollTop = pos.top;
            }
        });
    });
    observer.observe(document.documentElement, {childList: true, subtree: true});
})();
