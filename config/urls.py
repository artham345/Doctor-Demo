from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import path, reverse
from clinic import views as v
from clinic.security import doctor_required
from notifications.views import retry_emails

class PublicSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.8
    protocol = 'https'
    def items(self):
        return ['home', 'about', 'services', 'contact', 'book']
    def location(self, item):
        return reverse(item)

urlpatterns = [
    path('internal/retry-emails/', retry_emails, name='retry-emails'),
    path('', v.public_page, name='home'),
    path('about/', v.public_page, {'page': 'about'}, name='about'),
    path('services/', v.public_page, {'page': 'services'}, name='services'),
    path('privacy/', v.public_page, {'page': 'privacy'}, name='privacy'),
    path('contact/', v.contact, name='contact'),
    path('book/', v.booking, name='book'),
    path('availability/', v.availability, name='availability'),
    path('booking/<str:booking_id>/<str:token>/', v.booking_manage, name='booking-manage'),
    path('booking/<str:booking_id>/<str:token>/calendar/', v.calendar_download, name='booking-calendar'),
    path('doctor/login/', v.DoctorLoginView.as_view(), name='doctor-login'),
    path('doctor/logout/', auth.LogoutView.as_view(), name='doctor-logout'),
    path('doctor/password/', doctor_required(auth.PasswordChangeView.as_view(template_name='doctor/password.html', success_url='/doctor/dashboard/')), name='doctor-password'),
    path('doctor/dashboard/', v.dashboard, name='doctor-dashboard'),
    path('doctor/appointments/', v.appointments, name='doctor-appointments'),
    path('doctor/appointments/<int:pk>/', v.appointment_detail, name='doctor-appointment'),
    path('doctor/appointments/<int:pk>/status/', v.appointment_status, name='doctor-appointment-status'),
    path('doctor/patients/', v.patients, name='doctor-patients'),
    path('doctor/patients/<int:pk>/', v.patient_detail, name='doctor-patient'),
    path('doctor/schedule/', v.schedule, name='doctor-schedule'),
    path('doctor/schedule/<int:pk>/', v.schedule, name='doctor-schedule-edit'),
    path('doctor/schedule/<int:pk>/delete/', v.schedule_delete, name='doctor-schedule-delete'),
    path('doctor/leave/', v.leave, name='doctor-leave'),
    path('doctor/leave/<int:pk>/delete/', v.leave_delete, name='doctor-leave-delete'),
    path('doctor/services/', v.doctor_services, name='doctor-services'),
    path('doctor/services/<int:pk>/', v.doctor_services, name='doctor-service-edit'),
    path('doctor/profile/', v.profile, name='doctor-profile'),
    path('doctor/calendar/', v.calendar, name='doctor-calendar'),
    path('doctor/messages/', v.inbox, name='doctor-inbox'),
    path('admin/', admin.site.urls),
    path('health/', v.health, name='health'),
    path('robots.txt', v.robots),
    path('sitemap.xml', sitemap, {'sitemaps': {'public': PublicSitemap}}),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
handler403 = 'clinic.views.error403'
handler404 = 'clinic.views.error404'
handler500 = 'clinic.views.error500'
