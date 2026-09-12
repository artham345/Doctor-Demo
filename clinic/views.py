import calendar as cal
import hashlib
import hmac
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from .forms import BookingForm, ContactForm, LeaveForm, ProfileForm, ScheduleForm, ServiceForm
from .models import Appointment, ContactMessage, Doctor, DoctorLeave, DoctorSchedule, Patient, Service
from .security import allowed_request, doctor_required
from .services import ACTIVE, add_leave, available_slots, book_appointment, change_status, remove_leave, save_schedule, slot_datetime

def public_doctor():
    return get_object_or_404(Doctor, is_public=True)

def public_page(request, page='home'):
    doctor = public_doctor()
    return render(request, f'public/{page}.html', {'services': doctor.services.filter(is_active=True), 'periods': doctor.schedules.filter(is_active=True), 'page_title': {'home': 'Thoughtful care. A healthier tomorrow.', 'about': 'Meet your doctor', 'services': 'Care for every stage of life', 'privacy': 'Your privacy'}[page]})

def contact(request):
    doctor = public_doctor()
    form = ContactForm(request.POST or None)
    if request.method == 'POST':
        if not allowed_request(request, 'contact', 5):
            form.add_error(None, 'Too many messages. Please try again in 10 minutes or call the clinic.')
        elif form.is_valid():
            item = form.save(commit=False)
            item.doctor = doctor
            item.save()
            messages.success(request, 'Your message has been sent. The clinic will contact you soon.')
            return redirect('contact')
    return render(request, 'public/contact.html', {'form': form, 'periods': doctor.schedules.filter(is_active=True), 'page_title': 'Let’s talk about your care'})

def booking(request):
    doctor = public_doctor()
    form = BookingForm(request.POST or None)
    if request.method == 'POST':
        if not allowed_request(request, 'booking', 10):
            form.add_error(None, 'Too many booking attempts. Please try again in 10 minutes or call the clinic.')
        elif form.is_valid():
            try:
                appointment, token = book_appointment(doctor, form.cleaned_data)
                return redirect('booking-manage', booking_id=appointment.booking_id, token=token)
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(request, 'appointments/book.html', {'form': form, 'today': timezone.localdate().isoformat(), 'last_date': (timezone.localdate() + timedelta(days=settings.BOOKING_WINDOW_DAYS)).isoformat(), 'page_title': 'Make time for your health'})

@require_GET
def availability(request):
    doctor = public_doctor()
    try:
        day = date.fromisoformat(request.GET.get('date', ''))
    except ValueError:
        return JsonResponse({'error': 'Choose a valid date.'}, status=400)
    slots = available_slots(doctor, day)
    response = JsonResponse({'date': day.isoformat(), 'timezone': settings.TIME_ZONE, 'slots': [{'time': start.strftime('%H:%M'), 'label': start.strftime('%I:%M %p').lstrip('0'), 'duration': duration} for start, duration in slots]})
    response['Cache-Control'] = 'no-store'
    return response

def private_booking(booking_id, token):
    item = get_object_or_404(Appointment.objects.select_related('doctor', 'patient'), booking_id=booking_id)
    if not hmac.compare_digest(item.token_digest, hashlib.sha256(token.encode()).hexdigest()):
        raise Http404
    return item

