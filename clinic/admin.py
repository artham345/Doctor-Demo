from django.contrib import admin
from django.db import transaction
from .admin_forms import AdminAppointmentForm, AdminScheduleForm, AdminLeaveForm
from .services import change_status, save_schedule, add_leave, remove_leave
from .models import Doctor, Patient, Appointment, Service, DoctorSchedule, DoctorLeave, ContactMessage

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['name', 'clinic_name', 'specialization', 'is_public', 'is_demo']
    search_fields = ['name', 'clinic_name']
    list_filter = ['is_public', 'is_demo']
    fieldsets = [('Account', {'fields': ['user', 'is_public', 'is_demo']}), ('Profile', {'fields': ['name', 'specialization', 'biography', 'qualifications', 'education', 'certifications', 'expertise', 'experience']}), ('Clinic', {'fields': ['clinic_name', 'clinic_address', 'phone', 'email', 'website_link', 'instagram_link']})]
    # All image uploads pass through the portal's image validation.

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'doctor', 'is_active']
    list_filter = ['is_active', 'doctor']
    search_fields = ['name']

class LockedDoctorAdmin(admin.ModelAdmin):
    """Keep admin validation and persistence under the same lock as public booking."""
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method != 'POST':
            return super().changeform_view(request, object_id, form_url, extra_context)
        with transaction.atomic():
            obj = self.get_object(request, object_id) if object_id else None
            doctor_id = obj.doctor_id if obj else request.POST.get('doctor')
            if doctor_id and str(doctor_id).isdigit():
                Doctor.objects.select_for_update().filter(pk=doctor_id).first()
            return super().changeform_view(request, object_id, form_url, extra_context)
    def get_readonly_fields(self, request, obj=None):
        return ['doctor'] if obj else []
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Appointment)
class AppointmentAdmin(LockedDoctorAdmin):
    form = AdminAppointmentForm
    list_display = ['booking_id', 'doctor', 'patient', 'appointment_date', 'appointment_time', 'status']
    search_fields = ['booking_id', 'patient__name', 'patient__phone']
    list_filter = ['status', 'appointment_date', 'doctor']
    ordering = ['-appointment_date', 'appointment_time']
    exclude = ['token_digest']
    def get_readonly_fields(self, request, obj=None):
        return ['booking_id', 'doctor', 'patient', 'appointment_date', 'appointment_time', 'duration', 'reason', 'message', 'created_at', 'updated_at']
    def has_add_permission(self, request):
        return False
    def save_model(self, request, obj, form, change):
        change_status(obj, obj.status)

@admin.register(Patient)
class PatientAdmin(LockedDoctorAdmin):
    list_display = ['name', 'doctor', 'phone', 'created_at']
    search_fields = ['name', 'phone']
    list_filter = ['doctor']
    ordering = ['name']
    def has_add_permission(self, request):
        return False
    def get_readonly_fields(self, request, obj=None):
        return ['doctor', 'created_at', 'updated_at']

@admin.register(DoctorSchedule)
class ScheduleAdmin(LockedDoctorAdmin):
    form = AdminScheduleForm
    list_display = ['doctor', 'day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_active']
    list_filter = ['doctor', 'day_of_week', 'is_active']
    search_fields = ['doctor__name']
    def save_model(self, request, obj, form, change):
        save_schedule(obj)

@admin.register(DoctorLeave)
class LeaveAdmin(LockedDoctorAdmin):
    form = AdminLeaveForm
    list_display = ['doctor', 'date', 'reason']
    list_filter = ['doctor', 'date']
    search_fields = ['reason', 'doctor__name']
    def save_model(self, request, obj, form, change):
        add_leave(obj)
    def has_delete_permission(self, request, obj=None):
        return admin.ModelAdmin.has_delete_permission(self, request, obj)
    def delete_model(self, request, obj):
        remove_leave(obj)
    def delete_queryset(self, request, queryset):
        for obj in queryset.order_by('doctor_id', 'pk'):
            remove_leave(obj)

@admin.register(ContactMessage)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at', 'is_read']
    list_filter = ['is_read']
    search_fields = ['name', 'email']
    readonly_fields = ['doctor', 'name', 'phone', 'email', 'message', 'created_at']
    def has_add_permission(self, request):
        return False

admin.site.site_header = 'Clinic administration'
admin.site.site_title = 'Clinic admin'
admin.site.index_title = 'Website configuration · manage appointments and availability in the doctor portal'
