import secrets
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q, F

phone_validator = RegexValidator(r'^\+?[0-9]{8,15}$', 'Enter 8–15 digits, optionally starting with + (country code).')

def photo_path(instance, filename):
    return f'doctors/{uuid.uuid4().hex}{__import__("pathlib").Path(filename).suffix.lower()}'

class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Doctor(Timestamped):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='doctor')
    name = models.CharField(max_length=120)
    specialization = models.CharField(max_length=160)
    biography = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)
    education = models.TextField(blank=True)
    certifications = models.TextField(blank=True)
    expertise = models.TextField(blank=True)
    experience = models.PositiveSmallIntegerField(default=0)
    phone = models.CharField(max_length=16, validators=[phone_validator])
    email = models.EmailField()
    clinic_name = models.CharField(max_length=160)
    clinic_address = models.TextField()
    profile_image = models.ImageField(upload_to=photo_path, blank=True)
    website_link = models.URLField(blank=True)
    instagram_link = models.URLField(blank=True)
    is_public = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['is_public'], condition=Q(is_public=True), name='one_public_doctor')]
    def __str__(self):
        return self.name

class Service(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=120)
    description = models.TextField(max_length=1500)
    icon = models.CharField(max_length=20, choices=[('heart', 'Heart'), ('pulse', 'Pulse'), ('shield', 'Shield'), ('plus', 'Medical cross')], default='heart')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['id']
    def __str__(self):
        return self.name

class Patient(Timestamped):
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name='patients')
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=16, validators=[phone_validator], db_index=True)
    email = models.EmailField(blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(120)])
    gender = models.CharField(max_length=20, choices=[('', 'Prefer not to say'), ('female', 'Female'), ('male', 'Male'), ('other', 'Other')], blank=True)
    class Meta:
        ordering = ['name', 'id']
        indexes = [models.Index(fields=['doctor', 'name'])]
    def __str__(self):
        return self.name

class DoctorSchedule(models.Model):
    DAYS = list(enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']))
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(5), MaxValueValidator(180)])
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ['day_of_week', 'start_time']
        constraints = [models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='schedule_positive_period'), models.CheckConstraint(condition=Q(slot_duration__gte=5, slot_duration__lte=180, day_of_week__lte=6), name='schedule_valid_values')]
    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError('End time must be after start time.')
        if self.doctor_id and self.is_active and self.start_time and self.end_time:
            overlaps = DoctorSchedule.objects.filter(doctor_id=self.doctor_id, day_of_week=self.day_of_week, is_active=True, start_time__lt=self.end_time, end_time__gt=self.start_time).exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError('Working periods cannot overlap. Leave a gap between periods for breaks.')
    def __str__(self):
        return f'{self.get_day_of_week_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}'

class DoctorLeave(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='leaves')
    date = models.DateField()
    reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-date']
        constraints = [models.UniqueConstraint(fields=['doctor', 'date'], name='unique_doctor_leave')]
    def __str__(self):
        return str(self.date)

class Appointment(Timestamped):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        NO_SHOW = 'NO_SHOW', 'No show'
    booking_id = models.CharField(max_length=30, unique=True, editable=False)
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name='appointments')
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='appointments')
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    duration = models.PositiveSmallIntegerField(default=30)
    reason = models.CharField(max_length=300, blank=True)
    message = models.TextField(max_length=1500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    token_digest = models.CharField(max_length=64, editable=False)
    class Meta:
        ordering = ['appointment_date', 'appointment_time', 'id']
        constraints = [models.UniqueConstraint(fields=['doctor', 'appointment_date', 'appointment_time'], condition=~Q(status='CANCELLED'), name='unique_occupied_doctor_slot'), models.CheckConstraint(condition=Q(status__in=['PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW']), name='valid_appointment_status')]
        indexes = [models.Index(fields=['doctor', 'appointment_date', 'status'])]
    def save(self, *args, **kwargs):
        if not self.booking_id:
            self.booking_id = f'APT-{self.appointment_date.year}-{secrets.token_hex(5).upper()}'
        super().save(*args, **kwargs)
    def __str__(self):
        return self.booking_id

class ContactMessage(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='contact_messages')
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=16, validators=[phone_validator])
    email = models.EmailField()
    message = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    class Meta:
        ordering = ['-created_at']

class RateLimit(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
