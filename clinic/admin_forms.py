from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance
from django.utils import timezone
from .models import Appointment, DoctorSchedule, DoctorLeave
from .services import ACTIVE, validate_schedule_change, validate_status_change

class AdminAppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['status']
    def clean_status(self):
        status = self.cleaned_data['status']
        validate_status_change(Appointment.objects.get(pk=self.instance.pk), status)
        return status

class AdminScheduleForm(forms.ModelForm):
    class Meta:
        model = DoctorSchedule
        fields = '__all__'
    def clean(self):
        cleaned = super().clean()
        if not self.errors:
            period = construct_instance(self, self.instance, self._meta.fields, self._meta.exclude)
            if period.doctor_id:
                validate_schedule_change(period)
        return cleaned

class AdminLeaveForm(forms.ModelForm):
    class Meta:
        model = DoctorLeave
        fields = '__all__'
    def clean(self):
        cleaned = super().clean()
        doctor = cleaned.get('doctor') or getattr(self.instance, 'doctor', None)
        day = cleaned.get('date')
        if day and day < timezone.localdate():
            raise ValidationError('Choose today or a future date.')
        if doctor and day and Appointment.objects.filter(doctor=doctor, appointment_date=day, status__in=ACTIVE).exists():
            raise ValidationError('Cancel the existing appointments first so the patients are notified.')
        return cleaned
