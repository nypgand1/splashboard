(function () {
    var NARROW = '(max-width: 767px)';
    var WIDE_R = 112;
    var NARROW_R = 24;

    function plotNode() {
        return document.querySelector('#rotation-graph .js-plotly-plot')
            || document.querySelector('#rotation-graph .plotly-graph-div');
    }

    function wantsNarrow() {
        return window.matchMedia(NARROW).matches;
    }

    function isRightKill(ann) {
        return !!(ann
            && ann.text === '3+ STOPS'
            && +ann.x === 1
            && typeof ann.xref === 'string'
            && ann.xref.indexOf('domain') !== -1);
    }

    function hidden(axis) {
        return !!(axis && axis.visible === false);
    }

    function laneMatches(gd, narrow) {
        var layout = gd.layout;
        if (!layout || !layout.yaxis4) {
            return true;
        }
        var margin = layout.margin || {};
        var wantR = narrow ? NARROW_R : WIDE_R;
        if (margin.r !== wantR) {
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
        var anns = layout.annotations || [];
        var i;
        for (i = 0; i < anns.length; i++) {
            if (!isRightKill(anns[i])) {
                continue;
            }
            if (narrow ? anns[i].visible !== false : anns[i].visible === false) {
                return false;
            }
        }
        return true;
    }

    function laneUpdate(gd, narrow) {
        var update = {
            'margin.r': narrow ? NARROW_R : WIDE_R,
            'yaxis4.visible': !narrow,
            'yaxis5.visible': !narrow,
            'yaxis6.visible': !narrow
        };
        var anns = (gd.layout && gd.layout.annotations) || [];
        var i;
        for (i = 0; i < anns.length; i++) {
            if (isRightKill(anns[i])) {
                update['annotations[' + i + '].visible'] = !narrow;
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
