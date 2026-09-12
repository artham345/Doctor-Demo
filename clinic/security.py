import hashlib
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import RateLimit

def doctor_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not hasattr(request.user, 'doctor') or not request.user.is_active:
            raise PermissionDenied
        request.doctor = request.user.doctor
        return view(request, *args, **kwargs)
    return wrapped

def allowed_request(request, scope, limit, seconds=600):
    # Never trust a caller-supplied X-Forwarded-For; fail conservatively behind proxies.
    identity = request.META.get('REMOTE_ADDR', 'unknown')
    key = hashlib.sha256(f'{settings.SECRET_KEY}:{scope}:{identity}'.encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        row, _ = RateLimit.objects.get_or_create(key=key, defaults={'expires_at': now + timedelta(seconds=seconds)})
        row = RateLimit.objects.select_for_update().get(pk=row.pk)
        if row.expires_at <= now:
            row.count = 0
            row.expires_at = now + timedelta(seconds=seconds)
        row.count += 1
        row.save()
        return row.count <= limit
