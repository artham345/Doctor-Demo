import re
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from .models import Patient, DoctorSchedule, DoctorLeave, Doctor, Service, ContactMessage

class StyledForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3

class PhoneMixin:
    def clean_phone(self):
        value = re.sub(r'[\s()\-]', '', self.cleaned_data['phone'])
        if not re.fullmatch(r'\+?[0-9]{8,15}', value):
            raise ValidationError('Enter 8–15 digits, including your country code when needed.')
        return value

class BookingForm(StyledForm, PhoneMixin, forms.Form):
    appointment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Appointment date')
    appointment_time = forms.TimeField(widget=forms.HiddenInput())
    name = forms.CharField(max_length=120, label='Full name', widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    phone = forms.CharField(max_length=30, label='Phone number', widget=forms.TextInput(attrs={'type': 'tel', 'autocomplete': 'tel'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    age = forms.IntegerField(required=False, min_value=0, max_value=120)
    gender = forms.ChoiceField(choices=Patient._meta.get_field('gender').choices, required=False)
    reason = forms.CharField(max_length=300, required=False, label='Reason for visit')
    message = forms.CharField(max_length=1500, required=False, label='Additional message', widget=forms.Textarea)
    consent = forms.BooleanField(label='I agree to the clinic using these details to arrange and manage my appointment.')
    website = forms.CharField(required=False, widget=forms.HiddenInput())
    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise ValidationError('Unable to accept this booking.')
        return ''

class ScheduleForm(StyledForm, forms.ModelForm):
    class Meta:
        model = DoctorSchedule
        fields = ['day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_active']
        widgets = {'start_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}), 'end_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'})}

class LeaveForm(StyledForm, forms.ModelForm):
    class Meta:
        model = DoctorLeave
        fields = ['date', 'reason']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

class ServiceForm(StyledForm, forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'description', 'icon', 'is_active']

class ProfileForm(StyledForm, PhoneMixin, forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ['name', 'specialization', 'biography', 'qualifications', 'education', 'certifications', 'expertise', 'experience', 'phone', 'email', 'clinic_name', 'clinic_address', 'profile_image', 'website_link', 'instagram_link']
    def clean_profile_image(self):
        photo = self.cleaned_data.get('profile_image')
        if photo and hasattr(photo, 'content_type'):
            if not settings.DEBUG and not settings.USE_S3:
                raise ValidationError('Photo uploads need durable media storage. Ask your website administrator to enable it.')
            if photo.size > 5 * 1024 * 1024 or photo.content_type not in ['image/jpeg', 'image/png', 'image/webp']:
                raise ValidationError('Use a JPEG, PNG, or WebP image under 5 MB.')
            if photo.image.width > 6000 or photo.image.height > 6000:
                raise ValidationError('Image dimensions must be 6000 pixels or less.')
        return photo

class ContactForm(StyledForm, PhoneMixin, forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput())
    class Meta:
        model = ContactMessage
        fields = ['name', 'phone', 'email', 'message']
    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise ValidationError('Unable to accept this message.')
        return ''
