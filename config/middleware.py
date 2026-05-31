from django.conf import settings
from django.core.exceptions import PermissionDenied


class AdminIPRestrictionMiddleware:
    """Allow Django Admin access only from configured trusted IP addresses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            allowed_ips = set(getattr(settings, "ADMIN_ALLOWED_IPS", []))
            client_ip = self._get_client_ip(request)

            if allowed_ips and client_ip not in allowed_ips:
                raise PermissionDenied("Django Admin access is restricted.")

        return self.get_response(request)

    @staticmethod
    def _get_client_ip(request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for and getattr(settings, "TRUST_X_FORWARDED_FOR", False):
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
