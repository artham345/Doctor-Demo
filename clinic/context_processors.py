from django.conf import settings
from .models import Doctor

def clinic(request):
    doctor = getattr(request, 'doctor', None) or Doctor.objects.filter(is_public=True).first()
    return {'clinic': doctor, 'site_url': settings.SITE_URL, 'clinic_timezone': settings.TIME_ZONE}