@require_http_methods(['GET', 'POST'])
def booking_manage(request, booking_id, token):
    appointment = private_booking(booking_id, token)
    if request.method == 'POST':
        try:
            appointment = change_status(appointment, 'CANCELLED', patient_request=True)
            messages.success(request, 'Your appointment has been cancelled.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        return redirect('booking-manage', booking_id=booking_id, token=token)
    can_cancel = appointment.status in ACTIVE and slot_datetime(appointment.appointment_date, appointment.appointment_time) > timezone.now()
    return render(request, 'appointments/confirmation.html', {'appointment': appointment, 'token': token, 'can_cancel': can_cancel, 'page_title': 'Your appointment'})

@require_GET
def calendar_download(request, booking_id, token):
    appointment = private_booking(booking_id, token)
    if appointment.status == 'CANCELLED':
        raise Http404
    from datetime import timezone as dt_timezone
    start = slot_datetime(appointment.appointment_date, appointment.appointment_time).astimezone(dt_timezone.utc)
    end = start + timedelta(minutes=appointment.duration)
    def escape(value):
        return value.replace('\\', '\\\\').replace('\r', '').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Clinic//Appointments//EN', 'BEGIN:VEVENT', f'UID:{appointment.booking_id}@clinic', f'DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}', f'DTSTART:{start:%Y%m%dT%H%M%SZ}', f'DTEND:{end:%Y%m%dT%H%M%SZ}', f'SUMMARY:{escape("Appointment with " + appointment.doctor.name)}', f'LOCATION:{escape(appointment.doctor.clinic_address)}', 'END:VEVENT', 'END:VCALENDAR']
    # Fold on UTF-8 byte boundaries, per RFC 5545.
    folded = []
    for line in lines:
        current = ''
        for char in line:
            if len((current + char).encode()) > 73:
                folded.append(current)
                current = ' '
            current += char
        folded.append(current)
    response = HttpResponse('\r\n'.join(folded) + '\r\n', content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="clinic-appointment.ics"'
    return response

class DoctorLoginView(LoginView):
    template_name = 'doctor/login.html'
    redirect_authenticated_user = False
    def post(self, request, *args, **kwargs):
        if not allowed_request(request, 'login', 10):
            return render(request, self.template_name, {'form': self.get_form(), 'locked': True}, status=429)
        return super().post(request, *args, **kwargs)
    def form_valid(self, form):
        if not hasattr(form.get_user(), 'doctor'):
            form.add_error(None, 'This account does not have access to the doctor portal.')
            return self.form_invalid(form)
        return super().form_valid(form)

@doctor_required
def dashboard(request):
    appointments = request.doctor.appointments.all()
    today = timezone.localdate()
    counts = dict(appointments.values('status').annotate(total=Count('id')).values_list('status', 'total'))
    return render(request, 'doctor/dashboard.html', {'page_title': 'Your practice at a glance', 'today': today, 'today_count': appointments.filter(appointment_date=today).exclude(status='CANCELLED').count(), 'upcoming_count': appointments.filter(appointment_date__gte=today, status__in=ACTIVE).count(), 'pending_count': counts.get('PENDING', 0), 'completed_count': counts.get('COMPLETED', 0), 'cancelled_count': counts.get('CANCELLED', 0), 'appointments': appointments.filter(appointment_date=today).select_related('patient'), 'unread_count': request.doctor.contact_messages.filter(is_read=False).count()})

@doctor_required
def appointments(request):
    items = request.doctor.appointments.select_related('patient').order_by('-appointment_date', 'appointment_time')
    if request.method == 'POST':
        request.session['appointment_search'] = request.POST.get('q', '').strip()[:120]
        return redirect(reverse('doctor-appointments') + '?' + urlencode({'status': request.POST.get('status', ''), 'date': request.POST.get('date', '')}))
    if request.GET.get('clear'):
        request.session.pop('appointment_search', None)
    search = request.session.get('appointment_search', '')
    status = request.GET.get('status', '')
    selected_date = request.GET.get('date', '')
    if search:
        items = items.filter(Q(patient__name__icontains=search) | Q(booking_id__icontains=search))
    if status in Appointment.Status.values:
        items = items.filter(status=status)
    if selected_date:
        try:
            items = items.filter(appointment_date=date.fromisoformat(selected_date))
        except ValueError:
            messages.error(request, 'Enter a valid filter date.')
    return render(request, 'doctor/appointments.html', {'page_title': 'Appointments', 'search': search, 'page_obj': Paginator(items, 15).get_page(request.GET.get('page')), 'statuses': Appointment.Status.choices, 'query_string': urlencode({'status': status, 'date': selected_date})})

@doctor_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(request.doctor.appointments.select_related('patient'), pk=pk)
    return render(request, 'doctor/appointment_detail.html', {'page_title': appointment.booking_id, 'appointment': appointment})

@doctor_required
@require_POST
def appointment_status(request, pk):
    appointment = get_object_or_404(request.doctor.appointments, pk=pk)
    try:
        change_status(appointment, request.POST.get('status'))
        messages.success(request, 'Appointment updated.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('doctor-appointment', pk=pk)

@doctor_required
def patients(request):
    items = request.doctor.patients.annotate(visit_count=Count('appointments')).order_by('name', 'pk')
    if request.method == 'POST':
        request.session['patient_search'] = request.POST.get('q', '').strip()[:120]
        return redirect('doctor-patients')
    if request.GET.get('clear'):
        request.session.pop('patient_search', None)
    q = request.session.get('patient_search', '')
    if q:
        items = items.filter(Q(name__icontains=q) | Q(phone__icontains=q))
    return render(request, 'doctor/patients.html', {'page_title': 'Patients', 'search': q, 'page_obj': Paginator(items, 15).get_page(request.GET.get('page')), 'query_string': ''})

@doctor_required
def patient_detail(request, pk):
    patient = get_object_or_404(request.doctor.patients, pk=pk)
    return render(request, 'doctor/patient_detail.html', {'page_title': patient.name, 'patient': patient, 'appointments': patient.appointments.filter(doctor=request.doctor).order_by('-appointment_date')})

@doctor_required
def schedule(request, pk=None):
    instance = get_object_or_404(request.doctor.schedules, pk=pk) if pk else DoctorSchedule(doctor=request.doctor)
    form = ScheduleForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        try:
            save_schedule(form.save(commit=False))
            messages.success(request, 'Working period saved.')
            return redirect('doctor-schedule')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'doctor/schedule.html', {'page_title': 'Working schedule', 'form': form, 'periods': request.doctor.schedules.all(), 'editing': bool(pk)})

@doctor_required
@require_POST
def schedule_delete(request, pk):
    period = get_object_or_404(request.doctor.schedules, pk=pk)
    try:
        save_schedule(period, delete=True)
        messages.success(request, 'Working period deleted.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('doctor-schedule')

@doctor_required
def leave(request):
    form = LeaveForm(request.POST or None, instance=DoctorLeave(doctor=request.doctor))
    if request.method == 'POST' and form.is_valid():
        try:
            add_leave(form.save(commit=False))
            messages.success(request, 'Leave added. This date is now closed for bookings.')
            return redirect('doctor-leave')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'doctor/leave.html', {'page_title': 'Leave & holidays', 'form': form, 'upcoming': request.doctor.leaves.filter(date__gte=timezone.localdate()), 'past': request.doctor.leaves.filter(date__lt=timezone.localdate())})

@doctor_required
@require_POST
def leave_delete(request, pk):
    remove_leave(get_object_or_404(request.doctor.leaves, pk=pk))
    messages.success(request, 'Leave removed.')
    return redirect('doctor-leave')

@doctor_required
def doctor_services(request, pk=None):
    instance = get_object_or_404(request.doctor.services, pk=pk) if pk else Service(doctor=request.doctor)
    form = ServiceForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Service saved.')
        return redirect('doctor-services')
    return render(request, 'doctor/services.html', {'page_title': 'Your services', 'form': form, 'services': request.doctor.services.all(), 'editing': bool(pk)})

@doctor_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.doctor)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your profile has been updated.')
        return redirect('doctor-profile')
    return render(request, 'doctor/profile.html', {'page_title': 'Your profile', 'form': form})

@doctor_required
def calendar(request):
    try:
        anchor = date.fromisoformat(request.GET.get('date', timezone.localdate().isoformat()))
        if not 1901 <= anchor.year <= 2099:
            raise ValueError
    except ValueError:
        anchor = timezone.localdate()
    mode = request.GET.get('view', 'month')
    if mode == 'day':
        start, end = anchor, anchor
        previous, following = anchor - timedelta(days=1), anchor + timedelta(days=1)
    elif mode == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        previous, following = anchor - timedelta(days=7), anchor + timedelta(days=7)
    else:
        mode = 'month'
        first = anchor.replace(day=1)
        last = anchor.replace(day=cal.monthrange(anchor.year, anchor.month)[1])
        start = first - timedelta(days=first.weekday())
        end = last + timedelta(days=6-last.weekday())
        previous, following = first - timedelta(days=1), last + timedelta(days=1)
    by_day = {}
    for item in request.doctor.appointments.filter(appointment_date__range=(start, end)).select_related('patient'):
        by_day.setdefault(item.appointment_date, []).append(item)
    days = [{'date': start + timedelta(days=i), 'items': by_day.get(start + timedelta(days=i), []), 'outside': (start + timedelta(days=i)).month != anchor.month} for i in range((end-start).days+1)]
    return render(request, 'doctor/calendar.html', {'page_title': 'Appointment calendar', 'anchor': anchor, 'mode': mode, 'days': days, 'previous': previous, 'following': following, 'today': timezone.localdate()})

@doctor_required
def inbox(request):
    if request.method == 'POST':
        message = get_object_or_404(request.doctor.contact_messages, pk=request.POST.get('message_id'))
        message.is_read = True
        message.save(update_fields=['is_read'])
        return redirect('doctor-inbox')
    return render(request, 'doctor/inbox.html', {'page_title': 'Clinic messages', 'page_obj': Paginator(request.doctor.contact_messages.all(), 15).get_page(request.GET.get('page'))})

def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})

def robots(request):
    return HttpResponse(f'User-agent: *\nDisallow: /doctor/\nDisallow: /booking/\nDisallow: /admin/\nSitemap: {settings.SITE_URL}/sitemap.xml\n', content_type='text/plain')

def error403(request, exception=None):
    return render(request, 'errors/error.html', {'code': 403, 'heading': 'This page is private', 'explanation': 'Please sign in with an authorized account.'}, status=403)

def csrf_failure(request, reason=''):
    return render(request, 'errors/error.html', {'code': 403, 'heading': 'Please refresh and try again', 'explanation': 'Your form could not be verified. Refresh the page before submitting again.'}, status=403)

def error404(request, exception=None):
    return render(request, 'errors/error.html', {'code': 404, 'heading': 'We couldn’t find that page', 'explanation': 'The link may have changed or is no longer available.'}, status=404)

def error500(request):
    # No database-dependent base template: safe even when the database is unavailable.
    from django.template.loader import render_to_string
    return HttpResponse(render_to_string('errors/500.html'), status=500)
