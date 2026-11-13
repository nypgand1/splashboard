(function () {
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.page_nav = window.dash_clientside.page_nav || {};

    function normalizeNavPath(pathname) {
        var path = typeof pathname === 'string' && pathname ? pathname : window.location.pathname;
        if (!path) {
            path = '/';
        }
        if (path.length > 1 && path.charAt(path.length - 1) === '/') {
            path = path.slice(0, -1);
        }
        return path;
    }

    function resolveNavSectionState(pathname) {
        var path = normalizeNavPath(pathname);
        if (path === '/' || path === '/game' || path.indexOf('/game/') === 0) {
            return {section: 'schedule', page: path === '/'};
        }
        if (path === '/team-stats') {
            return {section: 'team-stats', page: true};
        }
        return {section: '', page: false};
    }

    function readItemSection(node) {
        var match = String(node.className || '').match(/app-section-([a-z0-9-]+)/);
        return match ? match[1] : '';
    }

    var currentPath = '';

    function applyNavCurrentState(pathname) {
        var state = resolveNavSectionState(pathname);
        var nodes = document.querySelectorAll('.app-page-link, .app-page-menu-item');
        var index;
        for (index = 0; index < nodes.length; index += 1) {
            var node = nodes[index];
            var on = state.section !== '' && readItemSection(node) === state.section;
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

    function containsNavPageItem(node) {
        if (!node || node.nodeType !== 1) {
            return false;
        }
        if (node.matches && node.matches('.app-page-menu-item, .app-page-link')) {
            return true;
        }
        return !!(node.querySelector && node.querySelector('.app-page-menu-item, .app-page-link'));
    }

    function measureInlinePageNav(nav) {
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

    function observePageNavResize(nav) {
        if (nav.__pageNavWatch || !window.ResizeObserver) {
            return;
        }
        var bar = nav.closest('.app-navbar-bar') || nav;
        var observer = new ResizeObserver(function () {
            measureInlinePageNav(nav);
        });
        observer.observe(bar);
        nav.__pageNavWatch = observer;
    }

    function syncPageNav(pathname) {
        if (typeof pathname === 'string' && pathname) {
            currentPath = pathname;
        } else if (!currentPath) {
            currentPath = window.location.pathname;
        }
        document.querySelectorAll('.app-page-nav').forEach(function (nav) {
            observePageNavResize(nav);
            measureInlinePageNav(nav);
        });
        applyNavCurrentState(currentPath);
    }

    function observeDropdownPortal() {
        if (!document.body || document.body.__pageNavPortal) {
            return;
        }
        var observer = new MutationObserver(function (records) {
            var index;
            var record;
            for (index = 0; index < records.length; index += 1) {
                record = records[index];
                if (containsNavPageItem(record.target) || hasAddedNavPageItem(record.addedNodes)) {
                    applyNavCurrentState(currentPath || window.location.pathname);
                    return;
                }
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
        document.body.__pageNavPortal = observer;
    }

    function hasAddedNavPageItem(nodes) {
        var index;
        for (index = 0; index < nodes.length; index += 1) {
            if (containsNavPageItem(nodes[index])) {
                return true;
            }
        }
        return false;
    }

    window.dash_clientside.page_nav.sync = syncPageNav;

    function schedulePageNavSync() {
        syncPageNav();
        window.setTimeout(syncPageNav, 0);
        window.setTimeout(syncPageNav, 300);
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(function () {
                syncPageNav();
            });
        }
    }

    window.addEventListener('popstate', function () {
        syncPageNav();
    });

    function bootPageNav() {
        observeDropdownPortal();
        schedulePageNavSync();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootPageNav);
    } else {
        bootPageNav();
    }
})();
