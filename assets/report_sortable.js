/* Client-side SortableJS initialization + A4 page-break ruler injection */
(function() {
    /* ---- SortableJS drag-and-drop ---- */
    function initSortable() {
        var el = document.getElementById('report-canvas-list');
        if (el && window.Sortable && !el.dataset.sortableInitialized) {
            el.dataset.sortableInitialized = "true";
            new Sortable(el, {
                handle: '.drag-handle',
                animation: 150,
                ghostClass: 'sortable-ghost',
                onEnd: function(evt) {
                    var event = new CustomEvent('report-blocks-reordered', {
                        detail: { oldIndex: evt.oldIndex, newIndex: evt.newIndex }
                    });
                    document.dispatchEvent(event);
                }
            });
        }
    }

    /* ---- A4 page-break ruler injection ----
       A4 Landscape: 297mm × 210mm
       With 10mm padding top+bottom → content area height = 190mm
       Convert to px (96dpi): 190mm ≈ 718px
       We insert a dashed red ruler line every 718px of cumulative block height.
    */
    var A4_CONTENT_HEIGHT_PX = 718; // ~190mm at 96dpi

    function insertPageBreakRulers() {
        var canvas = document.getElementById('report-canvas-list');
        if (!canvas) return;

        // Remove existing rulers
        canvas.querySelectorAll('.a4-page-break-ruler').forEach(function(r) { r.remove(); });

        var children = Array.from(canvas.children).filter(function(c) {
            return !c.classList.contains('a4-page-break-ruler') &&
                   !c.classList.contains('a4-width-indicator');
        });

        var cumulativeHeight = 0;
        var pageNum = 1;

        for (var i = 0; i < children.length; i++) {
            var childHeight = children[i].offsetHeight + 16; // include margin
            cumulativeHeight += childHeight;

            if (cumulativeHeight >= A4_CONTENT_HEIGHT_PX) {
                pageNum++;
                var ruler = document.createElement('hr');
                ruler.className = 'a4-page-break-ruler no-print';
                ruler.setAttribute('data-label', '↓ Page ' + pageNum + ' starts here');
                children[i].after(ruler);
                cumulativeHeight = 0; // reset for next page
            }
        }
    }

    
    /* ---- Observe DOM changes ---- */
    var observer = new MutationObserver(function() {
        initSortable();
        // Debounce ruler insertion
        
        clearTimeout(window._rulerTimeout);
        window._rulerTimeout = setTimeout(insertPageBreakRulers, 300);
    });

    document.addEventListener("DOMContentLoaded", function() {
        initSortable();
        observer.observe(document.body, { childList: true, subtree: true });
    });
})();
