// Report block renderers & parsers: builtin JS tables, pair stat-width sync,
// CSV parser & table renderer, static Rotation, and static Shot Chart.
(function () {
    var R = window.splashboardReport = window.splashboardReport || {};
    var state = R._state = R._state || {
        pairLayoutLock: false,
        pdfMeasurer: null,
        pdfHeaderPxCache: {},
        pdfFontOk: false,
        reportFontBinary: null
    };

    var CSV_MAX_BYTES = 65536;
    var CSV_MAX_COLUMNS = 24;
    var CSV_MAX_BODY_ROWS = 40;
    var CSV_TITLE_FALLBACK = 'Imported table';
    var CSV_OFFENSE_TITLE = 'Offense | Play-type Stats';
    var CSV_DEFENSE_TITLE = 'Defense | Play-type Stats';
    var CSV_ERR_EMPTY = 'This CSV is empty.';
    var CSV_ERR_UTF8 = 'This CSV is not UTF-8.';
    var CSV_ERR_HEADER = 'This CSV needs a header row.';
    var CSV_ERR_READ = 'This CSV could not be read.';
    var CSV_ERR_BYTES = 'This CSV is larger than 64KB.';
    var CSV_ERR_COLUMNS = 'This CSV has more than 24 columns.';
    var CSV_ERR_ROWS = 'This CSV has more than 40 rows.';
    var CSV_PPP_NUMBER = /^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$/;
    var ROTATION_EMPTY = 'No rotation chart for this game.';
    var ROTATION_ERROR = 'Could not load rotation.';
    var SHOT_CHART_EMPTY = 'No shot chart for this game.';
    var SHOT_CHART_ERROR = 'Could not load shot chart.';
    var SHOT_COURT_NATIVE_W = 380.05;
    var SHOT_COURT_ASPECT = 400.51 / SHOT_COURT_NATIVE_W;
    var SHOT_COURT_SCALE = 0.75;
    var SHOT_NAME_BLOCK_PX = 20;
    var ROTATION_FONT_SCALE = 0.75;
    var ROTATION_STATIC_CONFIG = {
        staticPlot: true,
        displayModeBar: false,
        responsive: false,
        scrollZoom: false,
        doubleClick: false
    };
    var A4_WIDTH_MM = 210;
    var A4_HEIGHT_MM = 297;
    var REPORT_FONT_NAME = 'NotoSansTC';
    var PDF_FAKE_BOLD_MM = 0.15;

    // Missing from NotoSansTC Regular. Screen fallback is zero-width or narrower than U+0020.
    // jsPDF otherwise measures each one as .notdef (1em) and then drops the glyph.
    // U+0020, U+00A0, U+2002, U+2003, and U+3000 stay.
    // cmap format 4 includes U+FF01, U+FF08, U+FF09, U+FF0C, U+FF1A, U+FF1B, U+FF1F.
    var REPORT_INVISIBLE_CHARS = /[\u00AD\u061C\u180E\u200B-\u200F\u202A-\u202E\u2060-\u2064\u2066-\u2069\uFEFF\u2004-\u200A\u202F\u205F]/g;

    var TABLE_TITLES = {
        score_group: 'Score',
        t_adv_df: 'Pace & Four Factors',
        adv_df: 'Advanced Stats',
        t_df: 'Team Stats',
        k_df: 'Key Stats',
        p_df_away: 'Away Player Stats',
        p_df_home: 'Home Player Stats',
        lineup_away: 'Away Lineup Stats',
        lineup_home: 'Home Lineup Stats'
    };
    var LOWER_BETTER = { Foul: 1, PF: 1, TO: 1, TOV: 1, 'TO%': 1 };
    var COL_GROUPS = [
        { name: '2PT', keys: ['2M', '2A', '2FG%'], subs: ['M', 'A', '%'] },
        { name: '3PT', keys: ['3M', '3A', '3FG%'], subs: ['M', 'A', '%'] },
        { name: 'FT', keys: ['FTM', 'FTA', 'FT%'], subs: ['M', 'A', '%'] },
        { name: 'REB', keys: ['OR', 'DR', 'REB'], subs: ['O', 'D', 'T'] },
        { name: 'Points in the Paint', keys: ['PIPM', 'PIPA', 'PIP'], subs: ['M', 'A', 'PT'] },
        { name: 'Second Chance Points', keys: ['SCP2M', 'SCP2A', 'SCP3M', 'SCP3A', 'SCP'], subs: ['2M', '2A', '3M', '3A', 'PT'] },
        { name: 'Fast Break Points', keys: ['FBP2M', 'FBP2A', 'FBP3M', 'FBP3A', 'FBP'], subs: ['2M', '2A', '3M', '3A', 'PT'] },
        { name: 'Points off Turnovers', keys: ['POT2M', 'POT2A', 'POT3M', 'POT3A', 'POT'], subs: ['2M', '2A', '3M', '3A', 'PT'] }
    ];
    var FF_KEYS = ['eFG%', 'TO%', 'ORB%', 'FT-R'];
    var KEY_STATS = ['PIP', 'SCP', 'FBP', 'POT'];
    var PAIR_WIDTHS = [
        ['p_df_home', 'p_df_away'],
        ['lineup_home', 'lineup_away']
    ];
    var STACK_PAIRS = [
        ['p_df_home', 'p_df_away'],
        ['lineup_home', 'lineup_away']
    ];

    var pairWidthJobs = {};
    var pairWidthTries = {};
    var pairMeasureCanvas;
    var pdfHeaderArm = false;

    function blockLocksSize(type) {
        return type === 'rotation' || type === 'shot_chart';
    }

    function isReportTable(type) {
        return type === 'builtin_table' || type === 'csv_table';
    }

    function locksResize(type) {
        return blockLocksSize(type) || isReportTable(type);
    }

    function stripReportInvisibleChars(text) {
        return String(text || '').replace(REPORT_INVISIBLE_CHARS, '');
    }

    function stripReportInvisibleIn(root) {
        if (!root || typeof document.createTreeWalker !== 'function') {
            return;
        }
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
        var node = walker.nextNode();
        while (node) {
            var cleaned = stripReportInvisibleChars(node.nodeValue);
            if (cleaned !== node.nodeValue) {
                node.nodeValue = cleaned;
            }
            node = walker.nextNode();
        }
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
        var columns = [];
        var indexes = [];
        obj.columns.forEach(function (col, i) {
            if (String(col).charAt(0) === '_') {
                return;
            }
            columns.push(col);
            indexes.push(i);
        });
        var rows = obj.data.map(function (row) {
            var rec = {};
            columns.forEach(function (col, i) {
                rec[col] = row[indexes[i]];
            });
            return rec;
        });
        return { columns: columns, rows: rows };
    }

    function rotationFigure() {
        var el = document.getElementById('report-rotation-figure');
        if (!el || !el.textContent) {
            return { _ui: 'empty' };
        }
        try {
            return JSON.parse(el.textContent);
        } catch (err) {
            return { _ui: 'error' };
        }
    }

    function rotationNativeHeightPx() {
        var fig = rotationFigure();
        if (!fig || fig._ui === 'empty' || fig._ui === 'error' || !fig.layout) {
            return 120;
        }
        return Math.max(120, Number(fig.layout.height) || 520);
    }

    function paintRotation(host) {
        if (!host) {
            return Promise.resolve();
        }
        host.textContent = '';
        var fig = rotationFigure();
        if (fig && fig._ui === 'error') {
            host.className += ' report-rotation-empty';
            host.textContent = ROTATION_ERROR;
            return Promise.resolve();
        }
        if (!fig || fig._ui === 'empty' || !fig.data) {
            host.className += ' report-rotation-empty';
            host.textContent = ROTATION_EMPTY;
            return Promise.resolve();
        }
        if (!window.Plotly || typeof window.Plotly.react !== 'function') {
            host.className += ' report-rotation-empty';
            host.textContent = ROTATION_ERROR;
            return Promise.resolve();
        }
        var gd = document.createElement('div');
        gd.className = 'report-rotation-plot';
        var hostW = Math.max(200, host.clientWidth || (host.parentElement && host.parentElement.clientWidth) || 640);
        var innerW = Math.round(hostW / ROTATION_FONT_SCALE);
        var innerH = rotationNativeHeightPx();
        var frame = document.createElement('div');
        frame.className = 'report-rotation-scale';
        frame.style.width = hostW + 'px';
        frame.style.height = Math.round(innerH * ROTATION_FONT_SCALE) + 'px';
        gd.style.width = innerW + 'px';
        gd.style.height = innerH + 'px';
        gd.style.transform = 'scale(' + ROTATION_FONT_SCALE + ')';
        gd.style.transformOrigin = 'top left';
        frame.appendChild(gd);
        host.appendChild(frame);
        var layout = Object.assign({}, fig.layout || {}, {
            width: innerW,
            height: innerH,
            autosize: false,
            dragmode: false
        });
        return window.Plotly.react(gd, fig.data, layout, ROTATION_STATIC_CONFIG).catch(function (err) {
            console.warn('Report rotation plot failed', err);
            host.textContent = ROTATION_ERROR;
            host.className += ' report-rotation-empty';
        });
    }

    function shotChartPayload() {
        var el = document.getElementById('report-shot-chart');
        if (!el || !el.textContent) {
            return { _ui: 'empty' };
        }
        try {
            return JSON.parse(el.textContent);
        } catch (err) {
            return { _ui: 'error' };
        }
    }

    function shotChartEstimatePx() {
        var fig = shotChartPayload();
        if (!fig || fig._ui === 'empty' || fig._ui === 'error' || !fig.away_src) {
            return 36;
        }
        var courtW = SHOT_COURT_NATIVE_W * SHOT_COURT_SCALE;
        return Math.round(courtW * SHOT_COURT_ASPECT + SHOT_NAME_BLOCK_PX);
    }

    function whenImageReady(img) {
        return new Promise(function (resolve) {
            if (img.complete && img.naturalWidth) {
                resolve();
                return;
            }
            img.addEventListener('load', function () { resolve(); }, { once: true });
            img.addEventListener('error', function () { resolve(); }, { once: true });
        });
    }

    function paintShotChart(host) {
        if (!host) {
            return Promise.resolve();
        }
        host.textContent = '';
        host.className = 'report-shot-chart-host';
        var fig = shotChartPayload();
        if (!fig || fig._ui === 'empty') {
            host.className += ' report-shot-chart-empty';
            host.textContent = SHOT_CHART_EMPTY;
            return Promise.resolve();
        }
        if (fig._ui === 'error' || !fig.away_src || !fig.home_src) {
            host.className += ' report-shot-chart-empty';
            host.textContent = SHOT_CHART_ERROR;
            return Promise.resolve();
        }
        var row = document.createElement('div');
        row.className = 'report-shot-chart-row';
        [
            { name: fig.away_name || 'Away', src: fig.away_src },
            { name: fig.home_name || 'Home', src: fig.home_src }
        ].forEach(function (side) {
            var team = document.createElement('div');
            team.className = 'report-shot-chart-team';
            var name = document.createElement('div');
            name.className = 'report-shot-chart-name';
            name.textContent = side.name;
            var img = document.createElement('img');
            img.className = 'report-shot-chart-court';
            img.alt = side.name + ' shot chart';
            img.src = side.src;
            team.appendChild(name);
            team.appendChild(img);
            row.appendChild(team);
        });
        host.appendChild(row);
        return Promise.all(Array.prototype.map.call(row.querySelectorAll('img'), whenImageReady));
    }

    function paintShotChartBlocks(paper) {
        var hosts = (paper || document).querySelectorAll('.report-shot-chart-host');
        var chain = Promise.resolve();
        Array.prototype.forEach.call(hosts, function (host) {
            chain = chain.then(function () {
                return paintShotChart(host);
            });
        });
        return chain;
    }

    function paintRotationBlocks(paper) {
        var hosts = (paper || document).querySelectorAll('.report-rotation-host');
        var chain = Promise.resolve();
        Array.prototype.forEach.call(hosts, function (host) {
            chain = chain.then(function () {
                return paintRotation(host);
            });
        });
        return chain;
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
        if (col === '+/-' || col === '#') {
            return false;
        }
        if (typeof val === 'string' && (val.indexOf('%') !== -1 || val.charAt(0) === '.')) {
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

    function winningIndexes(values, lower) {
        var present = [];
        values.forEach(function (value, index) {
            if (value === null || value === undefined || isNaN(value)) {
                return;
            }
            present.push({ index: index, value: value });
        });
        if (present.length < 2) {
            return [];
        }
        var first = present[0].value;
        var same = present.every(function (item) { return item.value === first; });
        if (same) {
            return [];
        }
        var best = first;
        present.forEach(function (item) {
            if (lower ? item.value < best : item.value > best) {
                best = item.value;
            }
        });
        var found = [];
        present.forEach(function (item) {
            if (item.value === best) {
                found.push(item.index);
            }
        });
        return found;
    }

    function winnerIndex(rows, columns, tableKey) {
        if (!rows || !rows.length) {
            return {};
        }
        if (tableKey !== 't_df' && tableKey !== 't_adv_df' && tableKey !== 'adv_df' && tableKey !== 'k_df' && tableKey !== 'score_group') {
            return {};
        }
        var map = {};
        columns.forEach(function (col) {
            if (col === 'Team' || col === 'Min' || col === '3P-R' || col === '3Pr') {
                return;
            }
            var values = rows.map(function (row) {
                return numVal(formatCell(col, row[col]));
            });
            var indexes = winningIndexes(values, !!LOWER_BETTER[col]);
            if (!indexes.length) {
                return;
            }
            map[col] = {};
            indexes.forEach(function (index) {
                map[col][index] = true;
            });
        });
        return map;
    }

    function headerLabel(col) {
        if (col === 'AST') {
            return 'AS';
        }
        if (col === 'PTS') {
            return 'PT';
        }
        return col;
    }

    function isLineupTable(tableKey) {
        return tableKey === 'lineup_home' || tableKey === 'lineup_away';
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
            if (isLineupTable(tableKey) && KEY_STATS.indexOf(col) !== -1 && !used.__key) {
                var presentKeys = KEY_STATS.filter(function (k) { return columns.indexOf(k) !== -1; });
                presentKeys.forEach(function (k) { used[k] = 1; });
                used.__key = 1;
                top.push({ text: 'Key Stats', span: presentKeys.length, group: true, cols: presentKeys });
                presentKeys.forEach(function (k) { sub.push({ label: k, col: k }); });
                return;
            }
            var group = COL_GROUPS.filter(function (g) { return g.keys.indexOf(col) !== -1; })[0];
            if (group) {
                var present = group.keys.filter(function (k) { return columns.indexOf(k) !== -1; });
                present.forEach(function (k) { used[k] = 1; });
                top.push({ text: group.name, span: present.length, group: true, cols: present });
                present.forEach(function (k) {
                    sub.push({ label: group.subs[group.keys.indexOf(k)] || k, col: k });
                });
                return;
            }
            if (ff.indexOf(col) !== -1 && !used['__ff']) {
                used['__ff'] = 1;
                ff.forEach(function (k) { used[k] = 1; });
                top.push({ text: 'FOUR FACTORS', span: ff.length, group: true, cols: ff.slice() });
                ff.forEach(function (k) { sub.push({ label: k, col: k }); });
                return;
            }
            if (used[col]) {
                return;
            }
            used[col] = 1;
            top.push({ text: headerLabel(col), span: 1, rowSpan: 2, col: col, cols: [col] });
        });
        top.forEach(function (cell, index) {
            var atRim = index + 1 >= top.length;
            if (atRim) {
                if (!cell.group) {
                    return;
                }
            } else {
                var next = top[index + 1];
                if (!cell.group && !next.group) {
                    return;
                }
            }
            cell.edge = true;
            var cols = cell.cols || [];
            var last = cols[cols.length - 1];
            if (!last) {
                return;
            }
            sub.forEach(function (item) {
                if (item.col === last) {
                    item.edge = true;
                }
            });
        });
        return { top: top, sub: sub };
    }

    function pairForKey(tableKey) {
        for (var i = 0; i < PAIR_WIDTHS.length; i++) {
            if (PAIR_WIDTHS[i][0] === tableKey || PAIR_WIDTHS[i][1] === tableKey) {
                return PAIR_WIDTHS[i];
            }
        }
        return null;
    }

    function isNameCol(col) {
        return col === 'Player' || col === 'Lineup' || col === 'Lineups';
    }

    function readLeafCols(table) {
        try {
            var cols = JSON.parse(table.getAttribute('data-cols') || '[]');
            return Array.isArray(cols) ? cols : [];
        } catch (err) {
            return [];
        }
    }

    function pairTextWidth(el) {
        var cs = window.getComputedStyle(el);
        if (!pairMeasureCanvas) {
            pairMeasureCanvas = document.createElement('canvas');
        }
        var ctx = pairMeasureCanvas.getContext('2d');
        var fontStyle = cs.fontStyle && cs.fontStyle !== 'normal' ? cs.fontStyle + ' ' : '';
        ctx.font = fontStyle + (cs.fontWeight || '400') + ' ' + (cs.fontSize || '9px') + ' ' + (cs.fontFamily || 'sans-serif');
        var pad = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
        var left = parseFloat(cs.borderLeftWidth) || 0;
        var right = parseFloat(cs.borderRightWidth) || 0;
        // Collapsed borders are shared. Count the wider edge once.
        var border = Math.max(left, right);
        return Math.ceil(ctx.measureText(el.textContent || '').width + pad + border);
    }

    function paperScale(paperRect) {
        return {
            x: paperRect.width ? (A4_WIDTH_MM / paperRect.width) : 1,
            y: paperRect.height ? (A4_HEIGHT_MM / paperRect.height) : 1
        };
    }

    function scaleXY(scale) {
        if (scale && typeof scale === 'object') {
            return { x: scale.x || 1, y: scale.y || 1 };
        }
        var n = Number(scale) || 1;
        return { x: n, y: n };
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

    function paperPxScale() {
        var paper = document.querySelector('#report-papers .report-paper');
        var rect = paper ? paper.getBoundingClientRect() : null;
        if (!rect || rect.width < 1) {
            return {
                x: A4_WIDTH_MM / (210 / 25.4 * 96),
                y: A4_HEIGHT_MM / (297 / 25.4 * 96)
            };
        }
        return paperScale(rect);
    }

    function pdfMeasurerDoc() {
        if (state.pdfMeasurer) {
            return state.pdfMeasurer;
        }
        if (!window.jspdf || !window.jspdf.jsPDF || !state.reportFontBinary || !R.registerReportFont) {
            return null;
        }
        var pdf = new window.jspdf.jsPDF({
            orientation: 'portrait',
            unit: 'mm',
            format: 'a4'
        });
        R.registerReportFont(pdf);
        if (!state.pdfFontOk) {
            return null;
        }
        state.pdfMeasurer = pdf;
        return pdf;
    }

    function armPdfHeaderMeasure() {
        if (pdfHeaderArm || state.pdfMeasurer || !R.ensureReportLibs || !R.loadReportFont) {
            return;
        }
        pdfHeaderArm = true;
        R.ensureReportLibs().then(function () {
            return R.loadReportFont();
        }).then(function () {
            pdfHeaderArm = false;
            state.pdfMeasurer = null;
            state.pdfHeaderPxCache = {};
            PAIR_WIDTHS.forEach(syncPairColumnWidths);
        }).catch(function () {
            pdfHeaderArm = false;
        });
    }

    function pdfHeaderFloorPx(text, fontPx, bold) {
        var pdf = pdfMeasurerDoc();
        if (!pdf || !text) {
            return 0;
        }
        var scale = paperPxScale();
        var pt = pxToPt(fontPx, scale);
        var key = text + '|' + pt + '|' + (bold ? 'b' : '') + '|' + scale.x.toFixed(4);
        if (state.pdfHeaderPxCache[key]) {
            return state.pdfHeaderPxCache[key];
        }
        pdf.setFontSize(pt);
        try {
            pdf.setFont(state.pdfFontOk ? REPORT_FONT_NAME : 'helvetica', 'normal');
        } catch (err) {
            pdf.setFont('helvetica', 'normal');
        }
        var textMm = pdf.getTextWidth(text);
        var boxMm = textMm + (bold ? PDF_FAKE_BOLD_MM : 0) + 0.8;
        var px = scale.x ? Math.ceil(boxMm / scale.x) : 0;
        state.pdfHeaderPxCache[key] = px;
        return px;
    }

    function measureLeafFloors(table) {
        var floors = {};
        var nodes = table.querySelectorAll('th[data-col], td[data-col]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (el.colSpan > 1) {
                continue;
            }
            var col = el.getAttribute('data-col');
            var width = pairTextWidth(el);
            if (el.tagName === 'TH' && !isNameCol(col)) {
                var headerStyle = window.getComputedStyle(el);
                var pdfFloor = pdfHeaderFloorPx(
                    (el.textContent || '').trim(),
                    parseFloat(headerStyle.fontSize) || 9,
                    fontWeightNum(headerStyle) >= 600
                );
                if (!pdfFloor) {
                    armPdfHeaderMeasure();
                }
                if (pdfFloor > width) {
                    width = pdfFloor;
                }
            }
            var lineupBody = (col === 'Lineup' || col === 'Lineups') && el.tagName !== 'TH';
            if (lineupBody) {
                if (width > (floors._nameNeed || 0)) {
                    floors._nameNeed = width;
                }
                continue;
            }
            if (floors[col] == null || width > floors[col]) {
                floors[col] = width;
            }
            if (isNameCol(col) && width > (floors._nameNeed || 0)) {
                floors._nameNeed = width;
            }
        }
        return floors;
    }

    function applyPairColGroup(table, cols, widths, hostW) {
        var sum = 0;
        cols.forEach(function (col) {
            sum += widths[col] || 0;
        });
        var nextWidth = sum > hostW + 1 ? sum + 'px' : '100%';
        var cg = table.querySelector('colgroup');
        if (!cg) {
            cg = document.createElement('colgroup');
            table.insertBefore(cg, table.firstChild);
        }
        var same = table.style.tableLayout === 'fixed'
            && table.style.width === nextWidth
            && cg.children.length === cols.length;
        if (same) {
            for (var i = 0; i < cols.length; i++) {
                if (cg.children[i].style.width !== (widths[cols[i]] || 0) + 'px') {
                    same = false;
                    break;
                }
            }
        }
        if (same) {
            return false;
        }
        while (cg.firstChild) {
            cg.removeChild(cg.firstChild);
        }
        cols.forEach(function (col) {
            var c = document.createElement('col');
            c.style.width = (widths[col] || 0) + 'px';
            cg.appendChild(c);
        });
        table.style.tableLayout = 'fixed';
        table.style.width = nextWidth;
        table.setAttribute('data-host-w', String(hostW));
        return true;
    }

    function syncPairColumnWidths(pair) {
        if (state.pairLayoutLock || !pair) {
            return false;
        }
        var entries = [];
        var pending = false;
        pair.forEach(function (key) {
            document.querySelectorAll('.report-table-host[data-table-host="' + key + '"]').forEach(function (host) {
                var table = host.querySelector('.report-js-table');
                if (!table || !table.getAttribute('data-cols')) {
                    return;
                }
                var cols = readLeafCols(table);
                if (!cols.length) {
                    return;
                }
                if (host.clientWidth < 1) {
                    pending = true;
                    return;
                }
                entries.push({ host: host, table: table, cols: cols });
            });
        });
        if (!entries.length) {
            return pending;
        }
        state.pairLayoutLock = true;
        try {
            var stat = {};
            entries.forEach(function (entry) {
                var floors = measureLeafFloors(entry.table);
                entry.floors = floors;
                entry.cols.forEach(function (col) {
                    if (isNameCol(col)) {
                        return;
                    }
                    var floor = floors[col] || 0;
                    if (!stat[col] || floor > stat[col]) {
                        stat[col] = floor;
                    }
                });
            });
            var statCols = [];
            var seenStat = {};
            entries.forEach(function (entry) {
                entry.cols.forEach(function (col) {
                    if (isNameCol(col) || seenStat[col]) {
                        return;
                    }
                    seenStat[col] = 1;
                    statCols.push(col);
                });
            });
            entries.forEach(function (entry) {
                var nameCol = null;
                var statSum = 0;
                entry.cols.forEach(function (col) {
                    if (isNameCol(col)) {
                        if (!nameCol) {
                            nameCol = col;
                        }
                        return;
                    }
                    statSum += stat[col] || 0;
                });
                var headerFloor = nameCol ? (entry.floors[nameCol] || 0) : 0;
                var nameNeed = entry.floors._nameNeed || 0;
                if (nameNeed < headerFloor) {
                    nameNeed = headerFloor;
                }
                entry.hostW = Math.floor(entry.host.clientWidth);
                entry.nameCol = nameCol;
                entry.nameNeed = nameNeed;
                entry.statSum = statSum;
                var spare = entry.hostW - statSum - nameNeed;
                entry.spare = spare > 0 ? spare : 0;
            });
            var sharedSpare = entries.length ? entries[0].spare : 0;
            entries.forEach(function (entry) {
                if (entry.spare < sharedSpare) {
                    sharedSpare = entry.spare;
                }
            });
            var extraEach = statCols.length ? Math.floor(sharedSpare / statCols.length) : 0;
            var leftoverPx = statCols.length ? sharedSpare - extraEach * statCols.length : 0;
            var bonus = {};
            statCols.forEach(function (col, index) {
                bonus[col] = extraEach + (index < leftoverPx ? 1 : 0);
            });
            var changed = false;
            entries.forEach(function (entry) {
                var widths = {};
                var grown = 0;
                entry.cols.forEach(function (col) {
                    if (isNameCol(col)) {
                        return;
                    }
                    widths[col] = (stat[col] || 0) + (bonus[col] || 0);
                    grown += widths[col];
                });
                var nameW = entry.hostW - grown;
                var headerFloor = entry.nameCol ? (entry.floors[entry.nameCol] || 0) : 0;
                if (nameW < headerFloor) {
                    nameW = headerFloor;
                }
                if (entry.nameCol) {
                    widths[entry.nameCol] = nameW;
                }
                entry.cols.forEach(function (col) {
                    if (isNameCol(col) && col !== entry.nameCol) {
                        widths[col] = entry.floors[col] || 0;
                    }
                });
                if (applyPairColGroup(entry.table, entry.cols, widths, entry.hostW)) {
                    changed = true;
                }
            });
            if (changed && R.fitTableBlocksOnGrid) {
                var grids = [];
                entries.forEach(function (entry) {
                    var gridEl = entry.table.closest('.report-grid');
                    var grid = gridEl && gridEl.gridstack;
                    if (grid && grids.indexOf(grid) === -1) {
                        grids.push(grid);
                    }
                });
                grids.forEach(function (grid) {
                    R.fitTableBlocksOnGrid(grid);
                });
            }
        } finally {
            state.pairLayoutLock = false;
        }
        if (!pending && R.commitTableResize) {
            document.querySelectorAll('.grid-stack-item[data-resize-commit="1"]').forEach(function (item) {
                if (pair.indexOf(item.getAttribute('data-table-key')) === -1) {
                    return;
                }
                var gridEl = item.closest('.report-grid');
                var grid = gridEl && gridEl.gridstack;
                R.commitTableResize(grid, item);
            });
        }
        return pending;
    }

    function schedulePairWidths(tableKey) {
        var pair = pairForKey(tableKey);
        if (!pair || pairWidthJobs[pair[0]]) {
            return;
        }
        pairWidthJobs[pair[0]] = 1;
        window.requestAnimationFrame(function () {
            window.requestAnimationFrame(function () {
                pairWidthJobs[pair[0]] = 0;
                var pending = syncPairColumnWidths(pair);
                var tries = pairWidthTries[pair[0]] || 0;
                if (pending && tries < 8) {
                    pairWidthTries[pair[0]] = tries + 1;
                    window.setTimeout(function () {
                        schedulePairWidths(tableKey);
                    }, 50);
                } else if (!pending) {
                    pairWidthTries[pair[0]] = 0;
                }
            });
        });
    }

    function pairWidthsStale() {
        var stale = false;
        PAIR_WIDTHS.forEach(function (pair) {
            pair.forEach(function (key) {
                document.querySelectorAll('.report-table-host[data-table-host="' + key + '"]').forEach(function (host) {
                    var table = host.querySelector('.report-js-table');
                    if (!table || host.clientWidth < 1) {
                        return;
                    }
                    if (!table.querySelector('colgroup')) {
                        stale = true;
                        return;
                    }
                    var prev = parseFloat(table.getAttribute('data-host-w') || '0');
                    if (Math.abs(prev - Math.floor(host.clientWidth)) > 1) {
                        stale = true;
                    }
                });
            });
        });
        return stale;
    }

    function refreshPairWidthsIfStale() {
        if (!pairWidthsStale()) {
            return;
        }
        PAIR_WIDTHS.forEach(syncPairColumnWidths);
    }

    function measureTableMaxContentWidth(item) {
        var table = item.querySelector('.report-js-table');
        if (!table) {
            return 0;
        }
        var clone = table.cloneNode(true);
        var cg = clone.querySelector('colgroup');
        if (cg) {
            cg.remove();
        }
        clone.style.cssText = 'position:absolute;left:-10000px;top:0;width:auto;max-width:none;table-layout:auto;visibility:hidden;';
        document.body.appendChild(clone);
        var width = clone.scrollWidth || clone.offsetWidth || 0;
        document.body.removeChild(clone);
        return width;
    }

    function csvBlockTitle(filename, coloring) {
        var name = String(filename || '').replace(/\\/g, '/').split('/').pop();
        var lower = name.toLowerCase();
        if (coloring === 'ppp') {
            if (lower.slice(-8) === '_off.csv') {
                return CSV_OFFENSE_TITLE;
            }
            if (lower.slice(-8) === '_def.csv') {
                return CSV_DEFENSE_TITLE;
            }
        }
        if (/\.csv$/i.test(name)) {
            name = name.slice(0, -4);
        }
        if (!String(name || '').trim()) {
            return CSV_TITLE_FALLBACK;
        }
        return name;
    }

    function pppCellStyle(text) {
        var token = String(text == null ? '' : text).trim();
        if (!CSV_PPP_NUMBER.test(token)) {
            return null;
        }
        var negative = token.charAt(0) === '-';
        var body = token.charAt(0) === '+' || negative ? token.slice(1) : token;
        var parts = body.split('.');
        var whole = parts[0] || '0';
        var frac = parts[1] || '';
        var scale = frac.length;
        var magnitude = parseInt(whole + frac, 10);
        if (negative) {
            magnitude = -magnitude;
        }
        var unit = Math.pow(10, scale);
        if (magnitude >= unit) {
            return { color: '#0077b6', fontWeight: '700' };
        }
        if (magnitude * 10 < 8 * unit) {
            return { color: '#e63946', fontWeight: '700' };
        }
        return null;
    }

    function parseCsvRecords(text) {
        var rows = [];
        var row = [];
        var field = '';
        var i = 0;
        var inQuotes = false;
        var afterQuote = false;
        var fieldStarted = false;
        function pushField() {
            row.push(field);
            field = '';
            afterQuote = false;
            fieldStarted = false;
        }
        function pushRow() {
            pushField();
            rows.push(row);
            row = [];
        }
        while (i < text.length) {
            var c = text.charAt(i);
            if (inQuotes) {
                if (c === '"') {
                    if (text.charAt(i + 1) === '"') {
                        field += '"';
                        i += 2;
                        continue;
                    }
                    inQuotes = false;
                    afterQuote = true;
                    i += 1;
                    continue;
                }
                field += c;
                i += 1;
                continue;
            }
            if (c === '"') {
                if (fieldStarted) {
                    throw new Error(CSV_ERR_READ);
                }
                inQuotes = true;
                fieldStarted = true;
                i += 1;
                continue;
            }
            if (c === ',') {
                pushField();
                i += 1;
                continue;
            }
            if (c === '\n' || c === '\r') {
                pushRow();
                i += 1;
                if (c === '\r' && text.charAt(i) === '\n') {
                    i += 1;
                }
                continue;
            }
            if (afterQuote) {
                throw new Error(CSV_ERR_READ);
            }
            field += c;
            fieldStarted = true;
            i += 1;
        }
        if (inQuotes) {
            throw new Error(CSV_ERR_READ);
        }
        if (fieldStarted || afterQuote || field.length || row.length) {
            pushRow();
        }
        return rows;
    }

    function parseCsvTable(text) {
        var source = String(text == null ? '' : text);
        if (source.charCodeAt(0) === 0xFEFF) {
            source = source.slice(1);
        }
        if (!source.trim()) {
            throw new Error(CSV_ERR_EMPTY);
        }
        var records = parseCsvRecords(source);
        if (!records.length) {
            throw new Error(CSV_ERR_EMPTY);
        }
        var columns = records[0].map(function (cell) {
            return cell == null ? '' : String(cell);
        });
        var headerText = columns.some(function (cell) {
            return String(cell).trim();
        });
        if (!headerText) {
            throw new Error(CSV_ERR_HEADER);
        }
        if (columns.length > CSV_MAX_COLUMNS) {
            throw new Error(CSV_ERR_COLUMNS);
        }
        var body = records.slice(1);
        if (body.length > CSV_MAX_BODY_ROWS) {
            throw new Error(CSV_ERR_ROWS);
        }
        var width = columns.length;
        var rows = body.map(function (record) {
            var cells = record.map(function (cell) {
                return cell == null ? '' : String(cell);
            });
            if (cells.length < width) {
                while (cells.length < width) {
                    cells.push('');
                }
            } else if (cells.length > width) {
                cells = cells.slice(0, width);
            }
            return cells;
        });
        return { columns: columns, rows: rows };
    }

    function readCsvStore(node) {
        var store = node && node.querySelector('script.report-csv-store');
        if (!store || !store.textContent) {
            return null;
        }
        try {
            return JSON.parse(store.textContent);
        } catch (err) {
            return null;
        }
    }

    function writeCsvStore(node, block) {
        var store = node.querySelector('script.report-csv-store');
        if (!store) {
            store = document.createElement('script');
            store.type = 'application/json';
            store.className = 'report-csv-store no-print';
            node.appendChild(store);
        }
        store.textContent = JSON.stringify({
            title: block.title || CSV_TITLE_FALLBACK,
            coloring: block.coloring === 'ppp' ? 'ppp' : 'plain',
            columns: block.columns || [],
            rows: block.rows || []
        });
    }

    function isCsvLabelHeader(text) {
        var token = String(text == null ? '' : text).trim().toLowerCase();
        return token === 'play type' || token === 'play-type';
    }

    function csvDefaultW(coloring) {
        return coloring === 'ppp' ? 6 : 12;
    }

    function csvHostWidth(item) {
        var host = item && item.querySelector('.report-table-host');
        var width = host ? host.clientWidth : 0;
        if (width < 1 && item) {
            width = item.clientWidth || 0;
        }
        return Math.floor(width);
    }

    function readCsvFloors(table) {
        try {
            var parsed = JSON.parse(table.getAttribute('data-csv-floors') || '[]');
            return Array.isArray(parsed) ? parsed : [];
        } catch (err) {
            return [];
        }
    }

    function measureCsvFloors(table) {
        var heads = table.querySelectorAll('thead th');
        var rows = table.querySelectorAll('tbody tr');
        var floors = [];
        for (var i = 0; i < heads.length; i++) {
            var label = heads[i].getAttribute('data-csv-label') === '1';
            var max = pairTextWidth(heads[i]);
            if (!label) {
                for (var r = 0; r < rows.length; r++) {
                    var cell = rows[r].children[i];
                    if (!cell) {
                        continue;
                    }
                    var width = pairTextWidth(cell);
                    if (width > max) {
                        max = width;
                    }
                }
            }
            floors.push(Math.max(1, max));
        }
        table.setAttribute('data-csv-floors', JSON.stringify(floors));
        return floors;
    }

    function applyCsvColGroup(table, widths, hostW) {
        var keys = [];
        var map = {};
        widths.forEach(function (width, index) {
            var key = String(index);
            keys.push(key);
            map[key] = width;
        });
        applyPairColGroup(table, keys, map, hostW);
    }

    function applyCsvColumns(item, remeasure) {
        var table = item && item.querySelector('.report-js-table[data-csv-coloring]');
        if (!table) {
            return;
        }
        var hostW = csvHostWidth(item);
        if (hostW < 1) {
            return;
        }
        var heads = table.querySelectorAll('thead th');
        var count = heads.length;
        if (!count) {
            return;
        }
        if (remeasure || !readCsvFloors(table).length) {
            measureCsvFloors(table);
        }
        var floors = readCsvFloors(table);
        if (floors.length !== count) {
            floors = [];
            for (var i = 0; i < count; i++) {
                floors.push(1);
            }
        }
        var labels = [];
        for (var c = 0; c < count; c++) {
            if (heads[c].getAttribute('data-csv-label') === '1') {
                labels.push(c);
            }
        }
        var widths = [];
        if (!labels.length) {
            var each = Math.floor(hostW / count);
            var extra = hostW - each * count;
            for (var n = 0; n < count; n++) {
                widths.push(Math.max(1, each + (n < extra ? 1 : 0)));
            }
            applyCsvColGroup(table, widths, hostW);
            return;
        }
        var statSum = 0;
        var labelSum = 0;
        for (var k = 0; k < count; k++) {
            if (labels.indexOf(k) === -1) {
                statSum += floors[k];
            } else {
                labelSum += floors[k];
            }
        }
        if (statSum + labelSum > hostW + 1) {
            for (var a = 0; a < count; a++) {
                widths.push(floors[a]);
            }
        } else {
            var leftover = hostW - statSum - labelSum;
            var share = Math.floor(leftover / labels.length);
            var rem = leftover - share * labels.length;
            var seen = 0;
            for (var b = 0; b < count; b++) {
                if (labels.indexOf(b) === -1) {
                    widths.push(floors[b]);
                } else {
                    widths.push(floors[b] + share + (seen < rem ? 1 : 0));
                    seen += 1;
                }
            }
        }
        applyCsvColGroup(table, widths, hostW);
    }

    function paintCsvTable(host, block) {
        if (!host) {
            return;
        }
        host.innerHTML = '';
        var columns = block.columns || [];
        var rows = block.rows || [];
        if (!columns.length) {
            host.textContent = '—';
            host.className = 'report-table-host';
            return;
        }
        var coloring = block.coloring === 'ppp';
        var pppIndex = {};
        if (coloring) {
            columns.forEach(function (col, index) {
                if (String(col == null ? '' : col).trim() === 'PPP') {
                    pppIndex[index] = 1;
                }
            });
        }
        var table = document.createElement('table');
        table.className = 'text-nowrap report-js-table';
        table.setAttribute('data-csv-coloring', coloring ? 'ppp' : 'plain');
        var thead = document.createElement('thead');
        var headRow = document.createElement('tr');
        var labeling = coloring;
        columns.forEach(function (col) {
            var th = document.createElement('th');
            th.textContent = col == null ? '' : String(col);
            if (labeling && isCsvLabelHeader(col)) {
                th.setAttribute('data-csv-label', '1');
            }
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);
        var tbody = document.createElement('tbody');
        rows.forEach(function (record) {
            var tr = document.createElement('tr');
            columns.forEach(function (_col, index) {
                var td = document.createElement('td');
                var text = record && record[index] != null ? String(record[index]) : '';
                td.textContent = text;
                if (labeling && isCsvLabelHeader(columns[index])) {
                    td.className = 'report-lineup-name';
                    td.style.fontWeight = '700';
                }
                if (pppIndex[index]) {
                    var tone = pppCellStyle(text);
                    if (tone) {
                        td.style.color = tone.color;
                        td.style.fontWeight = tone.fontWeight;
                    }
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        host.appendChild(table);
        host.className = 'report-table-host';
    }

    function teamStripeColor(row, rIdx) {
        var match = tablePayload().match || {};
        var away = match.away_team || '';
        var home = match.home_team || '';
        var name = row && row.Team != null ? String(row.Team) : '';
        if (away && home && away !== home) {
            if (name === home) {
                return '#0077b6';
            }
            if (name === away) {
                return '#94a3b8';
            }
        }
        return rIdx === 0 ? '#0077b6' : '#94a3b8';
    }

    function paintTable(host, tableKey) {
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
        var edgeCols = {};
        if (grouped) {
            grouped.top.forEach(function (cell) {
                if (!cell.edge) {
                    return;
                }
                var cols = cell.cols || [];
                var last = cols[cols.length - 1];
                if (last) {
                    edgeCols[last] = true;
                }
            });
        }
        var table = document.createElement('table');
        table.className = isLineupTable(tableKey)
            ? 'text-nowrap report-js-table report-lineup-table'
            : 'text-nowrap report-js-table';
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
                if (cell.col) {
                    th.setAttribute('data-col', cell.col);
                }
                tr1.appendChild(th);
            });
            thead.appendChild(tr1);
            if (grouped.sub.length) {
                var tr2 = document.createElement('tr');
                grouped.sub.forEach(function (item) {
                    var th = document.createElement('th');
                    th.textContent = item.label;
                    if (item.col) {
                        th.setAttribute('data-col', item.col);
                    }
                    tr2.appendChild(th);
                });
                thead.appendChild(tr2);
            }
        } else {
            var tr = document.createElement('tr');
            columns.forEach(function (col) {
                var th = document.createElement('th');
                th.textContent = headerLabel(col);
                th.setAttribute('data-col', col);
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
                if (col === 'Lineup' || col === 'Lineups') {
                    td.className = 'report-lineup-name';
                }
                if (col === '+/-') {
                    var st = plusMinusStyle(row[col]);
                    td.style.color = st.color;
                    td.style.fontWeight = st.fontWeight;
                }
                if (winners[col] && winners[col][rIdx]) {
                    td.style.color = '#0077b6';
                    td.style.fontWeight = '700';
                }
                if (edgeCols[col]) {
                    td.classList.add('braves-group-end');
                }
                if (cIdx === 0 && (col === 'Team' || tableKey === 't_df' || tableKey === 't_adv_df' || tableKey === 'adv_df' || tableKey === 'k_df' || tableKey === 'score_group') && rows.length === 2) {
                    td.style.borderLeft = '3.5px solid ' + teamStripeColor(row, rIdx);
                }
                if (dnp && col === 'Min') {
                    td.colSpan = Math.max(1, columns.length - cIdx);
                    td.style.fontWeight = '700';
                    td.style.color = '#94a3b8';
                } else {
                    td.setAttribute('data-col', col);
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        table.setAttribute('data-cols', JSON.stringify(columns));
        host.appendChild(table);
        host.className = 'report-table-host';
        if (pairForKey(tableKey)) {
            schedulePairWidths(tableKey);
        }
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

    Object.assign(R, {
        CSV_MAX_BYTES: CSV_MAX_BYTES,
        CSV_TITLE_FALLBACK: CSV_TITLE_FALLBACK,
        CSV_ERR_EMPTY: CSV_ERR_EMPTY,
        CSV_ERR_UTF8: CSV_ERR_UTF8,
        CSV_ERR_READ: CSV_ERR_READ,
        CSV_ERR_BYTES: CSV_ERR_BYTES,
        ROTATION_FONT_SCALE: ROTATION_FONT_SCALE,
        PAIR_WIDTHS: PAIR_WIDTHS,
        STACK_PAIRS: STACK_PAIRS,
        blockLocksSize: blockLocksSize,
        locksResize: locksResize,
        isReportTable: isReportTable,
        stripReportInvisibleChars: stripReportInvisibleChars,
        stripReportInvisibleIn: stripReportInvisibleIn,
        rotationNativeHeightPx: rotationNativeHeightPx,
        paintRotation: paintRotation,
        paintRotationBlocks: paintRotationBlocks,
        shotChartEstimatePx: shotChartEstimatePx,
        paintShotChart: paintShotChart,
        paintShotChartBlocks: paintShotChartBlocks,
        skipFourFactorsGroup: skipFourFactorsGroup,
        groupedHeader: groupedHeader,
        winningIndexes: winningIndexes,
        winnerIndex: winnerIndex,
        pairForKey: pairForKey,
        syncPairColumnWidths: syncPairColumnWidths,
        schedulePairWidths: schedulePairWidths,
        refreshPairWidthsIfStale: refreshPairWidthsIfStale,
        measureTableMaxContentWidth: measureTableMaxContentWidth,
        parseCsvTable: parseCsvTable,
        pppCellStyle: pppCellStyle,
        csvBlockTitle: csvBlockTitle,
        isCsvLabelHeader: isCsvLabelHeader,
        csvDefaultW: csvDefaultW,
        readCsvStore: readCsvStore,
        writeCsvStore: writeCsvStore,
        applyCsvColumns: applyCsvColumns,
        paintCsvTable: paintCsvTable,
        paintTable: paintTable,
        fillBlockTitle: fillBlockTitle,
        paperScale: paperScale,
        scaleXY: scaleXY,
        pxToPt: pxToPt,
        fontWeightNum: fontWeightNum
    });
})();
