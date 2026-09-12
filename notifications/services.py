from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from .models import EmailNotification

def queue_appointment_email(appointment, event, token=None, recipient=None):
    recipient = recipient or appointment.patient.email
    if not recipient:
        return
    titles = {'received': 'Your appointment request has been received', 'new': 'New appointment request', 'confirmed': 'Your appointment is confirmed', 'cancelled': 'Your appointment has been cancelled'}
    context = {'appointment': appointment, 'heading': titles[event], 'event': event, 'site_url': settings.SITE_URL, 'manage_url': settings.SITE_URL + reverse('booking-manage', args=[appointment.booking_id, token]) if token else None}
    EmailNotification.objects.create(appointment=appointment, recipient=recipient, subject=titles[event], text_body=render_to_string('emails/appointment.txt', context), html_body=render_to_string('emails/appointment.html', context))

def deliver_pending(limit=50):
    delivered = failed = 0
    for _ in range(limit):
        with transaction.atomic():
            item = EmailNotification.objects.select_for_update(skip_locked=True).filter(sent_at__isnull=True, next_attempt_at__lte=timezone.now()).first()
            if item is None:
                break
            item.attempts += 1
            try:
                email = EmailMultiAlternatives(item.subject, item.text_body, settings.DEFAULT_FROM_EMAIL, [item.recipient])
                email.attach_alternative(item.html_body, 'text/html')
                email.send(fail_silently=False)
                item.sent_at = timezone.now()
                item.last_error = ''
                # Cancellation links and message bodies are no longer needed after delivery.
                item.text_body = item.html_body = ''
                delivered += 1
            except Exception as exc:
                item.last_error = type(exc).__name__
                item.next_attempt_at = timezone.now() + timedelta(minutes=min(60, 2 ** min(item.attempts, 6)))
                failed += 1
            item.save()
    return delivered, failed
