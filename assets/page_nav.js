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
        var nodes = document.querySelectorAll('.app-page-link');
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

    function syncPageNav(pathname) {
        if (typeof pathname === 'string' && pathname) {
            currentPath = pathname;
        } else if (!currentPath) {
            currentPath = window.location.pathname;
        }
        applyNavCurrentState(currentPath);
    }

    window.dash_clientside.page_nav.sync = syncPageNav;

    window.addEventListener('popstate', function () {
        syncPageNav();
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            syncPageNav();
        });
    } else {
        syncPageNav();
    }
})();
