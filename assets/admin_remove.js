(function () {
    document.addEventListener('click', function (event) {
        var target = event.target;
        if (!target || !target.closest) {
            return;
        }
        var button = target.closest('[data-admin-remove]');
        if (!button) {
            return;
        }
        var dialog = document.getElementById('admin-remove-dialog');
        if (!dialog || !dialog.showModal) {
            return;
        }
        var email = button.getAttribute('data-admin-remove') || '';
        dialog.dataset.email = email;
        var copy = document.getElementById('admin-remove-copy');
        if (copy) {
            copy.textContent = 'Remove ' + email + ' from the list?';
        }
        if (!dialog.open) {
            dialog.showModal();
        }
    });

    document.addEventListener('close', function (event) {
        var dialog = event.target;
        if (!dialog || dialog.id !== 'admin-remove-dialog') {
            return;
        }
        var choice = dialog.returnValue;
        dialog.returnValue = '';
        if (choice !== 'remove') {
            return;
        }
        var email = dialog.dataset.email || '';
        if (!email || !window.dash_clientside || !window.dash_clientside.set_props) {
            return;
        }
        window.dash_clientside.set_props('admin-remove-go', {data: email});
    }, true);
}());
