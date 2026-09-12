import secrets
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .services import deliver_pending


@csrf_exempt
@require_POST
def retry_emails(request):
    # Machine-only endpoint: no session auth, header credentials, fixed batch.
    token = settings.EMAIL_RETRY_TOKEN
    supplied = request.headers.get('Authorization', '')
    if len(token) < 32 or not secrets.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
        response = JsonResponse({'error': 'Forbidden'}, status=403)
    else:
        try:
            sent, failed = deliver_pending(limit=2)
            response = JsonResponse({'delivered': sent, 'deferred': failed}, status=503 if failed else 200)
        except Exception:
            response = JsonResponse({'error': 'Retry temporarily unavailable'}, status=503)
    response['Cache-Control'] = 'no-store, private'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response
