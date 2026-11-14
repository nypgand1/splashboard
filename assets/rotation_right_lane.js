(function () {
    var NARROW = '(max-width: 767px)';
    var WIDE_L = 112;
    var WIDE_R = 112;
    var NARROW_L = 56;
    var NARROW_R = 24;
    var KILL_ROW = '3+ STOPS';
    var NARROW_KILL = 'STOPS';

    function findGameRotationNode() {
        return document.querySelector('#rotation-graph .js-plotly-plot')
            || document.querySelector('#rotation-graph .plotly-graph-div');
    }

    function isNarrowViewport() {
        return window.matchMedia(NARROW).matches;
    }

    function isDomainKillAnnotation(ann) {
        return !!(ann
            && (ann.text === KILL_ROW || ann.text === NARROW_KILL)
            && ann.y === KILL_ROW
            && typeof ann.xref === 'string'
            && ann.xref.indexOf('domain') !== -1);
    }

    function isRightKillAnnotation(ann) {
        return isDomainKillAnnotation(ann) && +ann.x === 1;
    }

    function isLeftKillAnnotation(ann) {
        return isDomainKillAnnotation(ann) && +ann.x === 0;
    }

    function isAxisHidden(axis) {
        return !!(axis && axis.visible === false);
    }

    function readAxisLabels(axis) {
        if (!axis) {
            return [];
        }
        if (axis.categoryarray && axis.categoryarray.length) {
            return axis.categoryarray;
        }
        return axis.tickvals || [];
    }

    function formatJerseyTick(label) {
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

    function formatWideTick(label) {
        var text = label == null ? '' : String(label);
        return text === KILL_ROW ? '' : text;
    }

    function computeAxisTickText(axis, narrow) {
        var labels = readAxisLabels(axis);
        var i;
        var out = [];
        for (i = 0; i < labels.length; i++) {
            out.push(narrow ? formatJerseyTick(labels[i]) : formatWideTick(labels[i]));
        }
        return out;
    }

    function hasMatchingTicks(axis, narrow) {
        if (!axis) {
            return true;
        }
        var want = computeAxisTickText(axis, narrow);
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

    function isGameLaneSynced(gd, narrow) {
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
        if (narrow ? !isAxisHidden(layout.yaxis4) : isAxisHidden(layout.yaxis4)) {
            return false;
        }
        if (layout.yaxis5 && (narrow ? !isAxisHidden(layout.yaxis5) : isAxisHidden(layout.yaxis5))) {
            return false;
        }
        if (layout.yaxis6 && (narrow ? !isAxisHidden(layout.yaxis6) : isAxisHidden(layout.yaxis6))) {
            return false;
        }
        if (!hasMatchingTicks(layout.yaxis, narrow) || !hasMatchingTicks(layout.yaxis3, narrow)) {
            return false;
        }
        var anns = layout.annotations || [];
        var i;
        var wantLeft = narrow ? NARROW_KILL : KILL_ROW;
        for (i = 0; i < anns.length; i++) {
            if (isRightKillAnnotation(anns[i])) {
                if (narrow ? anns[i].visible !== false : anns[i].visible === false) {
                    return false;
                }
                if (anns[i].text !== KILL_ROW) {
                    return false;
                }
            } else if (isLeftKillAnnotation(anns[i]) && anns[i].text !== wantLeft) {
                return false;
            }
        }
        return true;
    }

    function buildGameLaneUpdate(gd, narrow) {
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
            update['yaxis.tickvals'] = readAxisLabels(gd.layout.yaxis);
            update['yaxis.ticktext'] = computeAxisTickText(gd.layout.yaxis, narrow);
        }
        if (gd.layout && gd.layout.yaxis3) {
            update['yaxis3.tickvals'] = readAxisLabels(gd.layout.yaxis3);
            update['yaxis3.ticktext'] = computeAxisTickText(gd.layout.yaxis3, narrow);
        }
        var anns = (gd.layout && gd.layout.annotations) || [];
        var i;
        for (i = 0; i < anns.length; i++) {
            if (isRightKillAnnotation(anns[i])) {
                update['annotations[' + i + '].visible'] = !narrow;
                update['annotations[' + i + '].text'] = KILL_ROW;
            } else if (isLeftKillAnnotation(anns[i])) {
                update['annotations[' + i + '].text'] = narrow ? NARROW_KILL : KILL_ROW;
            }
        }
        return update;
    }

    function createLaneController(getNode, matchesFn, updateFn, pendingKey, againKey) {
        function completeLaneUpdate(retry) {
            window[pendingKey] = false;
            if (window[againKey]) {
                window[againKey] = false;
                syncLaneLayout(false);
                return;
            }
            var again = getNode();
            if (again && !matchesFn(again, isNarrowViewport()) && !retry) {
                syncLaneLayout(true);
            }
        }

        function syncLaneLayout(retry) {
            var gd = getNode();
            if (!gd || !gd.layout || !window.Plotly || typeof window.Plotly.relayout !== 'function') {
                return;
            }
            var narrow = isNarrowViewport();
            if (matchesFn(gd, narrow)) {
                return;
            }
            if (window[pendingKey]) {
                window[againKey] = true;
                return;
            }
            window[pendingKey] = true;
            var result;
            try {
                result = window.Plotly.relayout(gd, updateFn(gd, narrow));
            } catch (err) {
                completeLaneUpdate(retry);
                return;
            }
            if (result && typeof result.then === 'function') {
                result.then(function () { completeLaneUpdate(retry); }, function () { completeLaneUpdate(retry); });
            } else {
                completeLaneUpdate(retry);
            }
        }

        return syncLaneLayout;
    }

    var syncGameRotationLane = createLaneController(
        findGameRotationNode,
        isGameLaneSynced,
        buildGameLaneUpdate,
        '_rotationRightLanePending',
        '_rotationRightLaneAgain'
    );

    function findTeamRotationNode() {
        return document.querySelector('#ts-rotation-graph .js-plotly-plot')
            || document.querySelector('#ts-rotation-graph .plotly-graph-div');
    }

    function listYAxisKeys(layout) {
        var keys = [];
        var key;
        for (key in layout) {
            if (Object.prototype.hasOwnProperty.call(layout, key) && /^yaxis\d*$/.test(key)) {
                keys.push(key);
            }
        }
        return keys;
    }

    function isRightSideAxis(axis) {
        return !!(axis && axis.side === 'right');
    }

    function isLeftPlayerAxis(axis) {
        return !!(axis && axis.categoryarray && axis.categoryarray.length && !isRightSideAxis(axis));
    }

    function isTeamLaneSynced(gd, narrow) {
        var layout = gd.layout;
        if (!layout) {
            return true;
        }
        var keys = listYAxisKeys(layout);
        var rights = [];
        var i;
        for (i = 0; i < keys.length; i++) {
            if (isRightSideAxis(layout[keys[i]])) {
                rights.push(keys[i]);
            }
        }
        if (!rights.length) {
            return true;
        }
        var margin = layout.margin || {};
        if (margin.r !== (narrow ? NARROW_R : WIDE_R)) {
            return false;
        }
        if (margin.l !== (narrow ? NARROW_L : WIDE_L)) {
            return false;
        }
        for (i = 0; i < rights.length; i++) {
            if (narrow ? !isAxisHidden(layout[rights[i]]) : isAxisHidden(layout[rights[i]])) {
                return false;
            }
        }
        for (i = 0; i < keys.length; i++) {
            if (isLeftPlayerAxis(layout[keys[i]]) && !hasMatchingTicks(layout[keys[i]], narrow)) {
                return false;
            }
        }
        return true;
    }

    function buildTeamLaneUpdate(gd, narrow) {
        var update = {
            'margin.r': narrow ? NARROW_R : WIDE_R,
            'margin.l': narrow ? NARROW_L : WIDE_L
        };
        var keys = listYAxisKeys(gd.layout || {});
        var i;
        var axis;
        for (i = 0; i < keys.length; i++) {
            axis = gd.layout[keys[i]];
            if (isRightSideAxis(axis)) {
                update[keys[i] + '.visible'] = !narrow;
            } else if (isLeftPlayerAxis(axis)) {
                update[keys[i] + '.automargin'] = false;
                update[keys[i] + '.tickvals'] = readAxisLabels(axis);
                update[keys[i] + '.ticktext'] = computeAxisTickText(axis, narrow);
            }
        }
        return update;
    }

    var syncTeamRotationLane = createLaneController(
        findTeamRotationNode,
        isTeamLaneSynced,
        buildTeamLaneUpdate,
        '_teamRotationLanePending',
        '_teamRotationLaneAgain'
    );

    function bindRotationRightLane() {
        if (window._rotationRightLaneBound) {
            return;
        }
        window._rotationRightLaneBound = true;
        var mq = window.matchMedia(NARROW);
        if (typeof mq.addEventListener === 'function') {
            mq.addEventListener('change', function () {
                syncGameRotationLane(false);
                syncTeamRotationLane(false);
            });
        } else if (typeof mq.addListener === 'function') {
            mq.addListener(function () {
                syncGameRotationLane(false);
                syncTeamRotationLane(false);
            });
        }
        document.addEventListener('plotly_afterplot', function () {
            syncGameRotationLane(false);
            syncTeamRotationLane(false);
        }, true);
        window.setInterval(function () {
            syncGameRotationLane(false);
            syncTeamRotationLane(false);
        }, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindRotationRightLane);
    } else {
        bindRotationRightLane();
    }
})();
