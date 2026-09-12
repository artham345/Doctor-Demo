from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from clinic.models import Doctor

class Command(BaseCommand):
    help = 'Delete only a marked demonstration clinic and all its data.'
    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true')
    @transaction.atomic
    def handle(self, *args, **options):
        if not options['confirm']:
            raise CommandError('This deletes all data belonging to the demo clinic. Re-run with --confirm.')
        for doctor in Doctor.objects.select_for_update().filter(is_demo=True):
            user_id = doctor.user_id
            doctor.appointments.all().delete()
            doctor.patients.all().delete()
            doctor.delete()
            get_user_model().objects.filter(pk=user_id).delete()
        self.stdout.write('Marked demo clinics removed. Other doctors and their data were preserved.')
