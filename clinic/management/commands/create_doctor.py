from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from clinic.models import Doctor

class Command(BaseCommand):
    help = 'Create a real doctor portal account interactively, without placing passwords in shell history.'
    @transaction.atomic
    def handle(self, *args, **options):
        if Doctor.objects.filter(is_public=True).exists():
            raise CommandError('A public doctor exists. Update that profile in the portal, or remove demo data first.')
        username = input('Doctor username: ').strip()
        name = input('Doctor name (including title): ').strip()
        email = input('Clinic email: ').strip()
        phone = input('Clinic phone (digits with optional +): ').strip()
        clinic_name = input('Clinic name: ').strip()
        specialization = input('Specialization: ').strip()
        address = input('Clinic address: ').strip()
        password = getpass('Password: ')
        if password != getpass('Repeat password: '):
            raise CommandError('Passwords do not match.')
        user = get_user_model()(username=username, email=email)
        try:
            user.full_clean(exclude=['password'])
            validate_password(password, user)
            user.set_password(password)
            user.save()
            doctor = Doctor(user=user, name=name, email=email, phone=phone, clinic_name=clinic_name, specialization=specialization, clinic_address=address)
            doctor.full_clean()
            doctor.save()
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        self.stdout.write('Doctor created. Sign in to complete your profile, add services, and set working periods.')
