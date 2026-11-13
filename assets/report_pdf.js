// Report A4 PDF exporter: NotoSansTC font loader and jsPDF DOM walker.
(function () {
    var R = window.splashboardReport = window.splashboardReport || {};
    var state = R._state = R._state || {
        pairLayoutLock: false,
        pdfMeasurer: null,
        pdfHeaderPxCache: {},
        pdfFontOk: false,
        reportFontBinary: null
    };

    var A4_WIDTH_MM = 210;
    var A4_HEIGHT_MM = 297;
    var REPORT_FONT_NAME = 'NotoSansTC';
    var REPORT_FONT_URL = '/assets/NotoSansTC-Regular.ttf';
    var PDF_FAKE_BOLD_MM = 0.15;
    var reportFontLoading = null;

    function reportFontUrl() {
        var node = document.getElementById('report-font-url');
        var url = node && (node.textContent || '').trim();
        return url || REPORT_FONT_URL;
    }

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
        if (state.reportFontBinary) {
            return Promise.resolve(state.reportFontBinary);
        }
        if (reportFontLoading) {
            return reportFontLoading;
        }
        reportFontLoading = fetch(reportFontUrl()).then(function (res) {
            if (!res.ok) {
                throw new Error('font ' + res.status);
            }
            return res.arrayBuffer();
        }).then(function (buf) {
            state.reportFontBinary = arrayBufferToBase64(buf);
            return state.reportFontBinary;
        }).catch(function (err) {
            reportFontLoading = null;
            throw err;
        });
        return reportFontLoading;
    }

    function registerReportFont(pdf) {
        state.pdfFontOk = false;
        var reportFontBinary = state.reportFontBinary;
        if (!reportFontBinary) {
            pdf.setFont('helvetica', 'normal');
            return;
        }
        pdf.addFileToVFS('NotoSansTC-Regular.ttf', reportFontBinary);
        pdf.addFont('NotoSansTC-Regular.ttf', REPORT_FONT_NAME, 'normal');
        try {
            pdf.setFont(REPORT_FONT_NAME, 'normal');
            state.pdfFontOk = pdf.getTextWidth('Score') > 0;
        } catch (err) {
            state.pdfFontOk = false;
        }
        if (!state.pdfFontOk) {
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

    function clipBoxIsUsable(clip) {
        return !!(clip && clip.w >= 1 && clip.h >= 1);
    }

    function boxOutsideClip(box, clip) {
        if (!box || !clipBoxIsUsable(clip)) {
            return false;
        }
        var eps = 0.2;
        return box.x >= clip.x + clip.w - eps
            || box.y >= clip.y + clip.h - eps
            || box.x + box.w <= clip.x + eps
            || box.y + box.h <= clip.y + eps;
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
            pdf.setFont(state.pdfFontOk ? REPORT_FONT_NAME : 'helvetica', 'normal');
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
        var credit = paper.querySelector('.report-header-credit');
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
        if (credit) {
            var creditText = (credit.textContent || '').trim();
            if (creditText) {
                var creditStyle = window.getComputedStyle(credit);
                var creditBox = boxMm(paperRect, credit, scale);
                var creditColor = parseRgb(creditStyle.color) || [148, 163, 184];
                pdf.setTextColor(creditColor[0], creditColor[1], creditColor[2]);
                pdf.setFontSize(pxToPt(parseFloat(creditStyle.fontSize) || 8, scale));
                drawPdfText(pdf, creditText, creditBox.x + creditBox.w, creditBox.y + creditBox.h / 2, {
                    baseline: 'middle',
                    align: 'right',
                    bold: false
                });
            }
        }
    }

    function drawFilledCircle(pdf, box, rgb) {
        if (!box || !rgb) {
            return;
        }
        var radius = Math.min(box.w, box.h) / 2;
        if (!(radius > 0) || !isFinite(box.x) || !isFinite(box.y) || !isFinite(radius)) {
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

    function drawTitleDot(pdf, dot, paperRect, scale, tBox, textX) {
        var dBox = boxMm(paperRect, dot, scale);
        var box = tBox ? {
            x: textX,
            y: tBox.y + Math.max(0, (tBox.h - dBox.h) / 2),
            w: dBox.w,
            h: dBox.h
        } : dBox;
        if (paperOffsheet(box)) {
            return textX;
        }
        var style = window.getComputedStyle(dot);
        var fill = parseRgb(style.backgroundColor) || [0, 180, 216];
        drawFilledCircle(pdf, box, fill);
        return box.x + box.w + 1.2;
    }

    function drawTableCell(pdf, cell, paperRect, scale, clip) {
        var box = boxMm(paperRect, cell, scale);
        if (paperOffsheet(box) || boxOutsideClip(box, clip)) {
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
        if (cell.classList && cell.classList.contains('braves-group-end')) {
            pdf.setDrawColor(203, 213, 225);
            pdf.line(box.x + box.w, box.y, box.x + box.w, box.y + box.h);
        }
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
        var bold = fontWeightNum(style) >= 600;
        if (cell.classList && cell.classList.contains('report-lineup-name')) {
            var lines = lineupNameLines(pdf, text, maxW);
            if (!lines.length) {
                return;
            }
            var lineH = box.h / lines.length;
            lines.forEach(function (line, index) {
                drawPdfText(pdf, line, x, box.y + lineH * (index + 0.5), {
                    baseline: 'middle',
                    align: pdfAlign,
                    bold: bold
                });
            });
            return;
        }
        var fitted = fitText(pdf, text, maxW);
        if (!fitted) {
            return;
        }
        drawPdfText(pdf, fitted, x, box.y + box.h / 2, {
            baseline: 'middle',
            align: pdfAlign,
            bold: bold
        });
    }

    function lineupNameLines(pdf, text, maxW) {
        if (!text) {
            return [];
        }
        if (pdf.getTextWidth(text) <= maxW) {
            return [text];
        }
        var lines = [];
        var current = '';
        text.split('-').forEach(function (chunk, index) {
            var piece = index === 0 ? chunk : '-' + chunk;
            var trial = current + piece;
            if (current && pdf.getTextWidth(trial) > maxW) {
                lines.push(current);
                current = chunk;
            } else {
                current = trial;
            }
        });
        if (current) {
            lines.push(current);
        }
        var fitted = [];
        lines.forEach(function (line) {
            if (pdf.getTextWidth(line) <= maxW) {
                fitted.push(line);
                return;
            }
            var part = '';
            for (var i = 0; i < line.length; i++) {
                var next = part + line.charAt(i);
                if (part && pdf.getTextWidth(next) > maxW) {
                    fitted.push(part);
                    part = line.charAt(i);
                } else {
                    part = next;
                }
            }
            if (part) {
                fitted.push(part);
            }
        });
        return fitted;
    }

    function toRoman(num) {
        var romans = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'];
        return (num >= 1 && num <= 10) ? romans[num - 1] : String(num);
    }

    function toAlpha(num) {
        var alpha = 'abcdefghijklmnopqrstuvwxyz';
        return (num >= 1 && num <= 26) ? alpha[num - 1] : String(num);
    }

    function stripReportInvisibleChars(text) {
        return R.stripReportInvisibleChars ? R.stripReportInvisibleChars(text) : String(text || '');
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
                        var text = stripReportInvisibleChars(node.textContent || '');
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

            if (lineInfo.listType) {
                var level = lineInfo.indentLevel || 1;
                pdf.setFontSize(ptSize);
                pdf.setTextColor(15, 23, 42);
                if (lineInfo.listType === 'ul') {
                    if (level === 1) {
                        pdf.setFillColor(15, 23, 42);
                        pdf.circle(startX - 2.5, cursorY + lineH * 0.45, 0.6, 'F');
                    } else if (level === 2) {
                        pdf.setDrawColor(15, 23, 42);
                        pdf.setLineWidth(0.15);
                        pdf.circle(startX - 2.5, cursorY + lineH * 0.45, 0.6, 'S');
                    } else {
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

                if (span.bgColor) {
                    pdf.setFillColor(span.bgColor[0], span.bgColor[1], span.bgColor[2]);
                    pdf.rect(spanX, cursorY, sWidth, lineH * 0.95, 'F');
                }

                pdf.setTextColor(span.color[0], span.color[1], span.color[2]);
                pdf.setFontSize(ptSize);
                drawPdfText(pdf, span.text, spanX, cursorY, {
                    baseline: 'top',
                    bold: !!span.bold
                });

                if (span.underline) {
                    pdf.setDrawColor(span.color[0], span.color[1], span.color[2]);
                    pdf.setLineWidth(0.2);
                    pdf.line(spanX, cursorY + lineH * 0.82, spanX + sWidth, cursorY + lineH * 0.82);
                }

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
            return Promise.resolve();
        }
        var scale = paperScale(paperRect);
        pdf.setFillColor(255, 255, 255);
        pdf.rect(0, 0, A4_WIDTH_MM, A4_HEIGHT_MM, 'F');
        try {
            drawHeader(pdf, paper, paperRect, scale);
            paper.querySelectorAll('.grid-stack-item').forEach(function (item) {
                if (item.classList.contains('grid-stack-placeholder')) {
                    return;
                }
                try {
                    var title = item.querySelector('.report-block-title');
                    if (title) {
                        var titleText = (title.textContent || '').trim();
                        var titleRow = item.querySelector('.report-block-title-row');
                        var tBox = boxMm(paperRect, titleRow || title, scale);
                        var tStyle = window.getComputedStyle(title);
                        var tColor = parseRgb(tStyle.color) || [15, 23, 42];
                        var padL = 0;
                        if (titleRow) {
                            padL = parseFloat(window.getComputedStyle(titleRow).paddingLeft) || 0;
                        }
                        var textX = tBox.x + padL * scaleXY(scale).x;
                        var dot = title.querySelector('.report-block-title-dot');
                        if (dot) {
                            textX = drawTitleDot(pdf, dot, paperRect, scale, tBox, textX);
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
                    var clip = boxMm(paperRect, item, scale);
                    var tableEl = item.querySelector('.report-js-table');
                    if (tableEl && clipBoxIsUsable(clip)) {
                        var tableBox = boxMm(paperRect, tableEl, scale);
                        var top = Math.min(clip.y, tableBox.y);
                        var bottom = Math.max(clip.y + clip.h, tableBox.y + tableBox.h);
                        clip = {
                            x: clip.x,
                            y: top,
                            w: clip.w,
                            h: bottom - top
                        };
                    }
                    if (!clipBoxIsUsable(clip)) {
                        clip = null;
                    }
                    item.querySelectorAll('th, td').forEach(function (cell) {
                        drawTableCell(pdf, cell, paperRect, scale, clip);
                    });
                    var note = item.querySelector('[data-text-block]');
                    if (note) {
                        drawNote(pdf, note, paperRect, scale);
                    }
                    var img = item.querySelector('img.report-image-block');
                    if (img) {
                        drawImageBlock(pdf, img, paperRect, scale);
                    }
                    var shotEmpty = item.querySelector('.report-shot-chart-empty');
                    if (shotEmpty) {
                        var shotText = (shotEmpty.textContent || '').trim();
                        var shotBox = boxMm(paperRect, shotEmpty, scale);
                        var shotStyle = window.getComputedStyle(shotEmpty);
                        var shotColor = parseRgb(shotStyle.color) || [100, 116, 139];
                        if (shotText && shotBox.h > 0) {
                            pdf.setTextColor(shotColor[0], shotColor[1], shotColor[2]);
                            pdf.setFontSize(pxToPt(parseFloat(shotStyle.fontSize) || 12, scale));
                            drawPdfText(pdf, shotText, shotBox.x + 1, shotBox.y + shotBox.h / 2, {
                                baseline: 'middle'
                            });
                        }
                    }
                } catch (itemErr) {
                    console.warn('PDF item skipped', itemErr);
                }
            });
            var rotationChain = Promise.resolve();
            paper.querySelectorAll('.grid-stack-item[data-block-type="rotation"] .report-rotation-plot').forEach(function (gd) {
                rotationChain = rotationChain.then(function () {
                    return drawRotationPlot(pdf, gd, paperRect, scale);
                });
            });
            paper.querySelectorAll('.grid-stack-item[data-block-type="shot_chart"] .report-shot-chart-host').forEach(function (host) {
                if (host.classList.contains('report-shot-chart-empty')) {
                    return;
                }
                rotationChain = rotationChain.then(function () {
                    return drawShotChartImage(pdf, host, paperRect, scale);
                });
            });
            return rotationChain;
        } catch (err) {
            console.warn('PDF paper skipped', err);
            return Promise.resolve();
        }
    }

    function drawRotationPlot(pdf, gd, paperRect, scale) {
        if (!gd || !window.Plotly || typeof window.Plotly.toImage !== 'function') {
            return Promise.resolve();
        }
        var frame = gd.closest('.report-rotation-scale') || gd;
        var box = boxMm(paperRect, frame, scale);
        if (box.w <= 0 || box.h <= 0 || box.y >= A4_HEIGHT_MM) {
            return Promise.resolve();
        }
        var toImage = window.Plotly.toImage(gd, {
            format: 'png',
            scale: 2
        });
        var timed = new Promise(function (resolve) {
            window.setTimeout(function () {
                resolve(null);
            }, 8000);
        });
        return Promise.race([toImage, timed]).then(function (dataUrl) {
            if (dataUrl) {
                pdf.addImage(dataUrl, 'PNG', box.x, box.y, box.w, Math.min(box.h, A4_HEIGHT_MM - box.y));
            }
        }).catch(function (err) {
            console.warn('PDF rotation skipped', err);
        });
    }

    function loadCanvasFont() {
        if (!window.FontFace || !document.fonts) {
            return Promise.resolve();
        }
        if (document.fonts.check('12px "Noto Sans TC"')) {
            return document.fonts.ready;
        }
        return fetch(reportFontUrl()).then(function (res) {
            if (!res.ok) {
                throw new Error('font ' + res.status);
            }
            return res.arrayBuffer();
        }).then(function (buf) {
            var face = new FontFace('Noto Sans TC', buf);
            return face.load().then(function (loaded) {
                document.fonts.add(loaded);
            });
        }).catch(function () {
            return null;
        });
    }

    function rasterShotChart(host) {
        var width = Math.max(1, Math.round(host.clientWidth || host.getBoundingClientRect().width));
        var height = Math.max(1, Math.round(host.clientHeight || host.getBoundingClientRect().height));
        var canvas = document.createElement('canvas');
        var pixel = 2;
        canvas.width = width * pixel;
        canvas.height = height * pixel;
        var ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.setTransform(pixel, 0, 0, pixel, 0, 0);
        var hostRect = host.getBoundingClientRect();
        Array.prototype.forEach.call(host.querySelectorAll('.report-shot-chart-name'), function (name) {
            var rect = name.getBoundingClientRect();
            var style = window.getComputedStyle(name);
            var size = parseFloat(style.fontSize) || 12;
            ctx.fillStyle = style.color || '#0f172a';
            ctx.font = '700 ' + size + 'px "Noto Sans TC", sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(
                (name.textContent || '').trim(),
                (rect.left - hostRect.left) + rect.width / 2,
                (rect.top - hostRect.top) + rect.height / 2,
                Math.max(1, rect.width - 4)
            );
        });
        var imgs = host.querySelectorAll('img.report-shot-chart-court');
        return new Promise(function (resolve) {
            var pending = imgs.length;
            function completeRaster() {
                try {
                    resolve(canvas.toDataURL('image/png'));
                } catch (err) {
                    console.warn('shot chart image skipped', err);
                    resolve(null);
                }
            }
            if (!pending) {
                completeRaster();
                return;
            }
            Array.prototype.forEach.call(imgs, function (img) {
                var draw = function () {
                    var rect = img.getBoundingClientRect();
                    try {
                        ctx.drawImage(
                            img,
                            rect.left - hostRect.left,
                            rect.top - hostRect.top,
                            rect.width,
                            rect.height
                        );
                    } catch (err) {
                        console.warn('shot chart image skipped', err);
                    }
                    pending -= 1;
                    if (pending === 0) {
                        completeRaster();
                    }
                };
                if (img.complete) {
                    if (img.naturalWidth) {
                        draw();
                    } else {
                        pending -= 1;
                        if (pending === 0) {
                            completeRaster();
                        }
                    }
                } else {
                    img.addEventListener('load', draw, { once: true });
                    img.addEventListener('error', function () {
                        pending -= 1;
                        if (pending === 0) {
                            completeRaster();
                        }
                    }, { once: true });
                }
            });
        });
    }

    function drawShotChartImage(pdf, host, paperRect, scale) {
        if (!host) {
            return Promise.resolve();
        }
        var box = boxMm(paperRect, host, scale);
        if (box.w <= 0 || box.h <= 0 || box.y >= A4_HEIGHT_MM) {
            return Promise.resolve();
        }
        var timed = new Promise(function (resolve) {
            window.setTimeout(function () {
                resolve(null);
            }, 8000);
        });
        var raster = loadCanvasFont().then(function () {
            return rasterShotChart(host);
        });
        return Promise.race([raster, timed]).then(function (dataUrl) {
            if (dataUrl) {
                pdf.addImage(dataUrl, 'PNG', box.x, box.y, box.w, Math.min(box.h, A4_HEIGHT_MM - box.y));
            }
        }).catch(function (err) {
            console.warn('shot chart image skipped', err);
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

    function waitPdfFrame() {
        return new Promise(function (resolve) {
            var done = false;
            function completeFrame() {
                if (done) {
                    return;
                }
                done = true;
                resolve();
            }
            window.requestAnimationFrame(function () {
                window.requestAnimationFrame(completeFrame);
            });
            window.setTimeout(completeFrame, 120);
        });
    }

    function capturePdfScroll() {
        var workspace = document.getElementById('report-workspace');
        var papersEl = document.querySelector('.report-papers');
        var main = document.querySelector('.report-main');
        return {
            x: window.scrollX,
            y: window.scrollY,
            workspace: workspace ? workspace.scrollTop : 0,
            papers: papersEl ? papersEl.scrollTop : 0,
            main: main ? main.scrollTop : 0
        };
    }

    function restorePdfScroll(saved) {
        if (!saved) {
            return;
        }
        window.scrollTo(saved.x, saved.y);
        var workspace = document.getElementById('report-workspace');
        var papersEl = document.querySelector('.report-papers');
        var main = document.querySelector('.report-main');
        if (workspace) {
            workspace.scrollTop = saved.workspace;
        }
        if (papersEl) {
            papersEl.scrollTop = saved.papers;
        }
        if (main) {
            main.scrollTop = saved.main;
        }
    }

    function revealPaperForPdf(paper) {
        if (!paper) {
            return Promise.resolve();
        }
        paper.scrollIntoView({ block: 'start', inline: 'nearest' });
        void paper.offsetHeight;
        return waitPdfFrame();
    }

    function refitPaperForPdf(paper) {
        var gridEl = paper && paper.querySelector('.report-grid');
        var grid = gridEl && gridEl.gridstack;
        if (grid) {
            var originY = R.snapshotNodeYs ? R.snapshotNodeYs(grid) : {};
            if (grid.el) {
                grid.el._splashboardOriginY = originY;
            }
            if (R.fitTableBlocksOnGrid) R.fitTableBlocksOnGrid(grid);
            if (R.fitRotationBlocksOnGrid) R.fitRotationBlocksOnGrid(grid);
            if (R.fitShotChartBlocksOnGrid) R.fitShotChartBlocksOnGrid(grid);
            if (R.resolveOverlaps) R.resolveOverlaps(grid, originY);
        }
        if (paper) {
            void paper.offsetHeight;
        }
        return new Promise(function (resolve) {
            window.setTimeout(function () {
                waitPdfFrame().then(resolve);
            }, 50);
        });
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
        if (window.splashboardTableStick) {
            window.splashboardTableStick.pause();
        }
        var savedScroll = capturePdfScroll();
        setPdfBusy(true);
        return R.ensureReportLibs().then(function () {
            if (!window.jspdf || !window.jspdf.jsPDF) {
                throw new Error('jspdf missing');
            }
            return loadReportFont();
        }).then(function () {
            var JsPDF = window.jspdf.jsPDF;
            var pdf = new JsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
            registerReportFont(pdf);
            state.pdfMeasurer = pdf;
            state.pdfHeaderPxCache = {};
            if (R.PAIR_WIDTHS && R.syncPairColumnWidths) {
                R.PAIR_WIDTHS.forEach(R.syncPairColumnWidths);
            }
            var chain = Promise.resolve();
            Array.prototype.forEach.call(papers, function (paper, index) {
                chain = chain.then(function () {
                    var hydrate = R.hydratePage ? R.hydratePage(index) : Promise.resolve();
                    return Promise.resolve(hydrate).then(function () {
                        return revealPaperForPdf(paper);
                    }).then(function () {
                        return refitPaperForPdf(paper);
                    }).then(function () {
                        if (index > 0) {
                            pdf.addPage('a4', 'portrait');
                        }
                        return drawPaper(pdf, paper);
                    }).catch(function (err) {
                        console.warn('PDF page failed', err);
                    });
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
            restorePdfScroll(savedScroll);
            setPdfBusy(false);
            if (window.splashboardTableStick) {
                window.splashboardTableStick.resume();
            }
        });
    }

    Object.assign(R, {
        reportFontUrl: reportFontUrl,
        loadReportFont: loadReportFont,
        registerReportFont: registerReportFont,
        paperScale: paperScale,
        boxOutsideClip: boxOutsideClip,
        clipBoxIsUsable: clipBoxIsUsable,
        exportPapersToPdf: exportPapersToPdf,
        ensurePdfFont: function () {
            return loadReportFont();
        },
        exportPdf: function () {
            return exportPapersToPdf();
        }
    });
})();
