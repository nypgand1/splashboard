(function () {
    var NARROW = '(max-width: 767px)';
    var WIDE_L = 112;
    var WIDE_R = 112;
    var NARROW_L = 56;
    var NARROW_R = 24;
    var KILL_ROW = '3+ STOPS';
    var NARROW_KILL = 'STOPS';

    function plotNode() {
        return document.querySelector('#rotation-graph .js-plotly-plot')
            || document.querySelector('#rotation-graph .plotly-graph-div');
    }

    function wantsNarrow() {
        return window.matchMedia(NARROW).matches;
    }

    function isDomainKill(ann) {
        return !!(ann
            && (ann.text === KILL_ROW || ann.text === NARROW_KILL)
            && ann.y === KILL_ROW
            && typeof ann.xref === 'string'
            && ann.xref.indexOf('domain') !== -1);
    }

    function isRightKill(ann) {
        return isDomainKill(ann) && +ann.x === 1;
    }

    function isLeftKill(ann) {
        return isDomainKill(ann) && +ann.x === 0;
    }

    function hidden(axis) {
        return !!(axis && axis.visible === false);
    }

    function axisLabels(axis) {
        if (!axis) {
            return [];
        }
        if (axis.categoryarray && axis.categoryarray.length) {
            return axis.categoryarray;
        }
        return axis.tickvals || [];
    }

    function jerseyTick(label) {
        var text = label == null ? '' : String(label);
        if (text === KILL_ROW) {
            return '';
        }
        var match = /^(● |  )?(#\S+)(?:\s.*)?$/.exec(text);
        if (!match) {
            return text;
        }
        return (match[1] || '') + match[2];
    }

    function wideTick(label) {
        var text = label == null ? '' : String(label);
        return text === KILL_ROW ? '' : text;
    }

    function wantedTicks(axis, narrow) {
        var labels = axisLabels(axis);
        var i;
        var out = [];
        for (i = 0; i < labels.length; i++) {
            out.push(narrow ? jerseyTick(labels[i]) : wideTick(labels[i]));
        }
        return out;
    }

    function sameTicks(axis, narrow) {
        if (!axis) {
            return true;
        }
        var want = wantedTicks(axis, narrow);
        var have = axis.ticktext || [];
        if (have.length !== want.length) {
            return want.length === 0;
        }
        var i;
        for (i = 0; i < want.length; i++) {
            if (String(have[i] == null ? '' : have[i]) !== want[i]) {
                return false;
            }
        }
        return true;
    }

    function laneMatches(gd, narrow) {
        var layout = gd.layout;
        if (!layout || !layout.yaxis4) {
            return true;
        }
        var margin = layout.margin || {};
        if (margin.r !== (narrow ? NARROW_R : WIDE_R)) {
            return false;
        }
        if (margin.l !== (narrow ? NARROW_L : WIDE_L)) {
            return false;
        }
        if (narrow ? !hidden(layout.yaxis4) : hidden(layout.yaxis4)) {
            return false;
        }
        if (layout.yaxis5 && (narrow ? !hidden(layout.yaxis5) : hidden(layout.yaxis5))) {
            return false;
        }
        if (layout.yaxis6 && (narrow ? !hidden(layout.yaxis6) : hidden(layout.yaxis6))) {
            return false;
        }
        if (!sameTicks(layout.yaxis, narrow) || !sameTicks(layout.yaxis3, narrow)) {
            return false;
        }
        var anns = layout.annotations || [];
        var i;
        var wantLeft = narrow ? NARROW_KILL : KILL_ROW;
        for (i = 0; i < anns.length; i++) {
            if (isRightKill(anns[i])) {
                if (narrow ? anns[i].visible !== false : anns[i].visible === false) {
                    return false;
                }
                if (anns[i].text !== KILL_ROW) {
                    return false;
                }
            } else if (isLeftKill(anns[i]) && anns[i].text !== wantLeft) {
                return false;
            }
        }
        return true;
    }

    function laneUpdate(gd, narrow) {
        var update = {
            'margin.r': narrow ? NARROW_R : WIDE_R,
            'margin.l': narrow ? NARROW_L : WIDE_L,
            'yaxis4.visible': !narrow,
            'yaxis5.visible': !narrow,
            'yaxis6.visible': !narrow,
            'yaxis.automargin': false,
            'yaxis3.automargin': false
        };
        if (gd.layout && gd.layout.yaxis) {
            update['yaxis.tickvals'] = axisLabels(gd.layout.yaxis);
            update['yaxis.ticktext'] = wantedTicks(gd.layout.yaxis, narrow);
        }
        if (gd.layout && gd.layout.yaxis3) {
            update['yaxis3.tickvals'] = axisLabels(gd.layout.yaxis3);
            update['yaxis3.ticktext'] = wantedTicks(gd.layout.yaxis3, narrow);
        }
        var anns = (gd.layout && gd.layout.annotations) || [];
        var i;
        for (i = 0; i < anns.length; i++) {
            if (isRightKill(anns[i])) {
                update['annotations[' + i + '].visible'] = !narrow;
                update['annotations[' + i + '].text'] = KILL_ROW;
            } else if (isLeftKill(anns[i])) {
                update['annotations[' + i + '].text'] = narrow ? NARROW_KILL : KILL_ROW;
            }
        }
        return update;
    }

    function finish(retry) {
        window._rotationRightLanePending = false;
        if (window._rotationRightLaneAgain) {
            window._rotationRightLaneAgain = false;
            apply(false);
            return;
        }
        var again = plotNode();
        if (again && !laneMatches(again, wantsNarrow()) && !retry) {
            apply(true);
        }
    }

    function apply(retry) {
        var gd = plotNode();
        if (!gd || !gd.layout || !window.Plotly || typeof window.Plotly.relayout !== 'function') {
            return;
        }
        var narrow = wantsNarrow();
        if (laneMatches(gd, narrow)) {
            return;
        }
        if (window._rotationRightLanePending) {
            window._rotationRightLaneAgain = true;
            return;
        }
        window._rotationRightLanePending = true;
        var result;
        try {
            result = window.Plotly.relayout(gd, laneUpdate(gd, narrow));
        } catch (err) {
            finish(retry);
            return;
        }
        if (result && typeof result.then === 'function') {
            result.then(function () { finish(retry); }, function () { finish(retry); });
        } else {
            finish(retry);
        }
    }

    function bind() {
        if (window._rotationRightLaneBound) {
            return;
        }
        window._rotationRightLaneBound = true;
        var mq = window.matchMedia(NARROW);
        if (typeof mq.addEventListener === 'function') {
            mq.addEventListener('change', function () { apply(false); });
        } else if (typeof mq.addListener === 'function') {
            mq.addListener(function () { apply(false); });
        }
        document.addEventListener('plotly_afterplot', function () { apply(false); }, true);
        window.setInterval(function () { apply(false); }, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind);
    } else {
        bind();
    }
})();
