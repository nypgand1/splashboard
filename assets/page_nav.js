(function () {
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.page_nav = window.dash_clientside.page_nav || {};

    function cleanPath(pathname) {
        var path = typeof pathname === 'string' && pathname ? pathname : window.location.pathname;
        if (!path) {
            path = '/';
        }
        if (path.length > 1 && path.charAt(path.length - 1) === '/') {
            path = path.slice(0, -1);
        }
        return path;
    }

    function sectionState(pathname) {
        var path = cleanPath(pathname);
        if (path === '/' || path === '/game' || path.indexOf('/game/') === 0) {
            return {section: 'schedule', page: path === '/'};
        }
        if (path === '/team-stats') {
            return {section: 'team-stats', page: true};
        }
        return {section: '', page: false};
    }

    function sectionOf(node) {
        var match = String(node.className || '').match(/app-section-([a-z0-9-]+)/);
        return match ? match[1] : '';
    }

    var currentPath = '';

    function mark(pathname) {
        var state = sectionState(pathname);
        var nodes = document.querySelectorAll('.app-page-link, .app-page-menu-item');
        var index;
        for (index = 0; index < nodes.length; index += 1) {
            var node = nodes[index];
            var on = state.section !== '' && sectionOf(node) === state.section;
            if (on) {
                node.setAttribute('data-current', 'true');
            } else {
                node.removeAttribute('data-current');
            }
            if (on && state.page) {
                node.setAttribute('aria-current', 'page');
            } else {
                node.removeAttribute('aria-current');
            }
        }
    }

    function nodeHasPageItem(node) {
        if (!node || node.nodeType !== 1) {
            return false;
        }
        if (node.matches && node.matches('.app-page-menu-item, .app-page-link')) {
            return true;
        }
        return !!(node.querySelector && node.querySelector('.app-page-menu-item, .app-page-link'));
    }

    function measure(nav) {
        var bar = nav.closest('.app-navbar-bar');
        var brand = bar && bar.querySelector('.app-navbar-brand-link');
        var links = nav.querySelector('.app-page-links');
        if (!bar || !brand || !links || bar.clientWidth <= 0) {
            return;
        }
        var styles = window.getComputedStyle(bar);
        var pad = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
        var gap = parseFloat(styles.columnGap);
        if (!isFinite(gap)) {
            gap = 20;
        }
        var available = bar.clientWidth - pad - brand.getBoundingClientRect().width - gap;
        var mode = links.scrollWidth <= available + 1 ? 'links' : 'menu';
        if (nav.getAttribute('data-mode') !== mode) {
            nav.setAttribute('data-mode', mode);
        }
    }

    function watch(nav) {
        if (nav.__pageNavWatch || !window.ResizeObserver) {
            return;
        }
        var bar = nav.closest('.app-navbar-bar') || nav;
        var observer = new ResizeObserver(function () {
            measure(nav);
        });
        observer.observe(bar);
        nav.__pageNavWatch = observer;
    }

    function sync(pathname) {
        if (typeof pathname === 'string' && pathname) {
            currentPath = pathname;
        } else if (!currentPath) {
            currentPath = window.location.pathname;
        }
        document.querySelectorAll('.app-page-nav').forEach(function (nav) {
            watch(nav);
            measure(nav);
        });
        mark(currentPath);
    }

    function watchPortal() {
        if (!document.body || document.body.__pageNavPortal) {
            return;
        }
        var observer = new MutationObserver(function (records) {
            var index;
            var record;
            for (index = 0; index < records.length; index += 1) {
                record = records[index];
                if (nodeHasPageItem(record.target) || addedPageItem(record.addedNodes)) {
                    mark(currentPath || window.location.pathname);
                    return;
                }
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
        document.body.__pageNavPortal = observer;
    }

    function addedPageItem(nodes) {
        var index;
        for (index = 0; index < nodes.length; index += 1) {
            if (nodeHasPageItem(nodes[index])) {
                return true;
            }
        }
        return false;
    }

    window.dash_clientside.page_nav.sync = sync;

    function boot() {
        sync();
        window.setTimeout(sync, 0);
        window.setTimeout(sync, 300);
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(function () {
                sync();
            });
        }
    }

    window.addEventListener('popstate', function () {
        sync();
    });

    function start() {
        watchPortal();
        boot();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
