from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    """Public process liveness check; no database access or infrastructure details."""
    return JsonResponse({"status": "ok"})
