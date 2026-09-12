import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections, OperationalError, ProgrammingError
from notifications.services import deliver_pending

class Command(BaseCommand):
    help = 'Deliver queued emails with retry; --watch runs the worker continuously.'
    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                sent, failed = deliver_pending()
            except (OperationalError, ProgrammingError):
                if not options['watch']:
                    raise
                self.stderr.write('Database temporarily unavailable; retrying in 10 seconds.')
                time.sleep(10)
                continue
            if sent or failed:
                self.stdout.write(f'Delivered: {sent}; deferred: {failed}')
            if not options['watch']:
                return
            time.sleep(10)
