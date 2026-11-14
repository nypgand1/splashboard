(function () {
    function findRotationPlotNode() {
        return document.querySelector('#rotation-graph .js-plotly-plot')
            || document.querySelector('#rotation-graph .plotly-graph-div');
    }

    function findSubplotDragRect(gd, ev) {
        var drags = gd.querySelectorAll('.nsewdrag');
        var i, rect, fallback;
        for (i = 0; i < drags.length; i++) {
            rect = drags[i].getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) {
                continue;
            }
            if (!fallback) {
                fallback = rect;
            }
            if (ev.clientY >= rect.top && ev.clientY <= rect.bottom) {
                return rect;
            }
        }
        return fallback || null;
    }

    function mapEventToPlayheadTime(gd, ev) {
        var layout = gd && gd._fullLayout;
        if (!layout || !layout.xaxis || !layout.xaxis.range) {
            return null;
        }
        var box = findSubplotDragRect(gd, ev);
        if (!box || box.width <= 0) {
            return null;
        }
        var frac = (ev.clientX - box.left) / box.width;
        frac = Math.max(0, Math.min(1, frac));
        var xa = layout.xaxis;
        var t0 = xa.range[0];
        var t1 = xa.range[1];
        var t = t0 + frac * (t1 - t0);
        var minT = xa.minallowed != null ? xa.minallowed : Math.min(t0, t1);
        var maxT = xa.maxallowed != null ? xa.maxallowed : Math.max(t0, t1);
        if (typeof minT === 'number') {
            t = Math.max(t, minT);
        }
        if (typeof maxT === 'number') {
            t = Math.min(t, maxT);
        }
        return t;
    }

    function publishPlayheadTime(t) {
        window._rotationClickT = t;
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('rotation-click-t', {data: t});
        }
        var btn = document.getElementById('rotation-click-fire');
        if (btn) {
            btn.click();
        }
    }

    var pointerStart = null;

    function isEventInsidePlot(ev, gd) {
        var rect = gd.getBoundingClientRect();
        return ev.clientX >= rect.left && ev.clientX <= rect.right
            && ev.clientY >= rect.top && ev.clientY <= rect.bottom;
    }

    function handlePlayheadPointerDown(ev) {
        if (ev.button != null && ev.button !== 0) {
            return;
        }
        var gd = findRotationPlotNode();
        if (!gd || !isEventInsidePlot(ev, gd)) {
            pointerStart = null;
            return;
        }
        pointerStart = {x: ev.clientX, y: ev.clientY};
    }

    function handlePlayheadPointerUp(ev) {
        if (!pointerStart) {
            return;
        }
        var gd = findRotationPlotNode();
        var moved = Math.hypot(ev.clientX - pointerStart.x, ev.clientY - pointerStart.y);
        pointerStart = null;
        if (!gd || moved > 8) {
            return;
        }
        var t = mapEventToPlayheadTime(gd, ev);
        window._rotationClickDebug = {
            t: t,
            px: ev.clientX,
            py: ev.clientY,
            hasP2d: !!(gd._fullLayout && gd._fullLayout.xaxis && gd._fullLayout.xaxis.p2d)
        };
        if (t == null) {
            return;
        }
        publishPlayheadTime(t);
    }

    function bindRotationPlayhead() {
        if (window._rotationPlayheadDocBound) {
            return;
        }
        window._rotationPlayheadDocBound = true;
        document.addEventListener('pointerdown', handlePlayheadPointerDown, true);
        document.addEventListener('pointerup', handlePlayheadPointerUp, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindRotationPlayhead);
    } else {
        bindRotationPlayhead();
    }
})();
