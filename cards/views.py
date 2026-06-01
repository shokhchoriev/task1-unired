from django.http import JsonResponse

def ratelimit_error(request, exception):
    return JsonResponse(
        {
            "error": "Too many requests"
        },
        status=429,
    )