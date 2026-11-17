(function () {
    if (!window.fetch) {
        return;
    }
    var original = window.fetch;
    window.fetch = function (input, init) {
        var raw = typeof input === 'string' ? input : (input && input.url) || '';
        var path = raw;
        try {
            path = new URL(raw, window.location.href).pathname;
        } catch (err) {
            path = raw;
        }
        return original.apply(this, arguments).then(function (response) {
            if (response && response.status === 401 && path.indexOf('/_dash-') === 0) {
                var next = window.location.pathname + window.location.search;
                window.location.assign('/login?next=' + encodeURIComponent(next));
                return new Promise(function () {});
            }
            return response;
        });
    };
}());
