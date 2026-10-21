// AG-Grid custom cell renderers for Dash AG-Grid
var dagFuncs = window.dashAgGridFunctions = window.dashAgGridFunctions || {};

window.__lineupShowOpp = false;

window.applyLineupShowOpp = function (show, attempt) {
    window.__lineupShowOpp = !!show;
    attempt = attempt || 0;
    if (!window.dash_ag_grid || !window.dash_ag_grid.getApi) {
        return;
    }
    var pending = false;
    ['lineup-grid-0', 'lineup-grid-1'].forEach(function (id) {
        if (!document.getElementById(id)) {
            return;
        }
        var api;
        try {
            api = window.dash_ag_grid.getApi(id);
        } catch (err) {
            pending = true;
            return;
        }
        if (!api || (api.isDestroyed && api.isDestroyed())) {
            return;
        }
        var page = null;
        if (api.getGridOption('pagination') && api.paginationGetCurrentPage) {
            page = api.paginationGetCurrentPage();
        }
        api.setGridOption('isExternalFilterPresent', function () {
            return !window.__lineupShowOpp;
        });
        api.onFilterChanged();
        if (api.getGridOption('pagination')) {
            api.setGridOption('paginationPageSize', window.__lineupShowOpp ? 40 : 20);
            if (typeof page === 'number' && api.paginationGoToPage) {
                api.paginationGoToPage(page);
            }
        }
    });
    if (pending && attempt < 10) {
        setTimeout(function () {
            window.applyLineupShowOpp(window.__lineupShowOpp, attempt + 1);
        }, 50);
    }
};

// clientWidth is the grid host. textWidth is the longest Lineup label plus
// horizontal cell padding and border. Below the designed total, keep the
// designed Lineup width and let the grid scroll. Otherwise grow only to the
// label, and leave any remainder empty on the right.
function splashboardLineupColumnWidth(clientWidth, statsSum, designedLineup, textWidth) {
    if (!(clientWidth > 0) || typeof designedLineup !== 'number') {
        return null;
    }
    var total = statsSum + designedLineup;
    if (clientWidth < total) {
        return designedLineup;
    }
    var cap = clientWidth - statsSum;
    var need = Math.max(designedLineup, textWidth || 0);
    return Math.min(need, cap);
}
window.splashboardLineupColumnWidth = splashboardLineupColumnWidth;

var _lineupFitting = false;
var _lineupWidthByApi = new WeakMap();
var _lineupMeasureCanvas;

function _lineupApi(id) {
    var el = document.getElementById(id);
    if (!el || !window.dash_ag_grid || !window.dash_ag_grid.getApi) {
        return null;
    }
    try {
        var api = window.dash_ag_grid.getApi(id);
        if (!api || (api.isDestroyed && api.isDestroyed())) {
            return null;
        }
        return api;
    } catch (err) {
        return null;
    }
}

function _lineupHostWidth(api) {
    var ids = ['lineup-grid-0', 'lineup-grid-1', 'matchup-grid'];
    for (var i = 0; i < ids.length; i++) {
        if (_lineupApi(ids[i]) === api) {
            return document.getElementById(ids[i]).clientWidth;
        }
    }
    return 0;
}

function _lineupPeers(api) {
    if (_lineupApi('matchup-grid') === api) {
        return [api];
    }
    var peers = [];
    ['lineup-grid-0', 'lineup-grid-1'].forEach(function (id) {
        var peer = _lineupApi(id);
        if (peer) {
            peers.push(peer);
        }
    });
    if (!peers.length) {
        return [api];
    }
    for (var i = 0; i < peers.length; i++) {
        if (peers[i] === api) {
            return peers;
        }
    }
    return [api];
}

function _lineupFont() {
    var cell = document.querySelector(
        '.braves-lineup-grid .ag-row:not(.lineup-opp-row) .ag-cell[col-id="Lineup"], .braves-lineup-grid .ag-row:not(.lineup-opp-row) .ag-cell[col-id="Lineups"]'
    );
    if (!cell) {
        return '700 13px -apple-system, "PingFang TC", "Noto Sans TC", "Segoe UI", Roboto, sans-serif';
    }
    var cs = window.getComputedStyle(cell);
    return (cs.fontWeight || '700') + ' ' + (cs.fontSize || '13px') + ' ' + (cs.fontFamily || 'sans-serif');
}

