'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const modalElement = document.getElementById('confirm-modal');
  let pendingForm = null;
  let confirmed = false;
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (confirmed && pendingForm === form) return;
      if (!window.bootstrap || !modalElement) {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        return;
      }
      event.preventDefault();
      pendingForm = form;
      confirmed = false;
      document.getElementById('confirm-description').textContent = form.dataset.confirm;
      bootstrap.Modal.getOrCreateInstance(modalElement).show();
    });
  });
  document.getElementById('confirm-action')?.addEventListener('click', () => {
    if (pendingForm) {
      confirmed = true;
      pendingForm.requestSubmit();
    }
  });
});
