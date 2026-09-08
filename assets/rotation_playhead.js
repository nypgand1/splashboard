(function () {
    function plotNode() {
        return document.querySelector('#rotation-graph .js-plotly-plot')
            || document.querySelector('#rotation-graph .plotly-graph-div');
    }

    function dragBoxAt(gd, ev) {
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

    function eventToTime(gd, ev) {
        var layout = gd && gd._fullLayout;
        if (!layout || !layout.xaxis || !layout.xaxis.range) {
            return null;
        }
        var box = dragBoxAt(gd, ev);
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

    function publish(t) {
        window._rotationClickT = t;
        if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
            window.dash_clientside.set_props('rotation-click-t', {data: t});
        }
        var btn = document.getElementById('rotation-click-fire');
        if (btn) {
            btn.click();
        }
    }

    var down = null;

    function eventInsidePlot(ev, gd) {
        var rect = gd.getBoundingClientRect();
        return ev.clientX >= rect.left && ev.clientX <= rect.right
            && ev.clientY >= rect.top && ev.clientY <= rect.bottom;
    }

    function onDown(ev) {
        if (ev.button != null && ev.button !== 0) {
            return;
        }
        var gd = plotNode();
        if (!gd || !eventInsidePlot(ev, gd)) {
            down = null;
            return;
        }
        down = {x: ev.clientX, y: ev.clientY};
    }

    function onUp(ev) {
        if (!down) {
            return;
        }
        var gd = plotNode();
        var moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y);
        down = null;
        if (!gd || moved > 8) {
            return;
        }
        var t = eventToTime(gd, ev);
        window._rotationClickDebug = {
            t: t,
            px: ev.clientX,
            py: ev.clientY,
            hasP2d: !!(gd._fullLayout && gd._fullLayout.xaxis && gd._fullLayout.xaxis.p2d)
        };
        if (t == null) {
            return;
        }
        publish(t);
    }

    function bind() {
        if (window._rotationPlayheadDocBound) {
            return;
        }
        window._rotationPlayheadDocBound = true;
        document.addEventListener('pointerdown', onDown, true);
        document.addEventListener('pointerup', onUp, true);
        document.addEventListener('mousedown', onDown, true);
        document.addEventListener('mouseup', onUp, true);
    }

    function scan() {
        bind();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scan);
    } else {
        scan();
    }
    document.addEventListener('plotly_afterplot', scan, true);
    var obs = new MutationObserver(scan);
    if (document.body) {
        obs.observe(document.body, {childList: true, subtree: true});
    } else {
        document.addEventListener('DOMContentLoaded', function () {
            obs.observe(document.body, {childList: true, subtree: true});
        });
    }
})();
