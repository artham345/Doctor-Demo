import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from google_auth_oauthlib.flow import InstalledAppFlow
from notifications.gmail_backend import SCOPE


class Command(BaseCommand):
    help = 'Authorize Gmail locally and save a refresh token in ignored .env.gmail.'
    requires_system_checks = []

    def handle(self, *args, **options):
        if not settings.GMAIL_CLIENT_ID or not settings.GMAIL_CLIENT_SECRET:
            raise CommandError('Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in your local .env first.')
        target = settings.BASE_DIR / '.env.gmail'
        if target.exists():
            raise CommandError('Move existing .env.gmail to a secure backup before authorizing again.')
        flow = InstalledAppFlow.from_client_config({'installed': {
            'client_id': settings.GMAIL_CLIENT_ID,
            'client_secret': settings.GMAIL_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }}, scopes=[SCOPE], autogenerate_code_verifier=True)
        try:
            credentials = flow.run_local_server(
                host='127.0.0.1', port=0, timeout_seconds=180,
                authorization_prompt_message='Authorize the clinic sender in the browser that opens.',
                success_message='Gmail authorization received. You can close this tab.',
                prompt='consent',
            )
            if not credentials.refresh_token:
                raise ValueError('No refresh token')
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                output.write('GMAIL_REFRESH_TOKEN=' + credentials.refresh_token + '\n')
        except Exception:
            raise CommandError('Authorization could not complete. Check Google consent settings and try again.') from None
        self.stdout.write('Saved refresh token to .env.gmail (ignored by Git). Copy it to local .env and Render secrets. No email was sent.')
