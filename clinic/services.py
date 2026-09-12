"""All appointment and availability writes acquire the doctor's row lock first."""
import hashlib
import secrets
from datetime import datetime, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from .models import Appointment, Doctor, DoctorLeave, DoctorSchedule, Patient

SLOT_TAKEN = 'Sorry, this appointment slot was just booked. Please choose another time.'
ACTIVE = [Appointment.Status.PENDING, Appointment.Status.CONFIRMED]

def slot_datetime(day, time):
    return timezone.make_aware(datetime.combine(day, time))

def generated_slots(doctor, day):
    today = timezone.localdate()
    if not today <= day <= today + timedelta(days=settings.BOOKING_WINDOW_DAYS):
        return []
    if DoctorLeave.objects.filter(doctor=doctor, date=day).exists():
        return []
    slots = []
    for period in DoctorSchedule.objects.filter(doctor=doctor, day_of_week=day.weekday(), is_active=True):
        cursor = slot_datetime(day, period.start_time)
        end = slot_datetime(day, period.end_time)
        step = timedelta(minutes=period.slot_duration)
        while cursor + step <= end:
            if cursor > timezone.now():
                slots.append((cursor.time(), period.slot_duration))
            cursor += step
    return sorted(set(slots))

def available_slots(doctor, day):
    occupied = list(Appointment.objects.filter(doctor=doctor, appointment_date=day).exclude(status=Appointment.Status.CANCELLED))
    result = []
    for start, duration in generated_slots(doctor, day):
        begin = slot_datetime(day, start)
        end = begin + timedelta(minutes=duration)
        if not any(begin < slot_datetime(day, a.appointment_time) + timedelta(minutes=a.duration) and end > slot_datetime(day, a.appointment_time) for a in occupied):
            result.append((start, duration))
    return result

def book_appointment(doctor, data):
    token = secrets.token_urlsafe(32)
    try:
        with transaction.atomic():
            doctor = Doctor.objects.select_for_update().get(pk=doctor.pk)
            slots = dict(available_slots(doctor, data['appointment_date']))
            duration = slots.get(data['appointment_time'])
            if duration is None:
                raise ValidationError(SLOT_TAKEN)
            # Unauthenticated callers must never overwrite an existing patient's identity.
            # Exact demographic matches can share history; otherwise create a new record.
            fields = {k: data.get(k) for k in ('name', 'phone', 'email', 'age', 'gender')}
            patient = Patient.objects.filter(doctor=doctor, **fields).first()
            if patient is None:
                patient = Patient(doctor=doctor, **fields)
                patient.full_clean()
                patient.save()
            appointment = Appointment(doctor=doctor, patient=patient, appointment_date=data['appointment_date'], appointment_time=data['appointment_time'], duration=duration, reason=data.get('reason', ''), message=data.get('message', ''), token_digest=hashlib.sha256(token.encode()).hexdigest())
            appointment.save()
            from notifications.services import queue_appointment_email
            queue_appointment_email(appointment, 'received', token)
            queue_appointment_email(appointment, 'new', recipient=doctor.email)
    except IntegrityError as exc:
        raise ValidationError(SLOT_TAKEN) from exc
    return appointment, token

def validate_status_change(appointment, status, patient_request=False):
    allowed = {'PENDING': ['CONFIRMED', 'CANCELLED'], 'CONFIRMED': ['COMPLETED', 'CANCELLED', 'NO_SHOW']}
    if status == appointment.status:
        return
    if patient_request and (status != 'CANCELLED' or slot_datetime(appointment.appointment_date, appointment.appointment_time) <= timezone.now()):
        raise ValidationError('Online cancellation is available before your appointment. Please call the clinic.')
    if status not in allowed.get(appointment.status, []):
        raise ValidationError('This status change is not allowed.')
    if status in ['COMPLETED', 'NO_SHOW'] and slot_datetime(appointment.appointment_date, appointment.appointment_time) > timezone.now():
        raise ValidationError('An appointment can be completed or marked no show only after its start time.')

@transaction.atomic
def change_status(appointment, status, patient_request=False):
    Doctor.objects.select_for_update().get(pk=appointment.doctor_id)
    appointment = Appointment.objects.select_for_update().select_related('patient', 'doctor').get(pk=appointment.pk)
    validate_status_change(appointment, status, patient_request)
    if appointment.status == status:
        return appointment
    appointment.status = status
    appointment.save(update_fields=['status', 'updated_at'])
    if status in ['CONFIRMED', 'CANCELLED']:
        from notifications.services import queue_appointment_email
        queue_appointment_email(appointment, status.lower())
    return appointment

def validate_schedule_change(period, delete=False):
    old = DoctorSchedule.objects.filter(pk=period.pk).first() if period.pk else None
    proposed = list(DoctorSchedule.objects.filter(doctor_id=period.doctor_id, is_active=True).exclude(pk=period.pk))
    if not delete and period.is_active:
        proposed.append(period)
    weekdays = {period.day_of_week}
    if old:
        weekdays.add(old.day_of_week)
    upcoming = Appointment.objects.filter(doctor_id=period.doctor_id, appointment_date__gte=timezone.localdate(), status__in=ACTIVE)
    for appointment in upcoming:
        if appointment.appointment_date.weekday() not in weekdays:
            continue
        if slot_datetime(appointment.appointment_date, appointment.appointment_time) <= timezone.now():
            continue
        start = slot_datetime(appointment.appointment_date, appointment.appointment_time)
        end = start + timedelta(minutes=appointment.duration)
        fits = any(
            candidate.day_of_week == appointment.appointment_date.weekday()
            and candidate.slot_duration == appointment.duration
            and slot_datetime(appointment.appointment_date, candidate.start_time) <= start
            and end <= slot_datetime(appointment.appointment_date, candidate.end_time)
            and (start - slot_datetime(appointment.appointment_date, candidate.start_time)).total_seconds() % (candidate.slot_duration * 60) == 0
            for candidate in proposed
        )
        if not fits:
            raise ValidationError('This change would affect existing appointments. Cancel the affected appointments first, then update the schedule.')

@transaction.atomic
def save_schedule(period, delete=False):
    Doctor.objects.select_for_update().get(pk=period.doctor_id)
    if not delete:
        period.full_clean()
    validate_schedule_change(period, delete)
    if delete:
        period.delete()
    else:
        period.save()
    return period

@transaction.atomic
def add_leave(leave):
    Doctor.objects.select_for_update().get(pk=leave.doctor_id)
    if leave.date < timezone.localdate():
        raise ValidationError('Choose today or a future date.')
    if Appointment.objects.filter(doctor=leave.doctor, appointment_date=leave.date, status__in=ACTIVE).exists():
        raise ValidationError('There are appointments on this date. Cancel them first so patients receive a notification.')
    leave.full_clean()
    leave.save()
    return leave

@transaction.atomic
def remove_leave(leave):
    Doctor.objects.select_for_update().get(pk=leave.doctor_id)
    leave.delete()
