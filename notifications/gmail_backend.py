"""Send MIME messages using Gmail HTTPS and a send-only OAuth grant."""
import base64
from email.utils import parseaddr
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

SCOPE = 'https://www.googleapis.com/auth/gmail.send'


class GmailDeliveryError(Exception):
    """Safe to log: no provider bodies, tokens or message content."""


class GmailConfigurationError(GmailDeliveryError):
    pass


class GmailAuthorizationError(GmailDeliveryError):
    pass


class GmailPermissionError(GmailDeliveryError):
    pass


class GmailQuotaError(GmailDeliveryError):
    pass


class EmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        credentials = None
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                if not all([settings.GMAIL_CLIENT_ID, settings.GMAIL_CLIENT_SECRET,
                            settings.GMAIL_REFRESH_TOKEN, settings.GMAIL_SENDER]):
                    raise GmailConfigurationError('Gmail configuration is incomplete.')
                if parseaddr(message.from_email)[1].lower() != settings.GMAIL_SENDER.lower():
                    raise GmailConfigurationError('From address must match the authorized Gmail sender.')
                if credentials is None:
                    credentials = Credentials(
                        token=None, refresh_token=settings.GMAIL_REFRESH_TOKEN,
                        token_uri='https://oauth2.googleapis.com/token',
                        client_id=settings.GMAIL_CLIENT_ID,
                        client_secret=settings.GMAIL_CLIENT_SECRET, scopes=[SCOPE],
                    )
                    transport = Request()
                    refresh_requests = 0
                    def bounded_request(*args, **kwargs):
                        nonlocal refresh_requests
                        refresh_requests += 1
                        if refresh_requests > 1:
                            raise GmailDeliveryError('Token refresh deferred to the queue.')
                        kwargs['timeout'] = (3, 5)
                        return transport(*args, **kwargs)
                    credentials.refresh(bounded_request)
                mime = message.message()
                if message.bcc:
                    mime['Bcc'] = ', '.join(message.bcc)
                raw = base64.urlsafe_b64encode(mime.as_bytes(linesep='\r\n')).decode('ascii')
                response = requests.post(
                    'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                    headers={'Authorization': 'Bearer ' + credentials.token},
                    json={'raw': raw}, timeout=(3, 5), allow_redirects=False,
                )
                if response.status_code == 401:
                    raise GmailAuthorizationError('Gmail authorization must be renewed.')
                if response.status_code == 403:
                    raise GmailPermissionError('Check Gmail API access, scopes and account limits.')
                if response.status_code == 429:
                    raise GmailQuotaError('Gmail quota reached; delivery will retry.')
                if response.status_code != 200 or not response.json().get('id'):
                    raise GmailDeliveryError('Gmail did not acknowledge the message.')
                sent += 1
            except GmailDeliveryError:
                if not self.fail_silently:
                    raise
            except RefreshError:
                if not self.fail_silently:
                    raise GmailAuthorizationError('Gmail authorization must be renewed.') from None
            except Exception:
                if not self.fail_silently:
                    raise GmailDeliveryError('Gmail delivery failed; check authorization and quota.') from None
        return sent
