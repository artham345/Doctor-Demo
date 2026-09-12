import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from threading import Barrier
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from clinic.forms import BookingForm
from clinic.models import Appointment, Doctor, DoctorSchedule, DoctorLeave, Patient, Service
from clinic.services import SLOT_TAKEN, add_leave, available_slots, book_appointment, change_status, generated_slots, save_schedule
from notifications.models import EmailNotification
from notifications.services import deliver_pending

def fixture():
    user = get_user_model().objects.create_user('doctor', password='TestPass!27392')
    doctor = Doctor.objects.create(user=user, name='Dr. Test', specialization='Cardiology', phone='+919876543210', email='doctor@example.com', clinic_name='Test Clinic', clinic_address='Test address')
    day = timezone.localdate() + timedelta(days=2)
    DoctorSchedule.objects.create(doctor=doctor, day_of_week=day.weekday(), start_time=time(10), end_time=time(13), slot_duration=30)
    DoctorSchedule.objects.create(doctor=doctor, day_of_week=day.weekday(), start_time=time(17), end_time=time(19), slot_duration=30)
    Service.objects.create(doctor=doctor, name='Consultation', description='A consultation')
    return user, doctor, day

def data(day, at=time(10), **overrides):
    result = {'name': 'Test Patient', 'phone': '+919900001111', 'email': 'patient@example.com', 'age': 30, 'gender': '', 'appointment_date': day, 'appointment_time': at, 'reason': 'Consultation', 'message': '', 'consent': True}
    result.update(overrides)
    return result

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ClinicTests(TestCase):
    def setUp(self):
        self.user, self.doctor, self.day = fixture()
    def book(self, **kwargs):
        return book_appointment(self.doctor, data(self.day, **kwargs))
    def test_generated_slots_respect_periods_breaks_duration(self):
        slots = generated_slots(self.doctor, self.day)
        self.assertEqual(len(slots), 10)
        self.assertIn((time(12, 30), 30), slots)
        self.assertNotIn((time(13), 30), slots)
        self.assertNotIn((time(16, 30), 30), slots)
    def test_closed_past_leave_and_outside_window(self):
        self.assertEqual(available_slots(self.doctor, self.day + timedelta(days=1)), [])
        self.assertEqual(available_slots(self.doctor, timezone.localdate()-timedelta(days=1)), [])
        self.assertEqual(available_slots(self.doctor, self.day + timedelta(days=100)), [])
        add_leave(DoctorLeave(doctor=self.doctor, date=self.day))
        self.assertEqual(available_slots(self.doctor, self.day), [])
    def test_booking_creates_patient_appointment_and_emails(self):
        appointment, token = self.book()
        self.assertEqual(appointment.status, 'PENDING')
        self.assertTrue(appointment.booking_id.startswith(f'APT-{self.day.year}-'))
        self.assertEqual(appointment.token_digest, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(EmailNotification.objects.count(), 2)
        self.assertNotIn((time(10), 30), available_slots(self.doctor, self.day))
    def test_invalid_times_rejected(self):
        for at in [time(9), time(10, 15), time(13), time(16), time(19)]:
            with self.assertRaises(ValidationError):
                self.book(at=at)
        self.assertEqual(Appointment.objects.count(), 0)
    def test_past_booking_rejected(self):
        with self.assertRaises(ValidationError):
            book_appointment(self.doctor, data(timezone.localdate()-timedelta(days=1)))
    def test_booked_slot_rejected_and_no_orphan_patient(self):
        self.book()
        with self.assertRaisesMessage(ValidationError, SLOT_TAKEN):
            self.book(name='Second Patient')
        self.assertEqual(Patient.objects.count(), 1)
    def test_database_constraint_blocks_direct_duplicate(self):
        appointment, _ = self.book()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(doctor=self.doctor, patient=appointment.patient, appointment_date=self.day, appointment_time=time(10), token_digest='x', booking_id='DIFFERENT')
    def test_phone_email_and_age_validation(self):
        for overrides in [{'phone': 'abc'}, {'email': 'bad-address'}, {'age': -1}, {'age': 121}, {'consent': False}]:
            self.assertFalse(BookingForm(data(self.day, **overrides)).is_valid())
        form = BookingForm(data(self.day, phone='+91 99000-01111', email='', age=''))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['phone'], '+919900001111')
    def test_post_booking_and_secure_receipt(self):
        response = self.client.post(reverse('book'), data(self.day))
        self.assertEqual(response.status_code, 302)
        receipt = self.client.get(response.url)
        self.assertContains(receipt, 'Your appointment is reserved')
        self.assertNotContains(receipt, 'Test Patient')
        self.assertEqual(receipt['Cache-Control'], 'no-store, private')
    def test_availability_exposes_no_patient_information(self):
        self.book()
        response = self.client.get(reverse('availability'), {'date': self.day.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Test Patient')
        self.assertNotContains(response, 'patient@example.com')
        self.assertNotIn('10:00', [s['time'] for s in response.json()['slots']])
        self.assertEqual(self.client.get(reverse('availability'), {'date': 'wrong'}).status_code, 400)
    def test_unauthorized_portal_redirects(self):
        for name in ['doctor-dashboard', 'doctor-appointments', 'doctor-patients', 'doctor-calendar', 'doctor-schedule', 'doctor-leave', 'doctor-services', 'doctor-profile', 'doctor-inbox']:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn('/doctor/login/', response.url)
    def test_login_and_all_portal_pages(self):
        response = self.client.post(reverse('doctor-login'), {'username': 'doctor', 'password': 'TestPass!27392'})
        self.assertRedirects(response, reverse('doctor-dashboard'))
        appointment, _ = self.book()
        for name in ['doctor-dashboard', 'doctor-appointments', 'doctor-patients', 'doctor-calendar', 'doctor-schedule', 'doctor-leave', 'doctor-services', 'doctor-profile', 'doctor-inbox', 'doctor-password']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(reverse('doctor-appointment', args=[appointment.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('doctor-patient', args=[appointment.patient_id])).status_code, 200)
    def test_non_doctor_cannot_access(self):
        other = get_user_model().objects.create_user('other', password='OtherTest!123')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('doctor-dashboard')).status_code, 403)
    def test_doctor_ownership(self):
        appointment, _ = self.book()
        user = get_user_model().objects.create_user('second')
        other = Doctor.objects.create(user=user, name='Other', email='other@example.com', phone='+919876543211', clinic_name='Other', clinic_address='Other', is_public=False)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('doctor-appointment', args=[appointment.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('doctor-appointment-status', args=[appointment.pk]), {'status': 'CANCELLED'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('doctor-patient', args=[appointment.patient_id])).status_code, 404)
    def test_token_cancellation_and_rebooking(self):
        appointment, token = self.book()
        path = reverse('booking-manage', args=[appointment.booking_id, token])
        self.client.get(path)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'PENDING')
        self.assertEqual(self.client.get(reverse('booking-manage', args=[appointment.booking_id, 'wrong'])).status_code, 404)
        response = self.client.post(path)
        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'CANCELLED')
        self.book(name='Replacement')
        self.assertEqual(Appointment.objects.count(), 2)
    def test_calendar_download_private_and_no_sensitive_details(self):
        appointment, token = self.book()
        response = self.client.get(reverse('booking-calendar', args=[appointment.booking_id, token]))
        self.assertContains(response, 'BEGIN:VCALENDAR')
        self.assertNotContains(response, 'Test Patient')
        self.assertIn('attachment', response['Content-Disposition'])
    def test_status_transitions(self):
        appointment, _ = self.book()
        with self.assertRaises(ValidationError):
            change_status(appointment, 'COMPLETED')
        appointment = change_status(appointment, 'CONFIRMED')
        with self.assertRaises(ValidationError):
            change_status(appointment, 'NO_SHOW')
        appointment = change_status(appointment, 'CANCELLED')
        with self.assertRaises(ValidationError):
            change_status(appointment, 'CONFIRMED')
    def test_cannot_create_leave_over_bookings(self):
        self.book()
        with self.assertRaises(ValidationError):
            add_leave(DoctorLeave(doctor=self.doctor, date=self.day))
        self.assertEqual(DoctorLeave.objects.count(), 0)
    def test_schedule_edit_preserves_bookings(self):
        self.book()
        period = self.doctor.schedules.first()
        with self.assertRaises(ValidationError):
            save_schedule(period, delete=True)
        self.assertEqual(self.doctor.schedules.count(), 2)
        period = self.doctor.schedules.first()
        period.slot_duration = 20
        with self.assertRaises(ValidationError):
            save_schedule(period)
        period.refresh_from_db()
        self.assertEqual(period.slot_duration, 30)
    def test_overlap_schedule_rejected(self):
        with self.assertRaises(ValidationError):
            save_schedule(DoctorSchedule(doctor=self.doctor, day_of_week=self.day.weekday(), start_time=time(12), end_time=time(14)))
    def test_same_phone_does_not_overwrite_patient(self):
        first, _ = self.book()
        second, _ = self.book(at=time(10, 30), name='Another person')
        self.assertNotEqual(first.patient_id, second.patient_id)
        first.patient.refresh_from_db()
        self.assertEqual(first.patient.name, 'Test Patient')
    def test_email_worker_and_retry(self):
        self.book()
        sent, failed = deliver_pending()
        self.assertEqual((sent, failed), (2, 0))
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse(EmailNotification.objects.exclude(html_body='').exists())
        self.book(at=time(10, 30))
        with patch('notifications.services.EmailMultiAlternatives.send', side_effect=OSError('private smtp details')):
            sent, failed = deliver_pending()
        self.assertEqual((sent, failed), (0, 2))
        self.assertTrue(EmailNotification.objects.filter(last_error='OSError').exists())
    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('book'), data(self.day)).status_code, 403)
    def test_csrf_valid_same_origin_form_and_referrer_policy(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse('book'))
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        token = client.cookies['csrftoken'].value
        response = client.post(reverse('book'), {**data(self.day), 'csrfmiddlewaretoken': token}, HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 302)
    def test_search_terms_do_not_enter_urls(self):
        self.book()
        self.client.force_login(self.user)
        response = self.client.post(reverse('doctor-patients'), {'q': 'Test Patient'})
        self.assertEqual(response.url, reverse('doctor-patients'))
        self.assertContains(self.client.get(response.url), 'Test Patient')
    def test_public_pages_and_sitemap(self):
        for path in ['/', '/about/', '/services/', '/contact/', '/privacy/', '/book/', '/doctor/login/', '/robots.txt', '/sitemap.xml', '/health/']:
            self.assertEqual(self.client.get(path).status_code, 200, path)
    def test_contact_form_and_inbox(self):
        response = self.client.post('/contact/', {'name': 'Visitor', 'phone': '+919876543210', 'email': 'visitor@example.com', 'message': 'Opening hours?'})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/doctor/messages/'), 'Opening hours?')
    def test_honeypot_and_rate_limit(self):
        self.assertFalse(BookingForm(data(self.day, website='spam')).is_valid())
        for _ in range(11):
            response = self.client.post('/doctor/login/', {'username':'invalid', 'password':'invalid'})
        self.assertEqual(response.status_code, 429)
    def test_admin_status_uses_notifications_and_validation(self):
        appointment, _ = self.book()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse('admin:clinic_appointment_change', args=[appointment.pk])
        response = self.client.post(url, {'status':'CONFIRMED', '_save':'Save'})
        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'CONFIRMED')
        self.assertEqual(EmailNotification.objects.count(), 3)
        response = self.client.post(url, {'status':'NO_SHOW', '_save':'Save'})
        self.assertContains(response, 'only after its start time')
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'CONFIRMED')
    def test_admin_schedule_edit_protects_existing_bookings(self):
        self.book()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        period = self.doctor.schedules.first()
        response = self.client.post(reverse('admin:clinic_doctorschedule_change', args=[period.pk]), {'day_of_week':period.day_of_week,'start_time':'10:00','end_time':'13:00','slot_duration':20,'is_active':'on','_save':'Save'})
        self.assertContains(response, 'would affect existing appointments')
        period.refresh_from_db()
        self.assertEqual(period.slot_duration, 30)
    def test_doctor_can_add_edit_and_remove_schedule(self):
        self.client.force_login(self.user)
        weekday = (self.day.weekday()+1)%7
        response = self.client.post(reverse('doctor-schedule'), {'day_of_week':weekday,'start_time':'09:00','end_time':'11:00','slot_duration':20,'is_active':'on'})
        self.assertEqual(response.status_code, 302)
        period = self.doctor.schedules.get(day_of_week=weekday)
        response = self.client.post(reverse('doctor-schedule-edit',args=[period.pk]), {'day_of_week':weekday,'start_time':'09:00','end_time':'12:00','slot_duration':30,'is_active':'on'})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('doctor-schedule-delete',args=[period.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.doctor.schedules.filter(pk=period.pk).exists())
    def test_doctor_can_add_and_remove_leave(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('doctor-leave'), {'date':self.day,'reason':'Holiday'})
        self.assertEqual(response.status_code, 302)
        leave = self.doctor.leaves.get()
        self.assertEqual(available_slots(self.doctor, self.day), [])
        self.client.post(reverse('doctor-leave-delete',args=[leave.pk]))
        self.assertTrue(available_slots(self.doctor, self.day))
    def test_complete_and_no_show_after_start(self):
        for index, status in enumerate(['COMPLETED','NO_SHOW']):
            appointment, _ = self.book(at=time(10,index*30))
            appointment = change_status(appointment, 'CONFIRMED')
            with patch('clinic.services.timezone.now', return_value=timezone.now()+timedelta(days=3)):
                result = change_status(appointment,status)
            self.assertEqual(result.status,status)

class ConcurrentBookingTests(TransactionTestCase):
    def setUp(self):
        self.user, self.doctor, self.day = fixture()
    def test_two_concurrent_requests_only_one_wins(self):
        barrier = Barrier(2)
        doctor_id = self.doctor.pk
        day = self.day
        def attempt(name):
            close_old_connections()
            try:
                doctor = Doctor.objects.get(pk=doctor_id)
                barrier.wait(timeout=10)
                book_appointment(doctor, data(day, name=name))
                return 'booked'
            except ValidationError:
                return 'unavailable'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, ['First', 'Second']))
        self.assertCountEqual(results, ['booked', 'unavailable'])
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Patient.objects.count(), 1)
