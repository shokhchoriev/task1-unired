from django.http import JsonResponse
from .models import Payment
import logging


request_logger = logging.getLogger("task2.request")
error_logger = logging.getLogger("task2.error")
def payment_status(request):
    ext_id = request.GET.get("ext_id")

    if not ext_id:
        return JsonResponse({"status": "error", "message": "ext_id is required"}, status=400)

    try:
        payment = Payment.objects.get(ext_id=ext_id)

        request_logger.info(f"Payment status checked successfully for ext_id: {ext_id}")

        return JsonResponse({
            'id': str(payment.id),
            'ext_id': payment.ext_id,
            "amount": str(payment.amount),
            'status': payment.status
        })
    except Payment.DoesNotExist:

        error_logger.error(f"Payment status check failed: Payment with ext_id '{ext_id}' not found")
        return JsonResponse({'error': 'Payment topilmadi '}, status=404)