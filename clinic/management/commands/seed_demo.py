import os
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from clinic.models import Appointment, Doctor, DoctorSchedule, Service
from clinic.services import available_slots, book_appointment
from notifications.models import EmailNotification

class Command(BaseCommand):
    help = 'Create a local-only, clearly labelled demonstration clinic; existing data is preserved.'
    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Demo data is disabled in production.')
        if Doctor.objects.filter(is_public=True, is_demo=False).exists():
            raise CommandError('A real public doctor already exists. Demo seeding stopped.')
        User = get_user_model()
        existing_user = User.objects.filter(username='demo.doctor').first()
        if existing_user and not Doctor.objects.filter(user=existing_user, is_demo=True).exists():
            raise CommandError('The demo username already belongs to a non-demo account.')
        user, created = User.objects.get_or_create(username='demo.doctor', defaults={'email': 'doctor@example.com'})
        if created:
            user.set_password(os.getenv('DEMO_PASSWORD', 'DemoClinic!2026'))
            user.save()
        doctor, created = Doctor.objects.get_or_create(user=user, defaults={'name': 'Dr. John Sharma', 'specialization': 'Cardiologist', 'biography': 'Dr. John Sharma believes that good care begins with listening. With a focus on heart health and preventive care, he takes time to understand each person’s concerns and explain the next steps clearly. This is a fictional demonstration profile; replace it with the doctor’s verified biography before launch.', 'qualifications': 'MBBS, MD (General Medicine)\nDM (Cardiology)', 'education': 'Medical education and specialist training — replace with verified institution names and dates.', 'certifications': 'Replace with verified professional registrations and certifications.', 'expertise': 'Preventive cardiology\nHeart health consultations\nBlood pressure management\nOngoing cardiac care', 'experience': 15, 'phone': '+919876543210', 'email': 'doctor@example.com', 'clinic_name': 'Everwell Heart Clinic', 'clinic_address': '24, Park Avenue, Indiranagar\nBengaluru, Karnataka 560038\nDemonstration address', 'is_demo': True})
        if not created:
            self.stdout.write('Demo clinic already exists. No appointments or credentials were changed.')
            return
        services = [('Heart health consultation', 'A dedicated visit to discuss your concerns, understand your history, and plan your next steps.', 'heart'), ('Preventive heart care', 'A conversation about your risk factors and practical habits to support your long-term heart health.', 'shield'), ('Follow-up consultation', 'Ongoing attention to your progress, questions, and care plan with your doctor.', 'pulse')]
        for name, description, icon in services:
            Service.objects.create(doctor=doctor, name=name, description=description, icon=icon)
        from datetime import time
        for weekday in range(6):
            for start, end in [(time(10), time(13)), (time(17), time(20))]:
                DoctorSchedule.objects.create(doctor=doctor, day_of_week=weekday, start_time=start, end_time=end, slot_duration=30)
        names = ['Ananya Rao', 'Rahul Sharma', 'Meera Iyer', 'Arjun Patel', 'Priya Menon']
        for offset, name in enumerate(names):
            day = timezone.localdate() + timedelta(days=offset)
            while not available_slots(doctor, day):
                day += timedelta(days=1)
            start = available_slots(doctor, day)[0][0]
            appointment, _ = book_appointment(doctor, {'name': name, 'phone': f'+91980000000{offset}', 'email': '', 'age': 30 + offset * 5, 'gender': '', 'appointment_date': day, 'appointment_time': start, 'reason': 'Demonstration consultation', 'message': ''})
            if offset % 2 == 0:
                appointment.status = Appointment.Status.CONFIRMED
                appointment.save(update_fields=['status'])
        EmailNotification.objects.filter(appointment__doctor=doctor).delete()
        self.stdout.write(self.style.SUCCESS('Demo clinic created. Login: demo.doctor / DemoClinic!2026 (or DEMO_PASSWORD if set). Demo only; never use in production.'))
