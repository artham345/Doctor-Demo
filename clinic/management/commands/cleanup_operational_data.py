from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from clinic.models import RateLimit
from notifications.models import EmailNotification

class Command(BaseCommand):
    help = 'Remove expired rate-limit counters and delivered email metadata older than 30 days. Patient records are not deleted.'
    def handle(self, *args, **kwargs):
        RateLimit.objects.filter(expires_at__lt=timezone.now()).delete()
        EmailNotification.objects.filter(sent_at__lt=timezone.now()-timedelta(days=30)).delete()
        self.stdout.write('Expired operational data removed.')
