/* Select menu side and height. Keep the numbers aligned with select_menu_plan. */
(function () {
    var GAP = 12;
    var ROW_FALLBACK = 32;
    var MENU_GAP = 4;
    var FIELDS = [
        '#shot-chart-player-away',
        '#shot-chart-player-home',
        '#home-team',
        '#home-season',
        '#ts-team',
        '#ts-opponent',
        '#ts-stadium',
        '#ts-season'
    ].join(', ');

    function parsePxValue(value) {
        return Math.ceil(value - 1e-9);
    }

    function buildUniformRowHeights(rowHeight, rowCount) {
        var heights = [];
        var count = Math.max(0, rowCount);
        for (var i = 0; i < count; i++) {
            heights.push(+rowHeight);
        }
        return heights;
    }

    function computeSelectMenuPlan(rect, viewportHeight, heights, padTop, padBottom) {
        var above = Math.max(0, rect.top - GAP);
        var below = Math.max(0, viewportHeight - rect.bottom - GAP);
        var pad = parsePxValue(padTop) + parsePxValue(padBottom);
        var rows = heights.length;
        var sum = 0;
        for (var i = 0; i < rows; i++) {
            sum += heights[i];
        }
        var row = rows ? heights[0] : ROW_FALLBACK;
        var innerAll = rows ? parsePxValue(sum) : 0;
        var needed = innerAll + (rows ? pad : 0);

        function scrollInner(space) {
            var room = space - pad;
            var used = 0;
            var count = 0;
            var unit = row > 0 ? row : ROW_FALLBACK;
            for (var i = 0; i < rows; i++) {
                var next = used + heights[i];
                if (count >= 4 && next > room + 1e-6) {
                    break;
                }
                used = next;
                count += 1;
            }
            if (count < 4) {
                used = 4 * unit;
            }
            return parsePxValue(used);
        }

        var side;
        var inner;
        if (needed > 0 && below >= needed) {
            side = 'bottom';
            inner = innerAll;
        } else if (needed > 0 && above >= needed) {
            side = 'top';
            inner = innerAll;
        } else if (below >= above) {
            side = 'bottom';
            inner = scrollInner(below);
        } else {
            side = 'top';
            inner = scrollInner(above);
        }
        return {side: side, height: inner + pad, inner: inner};
    }

    function planSelectMenu(rect, viewportHeight, rowHeight, rowCount, padTop, padBottom) {
        var heights = Array.isArray(rowHeight) ? rowHeight : buildUniformRowHeights(rowHeight, rowCount);
        return computeSelectMenuPlan(rect, viewportHeight, heights, +padTop || 0, +padBottom || 0);
    }

    window.splashboardSelectMenuPlan = planSelectMenu;

    function applyMaxHeightStyle(node, pixels) {
        if (!node || !node.style || !node.style.maxHeight) {
            return false;
        }
        node.style.maxHeight = pixels;
        return true;
    }

    function positionSelectDropdown(dropdown, input, side, height) {
        if (!dropdown) {
            return;
        }
        var box = input.getBoundingClientRect();
        dropdown.style.maxHeight = height + 'px';
        dropdown.style.position = 'fixed';
        dropdown.style.left = Math.round(box.left) + 'px';
        dropdown.style.width = Math.round(box.width) + 'px';
        dropdown.style.transform = 'none';
        var used = dropdown.getBoundingClientRect().height || height;
        var top = side === 'top' ? box.top - MENU_GAP - used : box.bottom + MENU_GAP;
        dropdown.style.top = Math.round(top) + 'px';
    }

    function syncSelectDropdown(input) {
        var listId = input.getAttribute('aria-controls');
        if (!listId) {
            return;
        }
        var list = document.getElementById(listId);
        if (!list) {
            return;
        }
        var options = list.querySelectorAll('[role="option"]');
        if (!options.length) {
            return;
        }
        var heights = [];
        for (var i = 0; i < options.length; i++) {
            var measured = options[i].getBoundingClientRect().height;
            heights.push(measured > 0 ? measured : ROW_FALLBACK);
        }
        var dropdown = list.closest('.mantine-Select-dropdown, .mantine-Popover-dropdown');
        var padTop = 0;
        var padBottom = 0;
        if (dropdown) {
            var style = window.getComputedStyle(dropdown);
            padTop = parseFloat(style.paddingTop) || 0;
            padBottom = parseFloat(style.paddingBottom) || 0;
        }
        var plan = planSelectMenu(input.getBoundingClientRect(), window.innerHeight, heights, heights.length, padTop, padBottom);
        var innerPx = plan.inner + 'px';
        var wrote = applyMaxHeightStyle(list, innerPx);
        var nodes = list.querySelectorAll('*');
        for (var n = 0; n < nodes.length; n++) {
            if (applyMaxHeightStyle(nodes[n], innerPx)) {
                wrote = true;
            }
        }
        if (!wrote) {
            list.style.maxHeight = innerPx;
        }
        positionSelectDropdown(dropdown, input, plan.side, plan.height);
    }

    function findSelectInputFromEvent(event) {
        var target = event.target;
        if (!target || !target.closest) {
            return null;
        }
        var field = target.closest('.mantine-Select-root, .mantine-InputWrapper-root');
        if (!field) {
            return null;
        }
        return field.querySelector(FIELDS);
    }

    function scheduleSelectDropdownSync(event) {
        var input = findSelectInputFromEvent(event);
        if (!input) {
            return;
        }
        window.setTimeout(function () { syncSelectDropdown(input); }, 0);
        window.setTimeout(function () { syncSelectDropdown(input); }, 50);
        window.setTimeout(function () { syncSelectDropdown(input); }, 120);
        window.requestAnimationFrame(function () { syncSelectDropdown(input); });
    }

    document.addEventListener('pointerdown', scheduleSelectDropdownSync, true);
    document.addEventListener('keydown', scheduleSelectDropdownSync, true);
})();
