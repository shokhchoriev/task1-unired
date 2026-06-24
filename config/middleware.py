import hmac
import os

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from config.security import generate_hash


class RequestSignatureMiddleware:
    """Verify HMAC-SHA256 request-sign header on every mutating request.

    Secret resolution order:
      1. request.user.userprofile.secret  (authenticated users)
      2. SIGNATURE_SECRET env var         (anonymous / service clients)
      3. Neither present → 403

    Paths in SIGNATURE_EXEMPT_PATHS (settings) are skipped entirely.
    """

    MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.MUTATING_METHODS:
            exempt = getattr(settings, "SIGNATURE_EXEMPT_PATHS", [])
            if not any(request.path.startswith(p) for p in exempt):
                error_response = self._check_signature(request)
                if error_response is not None:
                    return error_response
        return self.get_response(request)

    def _check_signature(self, request):
        sign = request.META.get("HTTP_REQUEST_SIGN")
        if not sign:
            return JsonResponse({"error": "Missing signature"}, status=403)

        secret = self._resolve_secret(request)
        if not secret:
            return JsonResponse({"error": "Signature secret not configured"}, status=403)

        body = request.body.decode("utf-8", errors="replace")
        expected = generate_hash(body, secret)
        print(f"[DEBUG signature] secret[:6]={secret[:6]!r} | body_len={len(body)} | expected={expected} | received={sign}")
        if not hmac.compare_digest(expected, sign):
            return JsonResponse({"error": "Invalid signature"}, status=403)

        return None

    @staticmethod
    def _resolve_secret(request):
        if request.user.is_authenticated:
            try:
                return request.user.userprofile.secret
            except Exception:
                pass
        return os.getenv("SIGNATURE_SECRET") or ""


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
