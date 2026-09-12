from datetime import timedelta
from functools import partial
import logging
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
    item = EmailNotification.objects.create(appointment=appointment, recipient=recipient, subject=titles[event], text_body=render_to_string('emails/appointment.txt', context), html_body=render_to_string('emails/appointment.html', context))
    if settings.EMAIL_SEND_IMMEDIATELY:
        transaction.on_commit(partial(deliver_after_commit, item.pk))


def deliver_after_commit(notification_id):
    # Never turn an already committed booking into a failure page.
    try:
        deliver_pending(limit=1, notification_ids=[notification_id])
    except Exception as exc:
        logging.getLogger(__name__).warning('Post-commit email deferred (%s).', type(exc).__name__)

def deliver_pending(limit=50, notification_ids=None):
    delivered = failed = 0
    for _ in range(limit):
        with transaction.atomic():
            pending = EmailNotification.objects.select_for_update(skip_locked=True).filter(sent_at__isnull=True, next_attempt_at__lte=timezone.now())
            if notification_ids is not None:
                pending = pending.filter(pk__in=notification_ids)
            item = pending.first()
            if item is None:
                break
            item.attempts += 1
            try:
                email = EmailMultiAlternatives(item.subject, item.text_body, settings.DEFAULT_FROM_EMAIL, [item.recipient])
                email.attach_alternative(item.html_body, 'text/html')
                if settings.EMAIL_BACKEND.endswith(('dummy.EmailBackend', 'console.EmailBackend')):
                    raise RuntimeError('A real delivery backend is not configured.')
                if email.send(fail_silently=False) != 1:
                    raise RuntimeError('Email backend did not acknowledge delivery.')
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
