'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('booking-form');
  if (!form) return;
  const date = document.getElementById('id_appointment_date');
  const time = document.getElementById('id_appointment_time');
  const slots = document.getElementById('slot-list');
  const status = document.getElementById('slot-status');
  const submit = document.getElementById('book-submit');
  const summary = document.getElementById('booking-summary');
  let controller;
  const loadSlots = async () => {
    controller?.abort();
    controller = new AbortController();
    const selectedDate = date.value;
    time.value = '';
    slots.replaceChildren();
    submit.disabled = true;
    summary.textContent = 'Select your preferred date and time above.';
    if (!selectedDate || !date.checkValidity()) {
      status.textContent = 'Choose a date within the booking window.';
      return;
    }
    status.textContent = 'Checking available appointments…';
    slots.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(`${form.dataset.availabilityUrl}?date=${encodeURIComponent(selectedDate)}`, {signal: controller.signal, cache: 'no-store'});
      if (!response.ok) throw new Error('Availability unavailable');
      const data = await response.json();
      if (date.value !== selectedDate) return;
      status.textContent = data.slots.length ? `${data.slots.length} times available · ${data.timezone}` : 'No appointments available on this date. Please choose another day.';
      for (const slot of data.slots) {
        const label = document.createElement('label');
        label.className = 'slot-option';
        const radio = document.createElement('input');
        radio.type = 'radio'; radio.name = 'slot_choice'; radio.value = slot.time;
        const caption = document.createElement('span'); caption.textContent = slot.label;
        radio.addEventListener('change', () => {
          time.value = slot.time;
          submit.disabled = false;
          const readable = new Date(`${selectedDate}T12:00:00`).toLocaleDateString(undefined, {weekday:'long', day:'numeric', month:'long', year:'numeric'});
          summary.textContent = `${readable} at ${slot.label} · ${slot.duration} minutes · ${data.timezone}`;
        });
        label.append(radio, caption); slots.append(label);
      }
    } catch (error) {
      if (error.name !== 'AbortError') status.textContent = 'We couldn’t load appointments. Choose the date again to retry, or call the clinic.';
    } finally { if (date.value === selectedDate) slots.removeAttribute('aria-busy'); }
  };
  date.addEventListener('change', loadSlots);
  if (date.value) loadSlots();
  form.addEventListener('submit', event => {
    if (!time.value) { event.preventDefault(); status.textContent = 'Please select an available time.'; date.focus(); return; }
    submit.disabled = true; submit.textContent = 'Reserving your appointment…';
  });
  window.addEventListener('pageshow', () => { if (date.value) loadSlots(); });
});