function _lineupPad() {
    var cell = document.querySelector(
        '.braves-lineup-grid .ag-cell[col-id="Lineup"], .braves-lineup-grid .ag-cell[col-id="Lineups"]'
    );
    if (!cell) {
        return 6;
    }
    var cs = window.getComputedStyle(cell);
    return (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0)
        + (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.borderRightWidth) || 0);
}

function _lineupLabel(data, matchup) {
    if (!data) {
        return '';
    }
    if (data._opp && !matchup) {
        return 'Opp';
    }
    return data.Lineup || data.Lineups || '';
}

function _lineupTextWidth(api) {
    var matchup = _lineupApi('matchup-grid') === api;
    var pad = _lineupPad();
    var widest = 0;
    if (!api.forEachNode) {
        return 0;
    }
    if (!_lineupMeasureCanvas) {
        _lineupMeasureCanvas = document.createElement('canvas');
    }
    var ctx = _lineupMeasureCanvas.getContext('2d');
    ctx.font = _lineupFont();
    api.forEachNode(function (node) {
        var text = _lineupLabel(node && node.data, matchup);
        if (!text) {
            return;
        }
        widest = Math.max(widest, Math.ceil(ctx.measureText(String(text)).width + pad));
    });
    return widest;
}

function _applyLineupWidth(api, clientWidth, textWidth) {
    if (!api.getColumns || !api.setColumnWidths) {
        return;
    }
    var columns = api.getColumns() || [];
    var lineupId = null;
    var lineupDesigned = null;
    var others = 0;
    var updates = [];
    columns.forEach(function (col) {
        var def = col.getColDef();
        if (!def.field) {
            return;
        }
        var id = col.getColId();
        var designed = def.designedWidth;
        if (typeof designed !== 'number') {
            designed = col.getActualWidth();
        }
        if (id === 'Lineup' || id === 'Lineups') {
            lineupId = id;
            lineupDesigned = designed;
            return;
        }
        others += designed;
        updates.push({key: id, newWidth: designed});
    });
    var lineupWidth = splashboardLineupColumnWidth(clientWidth, others, lineupDesigned, textWidth);
    if (!lineupId || lineupWidth === null) {
        return;
    }
    updates.push({key: lineupId, newWidth: lineupWidth});
    var unchanged = updates.every(function (item) {
        var current = api.getColumn(item.key);
        return current && Math.round(current.getActualWidth()) === Math.round(item.newWidth);
    });
    if (unchanged) {
        return;
    }
    api.setColumnWidths(updates);
    if (api.resetRowHeights) {
        api.resetRowHeights();
    }
}

function splashboardFitLineupWidth(params) {
    var api = params && params.api;
    if (_lineupFitting || !api || (api.isDestroyed && api.isDestroyed())) {
        return;
    }
    var width = params.clientWidth;
    if (!(width > 0)) {
        width = _lineupHostWidth(api);
    }
    if (!(width > 0)) {
        return;
    }
    _lineupFitting = true;
    try {
        _lineupWidthByApi.set(api, width);
        var peers = _lineupPeers(api);
        var textWidth = 0;
        peers.forEach(function (peer) {
            textWidth = Math.max(textWidth, _lineupTextWidth(peer));
        });
        peers.forEach(function (peer) {
            var peerWidth = peer === api ? width : _lineupWidthByApi.get(peer);
            if (!(peerWidth > 0)) {
                peerWidth = _lineupHostWidth(peer);
            }
            if (peerWidth > 0) {
                _applyLineupWidth(peer, peerWidth, textWidth);
            }
        });
    } finally {
        _lineupFitting = false;
    }
}
window.splashboardFitLineupWidth = splashboardFitLineupWidth;
dagFuncs.splashboardFitLineupWidth = splashboardFitLineupWidth;

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

(function keepBoxScoreScroll() {
    window.__bsScrollSaved = window.__bsScrollSaved || {};
    if (window.__bsScrollKeep === undefined) {
        window.__bsScrollKeep = true;
    }

    function remember(el) {
        if (!window.__bsScrollKeep || !el || !el.id || !el.classList) {
            return;
        }
        if (!el.classList.contains('braves-table-scroll') || !el.closest('#pane-bs')) {
            return;
        }
        window.__bsScrollSaved[el.id] = {left: el.scrollLeft, top: el.scrollTop};
    }

    document.addEventListener('scroll', function (event) {
        remember(event.target);
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

