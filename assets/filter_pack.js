(function () {
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.filter_pack = window.dash_clientside.filter_pack || {};

    function contentWidth(cluster) {
        if (!cluster) {
            return 0;
        }
        var style = window.getComputedStyle(cluster);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return 0;
        }
        var inner = cluster.querySelector('.filter-cluster-inner');
        if (!inner) {
            return 0;
        }
        var kids = inner.children;
        var visible = false;
        var index;
        for (index = 0; index < kids.length; index += 1) {
            if (window.getComputedStyle(kids[index]).display !== 'none') {
                visible = true;
                break;
            }
        }
        if (!visible) {
            return 0;
        }
        return inner.scrollWidth;
    }

    function gapOf(pack) {
        var gap = parseFloat(window.getComputedStyle(pack).columnGap);
        return isFinite(gap) ? gap : 0;
    }

    function sumWidths(widths, gap) {
        var need = 0;
        var count = 0;
        var index;
        for (index = 0; index < widths.length; index += 1) {
            if (widths[index] > 0) {
                if (count) {
                    need += gap;
                }
                need += widths[index];
                count += 1;
            }
        }
        return need;
    }

    function setMode(pack, mode) {
        if (pack.getAttribute('data-mode') !== mode) {
            pack.setAttribute('data-mode', mode);
        }
    }

    function measureScope(pack) {
        var league = pack.querySelector(':scope > .filter-cluster-league');
        var typeNode = pack.querySelector(':scope > .filter-cluster-type');
        var gap = gapOf(pack);
        var mode = 'wide';
        if (sumWidths([contentWidth(league), contentWidth(typeNode)], gap) > pack.clientWidth + 1) {
            mode = 'split';
        }
        setMode(pack, mode);
    }

    function measurePlace(pack) {
        var stadium = pack.querySelector(':scope > .filter-cluster-stadium');
        var site = pack.querySelector(':scope > .filter-cluster-site');
        var gap = gapOf(pack);
        var mode = 'wide';
        if (sumWidths([contentWidth(stadium), contentWidth(site)], gap) > pack.clientWidth + 1) {
            mode = 'split';
        }
        setMode(pack, mode);
    }

    function measureMatch(pack) {
        var team = pack.querySelector(':scope > .filter-cluster-team');
        var opponent = pack.querySelector(':scope > .filter-cluster-opp');
        var gap = gapOf(pack);
        var mode = 'wide';
        if (sumWidths([contentWidth(team), contentWidth(opponent)], gap) > pack.clientWidth + 1) {
            mode = 'split';
        }
        setMode(pack, mode);
    }

    function measure(pack) {
        if (pack.classList.contains('filter-pack-scope')) {
            measureScope(pack);
            return;
        }
        if (pack.classList.contains('filter-pack-match')) {
            measureMatch(pack);
            return;
        }
        if (pack.classList.contains('filter-pack-place')) {
            measurePlace(pack);
            return;
        }
        var clusters = pack.querySelectorAll(':scope > .filter-cluster');
        var league = null;
        var team = null;
        var typeShow = null;
        var index;
        for (index = 0; index < clusters.length; index += 1) {
            var node = clusters[index];
            if (node.classList.contains('filter-cluster-league')) {
                league = node;
            } else if (node.classList.contains('filter-cluster-team')) {
                team = node;
            } else if (node.classList.contains('filter-cluster-type')) {
                typeShow = node;
            }
        }
        var leagueW = contentWidth(league);
        var teamW = contentWidth(team);
        var typeW = contentWidth(typeShow);
        var gap = parseFloat(window.getComputedStyle(pack).columnGap);
        if (!isFinite(gap)) {
            gap = 0;
        }
        var widths = [];
        if (leagueW > 0) {
            widths.push(leagueW);
        }
        if (teamW > 0) {
            widths.push(teamW);
        }
        if (typeW > 0) {
            widths.push(typeW);
        }
        var need = 0;
        widths.forEach(function (width, item) {
            need += width;
            if (item) {
                need += gap;
            }
        });
        var mode = 'wide';
        if (need > pack.clientWidth + 1) {
            if (teamW <= 0) {
                mode = 'split';
            } else {
                var pair = leagueW + teamW + (leagueW && teamW ? gap : 0);
                mode = pair <= pack.clientWidth + 1 ? 'split' : 'stack';
            }
        }
        if (pack.getAttribute('data-mode') !== mode) {
            pack.setAttribute('data-mode', mode);
        }
    }

    function watch(pack) {
        if (pack.__filterPackWatch || !window.ResizeObserver) {
            return;
        }
        var observer = new ResizeObserver(function () {
            measure(pack);
        });
        observer.observe(pack);
        pack.__filterPackWatch = observer;
    }

    function sync() {
        document.querySelectorAll('.filter-pack').forEach(function (pack) {
            watch(pack);
            measure(pack);
        });
    }

    window.dash_clientside.filter_pack.sync = sync;

    function boot() {
        sync();
        window.setTimeout(sync, 0);
        window.setTimeout(sync, 300);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
