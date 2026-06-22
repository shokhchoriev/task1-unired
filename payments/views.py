import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Payment
from .serializers import PaymentRequestSerializer, PaymentResponseSerializer
from .services import PaymentService

logger = logging.getLogger(__name__)


@api_view(["POST"])
def pay(request):
    """
    POST /pay/

    So'rov:
        {
            "card_number": "8600123456781234",
            "expire": "12/26",
            "amount": "50000.00",
            "currency": "UZS",
            "provider": "payme"   // yoki "stripe"
        }

    Javob (muvaffaqiyatli):
        HTTP 200
        { "id": 1, "status": "success", "provider_transaction_id": "...", ... }

    Javob (muvaffaqiyatsiz to'lov):
        HTTP 402
        { "id": 1, "status": "failed", "error_message": "...", ... }
    """
    serializer = PaymentRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    service = PaymentService()

    payment = service.pay(
        card_number=data["card_number"],
        expire=data["expire"],
        amount=data["amount"],
        currency=data["currency"],
        provider_name=data["provider"],
    )

    response_data = PaymentResponseSerializer(payment).data
    http_status = (
        status.HTTP_200_OK
        if payment.status == Payment.Status.SUCCESS
        else status.HTTP_402_PAYMENT_REQUIRED
    )
    return Response(response_data, status=http_status)
