import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Payment
from .serializers import PaymentRequestSerializer, PaymentResponseSerializer, RefundRequestSerializer
from .services import PaymentService

logger = logging.getLogger(__name__)


@api_view(["POST"])
def pay(request):
    """
    POST /pay/

    Accepts a payment request, creates a Payment record, and charges via the
    chosen provider. ext_id is optional — a UUID is auto-generated if omitted.

    Request:
        {
            "ext_id": "550e8400-e29b-41d4-a716-446655440000",  // optional
            "card_number": "4242424242424242",
            "expire": "12/26",
            "amount": "50.00",
            "currency": "USD",
            "provider": "stripe"
        }

    Response 200: payment succeeded
    Response 402: payment failed
    Response 400: validation error
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
        ext_id=data.get("ext_id"),
    )

    response_data = PaymentResponseSerializer(payment).data
    http_status = (
        status.HTTP_200_OK
        if payment.status == Payment.Status.SUCCESS
        else status.HTTP_402_PAYMENT_REQUIRED
    )
    return Response(response_data, status=http_status)


# ─── Stripe webhook ───────────────────────────────────────────────────────────

@csrf_exempt
def stripe_webhook(request):
    """
    POST /stripe/webhook/

    Stripe calls this endpoint to notify us of asynchronous payment events.
    Every request is verified with HMAC using STRIPE_WEBHOOK_SECRET before
    any database work happens.

    Handled events:
      - payment_intent.succeeded       → Payment.status = SUCCESS
      - payment_intent.payment_failed  → Payment.status = FAILED

    All other event types return 200 immediately (ignored, not an error).
    Stripe will retry on any non-2xx response, so we always return 200 once
    the signature is verified, even for unknown events.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured — rejecting webhook")
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        logger.warning("Stripe webhook: malformed payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook: invalid signature")
        return HttpResponse(status=400)

    intent = event["data"]["object"]
    intent_id = intent["id"]
    event_type = event["type"]

    if event_type == "payment_intent.succeeded":
        _apply_webhook_status(intent_id, Payment.Status.SUCCESS, None, intent)
    elif event_type == "payment_intent.payment_failed":
        last_error = intent.get("last_payment_error") or {}
        _apply_webhook_status(
            intent_id,
            Payment.Status.FAILED,
            last_error.get("message", "Payment failed"),
            intent,
        )
    else:
        logger.debug("Stripe webhook: unhandled event type '%s'", event_type)

    return HttpResponse(status=200)


def _apply_webhook_status(intent_id: str, new_status: str, error_msg, raw) -> None:
    """Update a Payment by provider_transaction_id inside a serialisable transaction.

    select_for_update() prevents a race condition when two webhook deliveries
    for the same event arrive simultaneously.
    """
    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(
                provider_transaction_id=intent_id
            )
        except Payment.DoesNotExist:
            logger.warning(
                "Stripe webhook: no Payment found for intent_id=%s (event may arrive "
                "before the synchronous charge response is saved — Stripe will retry)",
                intent_id,
            )
            return

        if payment.status == new_status:
            return  # idempotent — already in the target state

        update_fields = ["status", "provider_response", "updated_at"]
        payment.status = new_status
        try:
            import json
            payment.provider_response = json.loads(str(raw))
        except Exception:
            pass

        if error_msg is not None:
            payment.error_message = error_msg
            update_fields.append("error_message")

        payment.save(update_fields=update_fields)
        logger.info(
            "Stripe webhook: Payment pk=%s (intent=%s) → %s",
            payment.pk, intent_id, new_status,
        )


# ─── Stripe refund ────────────────────────────────────────────────────────────

@api_view(["POST"])
def stripe_refund(request):
    """
    POST /stripe/refund/

    Issue a full refund for a successful Stripe payment identified by ext_id.

    Request:  { "ext_id": "<uuid>" }
    Response 200: { "refund_id": "re_...", "ext_id": "...", "status": "refunded" }
    Response 400: validation error or payment not in refundable state
    Response 404: payment not found
    Response 409: already refunded
    Response 502: Stripe API error
    """
    serializer = RefundRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ext_id = serializer.validated_data["ext_id"]

    try:
        payment = Payment.objects.get(ext_id=ext_id, provider=Payment.Provider.STRIPE)
    except Payment.DoesNotExist:
        return Response(
            {"error": "Stripe payment not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if payment.status == Payment.Status.REFUNDED:
        return Response(
            {"error": "Payment already refunded", "refund_id": payment.refund_id},
            status=status.HTTP_409_CONFLICT,
        )

    if payment.status != Payment.Status.SUCCESS:
        return Response(
            {"error": f"Cannot refund a payment with status '{payment.status}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not payment.provider_transaction_id:
        return Response(
            {"error": "Payment has no Stripe transaction ID"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    service = PaymentService()
    try:
        result = service.refund(payment)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not result.success:
        logger.error("Refund failed for payment %s: %s", payment.pk, result.error)
        return Response({"error": result.error}, status=status.HTTP_502_BAD_GATEWAY)

    payment.refresh_from_db(fields=["refund_id", "status"])
    return Response(
        {
            "refund_id": payment.refund_id,
            "ext_id": str(payment.ext_id),
            "status": payment.status,
        },
        status=status.HTTP_200_OK,
    )
