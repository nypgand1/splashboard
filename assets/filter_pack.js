(function () {
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.filter_pack = window.dash_clientside.filter_pack || {};

    function measureClusterContentWidth(cluster) {
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

    function readPackGapPx(pack) {
        var gap = parseFloat(window.getComputedStyle(pack).columnGap);
        return isFinite(gap) ? gap : 0;
    }

    function sumClusterWidths(widths, gap) {
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

    function setFilterPackMode(pack, mode) {
        if (pack.getAttribute('data-mode') !== mode) {
            pack.setAttribute('data-mode', mode);
        }
    }

    function measureTwoClusterPack(pack, selA, selB) {
        var first = pack.querySelector(':scope > ' + selA);
        var second = pack.querySelector(':scope > ' + selB);
        var gap = readPackGapPx(pack);
        var mode = 'wide';
        if (sumClusterWidths([measureClusterContentWidth(first), measureClusterContentWidth(second)], gap) > pack.clientWidth + 1) {
            mode = 'split';
        }
        setFilterPackMode(pack, mode);
    }

    function measureFilterPack(pack) {
        if (pack.classList.contains('filter-pack-scope')) {
            measureTwoClusterPack(pack, '.filter-cluster-league', '.filter-cluster-type');
            return;
        }
        if (pack.classList.contains('filter-pack-match')) {
            measureTwoClusterPack(pack, '.filter-cluster-team', '.filter-cluster-opp');
            return;
        }
        if (pack.classList.contains('filter-pack-place')) {
            measureTwoClusterPack(pack, '.filter-cluster-stadium', '.filter-cluster-site');
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
        var leagueW = measureClusterContentWidth(league);
        var teamW = measureClusterContentWidth(team);
        var typeW = measureClusterContentWidth(typeShow);
        var gap = readPackGapPx(pack);
        var need = sumClusterWidths([leagueW, teamW, typeW], gap);
        var mode = 'wide';
        if (need > pack.clientWidth + 1) {
            if (teamW <= 0) {
                mode = 'split';
            } else {
                var pair = leagueW + teamW + (leagueW && teamW ? gap : 0);
                mode = pair <= pack.clientWidth + 1 ? 'split' : 'stack';
            }
        }
        setFilterPackMode(pack, mode);
    }

    function observeFilterPackResize(pack) {
        if (pack.__filterPackWatch || !window.ResizeObserver) {
            return;
        }
        var observer = new ResizeObserver(function () {
            measureFilterPack(pack);
        });
        observer.observe(pack);
        pack.__filterPackWatch = observer;
    }

    function syncFilterPacks() {
        document.querySelectorAll('.filter-pack').forEach(function (pack) {
            observeFilterPackResize(pack);
            measureFilterPack(pack);
        });
    }

    function fillProbeHost(id, options, fallback) {
        var host = document.getElementById(id);
        if (!host) {
            return;
        }
        var labels = [];
        (options || []).forEach(function (item) {
            if (item && item.label) {
                labels.push(String(item.label));
            } else if (typeof item === 'string' && item) {
                labels.push(item);
            }
        });
        if (!labels.length) {
            labels.push(fallback);
        }
        while (host.firstChild) {
            host.removeChild(host.firstChild);
        }
        labels.forEach(function (label) {
            var span = document.createElement('span');
            span.className = 'select-sizer-probe';
            span.setAttribute('aria-hidden', 'true');
            span.textContent = label;
            host.appendChild(span);
        });
    }

    function fillSelectSizerProbes(teamOptions, opponentLabels, stadiumOptions) {
        fillProbeHost('ts-team-probes', teamOptions, 'All Teams');
        fillProbeHost('ts-opponent-probes', opponentLabels, 'vs All Teams');
        fillProbeHost('ts-stadium-probes', stadiumOptions, 'All Stadiums');
        syncFilterPacks();
    }

    window.dash_clientside.filter_pack.sync = syncFilterPacks;
    window.dash_clientside.filter_pack.fillProbes = fillSelectSizerProbes;

    function bootFilterPacks() {
        syncFilterPacks();
        window.setTimeout(syncFilterPacks, 0);
        window.setTimeout(syncFilterPacks, 300);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootFilterPacks);
    } else {
        bootFilterPacks();
    }
})();
