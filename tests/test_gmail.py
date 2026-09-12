import base64
from email import message_from_bytes
from unittest.mock import Mock, patch
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from notifications.gmail_backend import EmailBackend, GmailDeliveryError
from notifications.models import EmailNotification
from notifications.services import deliver_after_commit, deliver_pending
from clinic.services import book_appointment, change_status
from tests.test_clinic import fixture, data


@override_settings(GMAIL_CLIENT_ID='test-client', GMAIL_CLIENT_SECRET='test-secret',
                   GMAIL_REFRESH_TOKEN='test-refresh', GMAIL_SENDER='sender@gmail.com')
class GmailBackendTests(SimpleTestCase):
    def message(self):
        message = EmailMultiAlternatives('Test subject', 'Plain body', 'Clinic <sender@gmail.com>', ['patient@example.com'])
        message.attach_alternative('<p>HTML body</p>', 'text/html')
        return message

    @patch('notifications.gmail_backend.requests.post')
    @patch('notifications.gmail_backend.Credentials')
    def test_sends_mime_over_https_with_send_only_scope(self, credentials, post):
        credentials.return_value.token = 'test-access'
        post.return_value = Mock(status_code=200, json=Mock(return_value={'id': 'message-id'}))
        self.assertEqual(EmailBackend().send_messages([self.message()]), 1)
        self.assertEqual(credentials.call_args.kwargs['scopes'], ['https://www.googleapis.com/auth/gmail.send'])
        request = post.call_args
        self.assertEqual(request.args[0], 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send')
        self.assertFalse(request.kwargs['allow_redirects'])
        self.assertEqual(request.kwargs['timeout'], (3, 5))
        mime = message_from_bytes(base64.urlsafe_b64decode(request.kwargs['json']['raw']))
        self.assertEqual(mime['To'], 'patient@example.com')
        self.assertEqual(mime['From'], 'Clinic <sender@gmail.com>')
        self.assertEqual([p.get_content_type() for p in mime.get_payload()], ['text/plain', 'text/html'])

    @patch('notifications.gmail_backend.requests.post')
    @patch('notifications.gmail_backend.Credentials')
    def test_provider_failure_is_sanitized_and_not_acknowledged(self, credentials, post):
        credentials.return_value.token = 'test-access'
        post.side_effect = RuntimeError('secret-token-and-private-message')
        with self.assertRaises(GmailDeliveryError) as error:
            EmailBackend().send_messages([self.message()])
        self.assertNotIn('secret-token', str(error.exception))
        self.assertEqual(EmailBackend(fail_silently=True).send_messages([self.message()]), 0)

    @patch('notifications.gmail_backend.requests.post')
    @patch('notifications.gmail_backend.Credentials')
    def test_invalid_refresh_token_does_not_send(self, credentials, post):
        credentials.return_value.refresh.side_effect = RuntimeError('invalid_grant secret')
        with self.assertRaises(GmailDeliveryError):
            EmailBackend().send_messages([self.message()])
        post.assert_not_called()

    @override_settings(GMAIL_REFRESH_TOKEN='')
    @patch('notifications.gmail_backend.requests.post')
    def test_missing_config_fails_without_network(self, post):
        with self.assertRaises(GmailDeliveryError):
            EmailBackend().send_messages([self.message()])
        post.assert_not_called()

    @patch('notifications.gmail_backend.requests.post')
    def test_different_sender_rejected(self, post):
        message = self.message()
        message.from_email = 'other@example.com'
        with self.assertRaises(GmailDeliveryError):
            EmailBackend().send_messages([message])
        post.assert_not_called()

    @patch('notifications.gmail_backend.requests.post')
    @patch('notifications.gmail_backend.Credentials')
    def test_quota_rejection_is_not_success(self, credentials, post):
        credentials.return_value.token = 'test-access'
        post.return_value = Mock(status_code=429)
        with self.assertRaises(GmailDeliveryError):
            EmailBackend().send_messages([self.message()])


@override_settings(EMAIL_SEND_IMMEDIATELY=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ImmediateDeliveryTests(TestCase):
    def setUp(self):
        self.user, self.doctor, self.day = fixture()

    def test_booking_and_confirmation_send_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            appointment, token = book_appointment(self.doctor, data(self.day))
            self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(EmailNotification.objects.filter(sent_at__isnull=False).count(), 2)
        with self.captureOnCommitCallbacks(execute=True):
            change_status(appointment, 'CONFIRMED')
        self.assertEqual(len(mail.outbox), 3)

    def test_rollback_discards_emails_and_callbacks(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    book_appointment(self.doctor, data(self.day))
                    raise RuntimeError('Rollback')
        self.assertEqual(EmailNotification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_delivery_failure_preserves_booking_and_retries(self):
        with patch('notifications.services.EmailMultiAlternatives.send', side_effect=RuntimeError('offline')):
            with self.captureOnCommitCallbacks(execute=True):
                appointment, token = book_appointment(self.doctor, data(self.day))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'PENDING')
        self.assertEqual(EmailNotification.objects.filter(sent_at__isnull=True, attempts=1).count(), 2)
        EmailNotification.objects.update(next_attempt_at=timezone.now())
        self.assertEqual(deliver_pending(), (2, 0))
        self.assertEqual(deliver_pending(), (0, 0))

    def test_only_new_notifications_are_sent_immediately(self):
        old = EmailNotification.objects.create(recipient='old@example.com', subject='Old', text_body='Old', html_body='Old')
        with self.captureOnCommitCallbacks(execute=True):
            book_appointment(self.doctor, data(self.day))
        old.refresh_from_db()
        self.assertIsNone(old.sent_at)
        self.assertEqual(len(mail.outbox), 2)

    @patch('notifications.services.deliver_pending', side_effect=RuntimeError('unavailable'))
    def test_post_commit_database_failure_is_contained(self, deliver):
        with self.assertLogs('notifications.services', level='WARNING'):
            deliver_after_commit(123)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend')
    def test_dummy_backend_cannot_discard_queued_messages(self):
        with self.captureOnCommitCallbacks(execute=True):
            book_appointment(self.doctor, data(self.day))
        self.assertEqual(EmailNotification.objects.filter(sent_at__isnull=True).count(), 2)


@override_settings(EMAIL_RETRY_TOKEN='a' * 48)
class RetryEndpointTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    @patch('notifications.views.deliver_pending')
    def test_missing_wrong_and_unicode_credentials_never_send(self, deliver):
        for header in ['', 'Bearer wrong', 'Bearer café']:
            self.assertEqual(self.client.post('/internal/retry-emails/', HTTP_AUTHORIZATION=header).status_code, 403)
        deliver.assert_not_called()

    @override_settings(EMAIL_RETRY_TOKEN='')
    @patch('notifications.views.deliver_pending')
    def test_endpoint_disabled_without_secret(self, deliver):
        self.assertEqual(self.client.post('/internal/retry-emails/', HTTP_AUTHORIZATION='Bearer ').status_code, 403)
        deliver.assert_not_called()

    @patch('notifications.views.deliver_pending', return_value=(2, 0))
    def test_authorized_post_has_bounded_batch_and_no_patient_data(self, deliver):
        response = self.client.post('/internal/retry-emails/', HTTP_AUTHORIZATION='Bearer ' + 'a' * 48)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'delivered': 2, 'deferred': 0})
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        deliver.assert_called_once_with(limit=2)
        self.assertEqual(self.client.get('/internal/retry-emails/').status_code, 405)

    @patch('notifications.views.deliver_pending', return_value=(0, 2))
    def test_delivery_failure_signals_scheduler(self, deliver):
        response = self.client.post('/internal/retry-emails/', HTTP_AUTHORIZATION='Bearer ' + 'a' * 48)
        self.assertEqual(response.status_code, 503)
