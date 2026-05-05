import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from jsonrpcserver import Error as RPCError
from jsonrpcserver import Result, Success, dispatch_to_serializable, method

from cards.models import Card
from cards.utils import format_expire

from .models import Error, Transfer
from .utils import (
    FakeNotificationService,
    calculate_exchange,
    generate_otp,
    get_transfer_by_ext_id,
)
# utils.py dan dekoratorni import qilish qismini qo'shdik
from .utils import FakeNotificationService, calculate_exchange, generate_otp, log_transfer_method


logger = logging.getLogger(__name__)
request_logger = logging.getLogger("task2.request")
error_logger = logging.getLogger("task2.error")

# Error codes matching task spec (32700–32714)
ERR_EXT_ID_UNIQUE = 32700
ERR_EXT_ID_EXISTS = 32701
ERR_BALANCE_NOT_ENOUGH = 32702
ERR_SMS_NOT_BIND = 32703
ERR_CARD_EXPIRY_INVALID = 32704
ERR_CARD_NOT_ACTIVE = 32705
ERR_UNKNOWN = 32706
ERR_CURRENCY_NOT_ALLOWED = 32707
ERR_AMOUNT_TOO_LARGE = 32708
ERR_AMOUNT_TOO_SMALL = 32709
ERR_OTP_EXPIRED = 32710
ERR_TRY_COUNT_REACHED = 32711
ERR_OTP_WRONG = 32712


def get_error(code, override_message=None):
    try:
        err_obj = Error.objects.get(code=code)
        message = override_message if override_message is not None else err_obj.en
        return RPCError(code=err_obj.code, message=message)
    except Error.DoesNotExist:
        return RPCError(code=code, message=override_message or "Unknown error")


def _parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _normalize_expiry(expiry_str):
    """Accept MM/YY or YYYY-MM and return YYYY-MM for DB lookup."""
    try:
        return format_expire(expiry_str)
    except Exception:
        return None


@method(name="transfer.create")
@method
@log_transfer_method  # LOGGING CREATE
def transfer_create(
    ext_id,
    sender_card_number,
    sender_card_expiry,
    receiver_card_number,
    sending_amount,
    currency,
) -> Result:
    try:
        request_logger.info(
            "transfer.create: ext_id=%s sender=%s receiver=%s amount=%s currency=%s",
            ext_id,
            sender_card_number,
            receiver_card_number,
            sending_amount,
            currency,
        )

        if Transfer.objects.filter(ext_id=ext_id).exists():
            return get_error(ERR_EXT_ID_EXISTS)

        if currency not in {643, 840}:
            return get_error(ERR_CURRENCY_NOT_ALLOWED)

        amount = _parse_amount(sending_amount)
        if amount is None:
            return get_error(ERR_AMOUNT_TOO_SMALL)

        normalized_expiry = _normalize_expiry(sender_card_expiry)
        if normalized_expiry is None:
            return get_error(ERR_CARD_EXPIRY_INVALID)

        try:
            sender_card = Card.objects.get(
                card_number=sender_card_number,
                expire=normalized_expiry,
            )
        except Card.DoesNotExist:
            return get_error(ERR_CARD_EXPIRY_INVALID)

        if sender_card.status != "active":
            return get_error(ERR_CARD_NOT_ACTIVE)

        if not sender_card.phone:
            return get_error(ERR_SMS_NOT_BIND)

        try:
            receiver_card = Card.objects.get(card_number=receiver_card_number)
        except Card.DoesNotExist:
            return get_error(ERR_UNKNOWN)

        receiving_amount = calculate_exchange(amount=amount, currency=currency)

        if sender_card.balance < receiving_amount:
            return get_error(ERR_BALANCE_NOT_ENOUGH)
        otp = generate_otp()

        transfer = Transfer.objects.create(
            ext_id=ext_id,
            sender_card_number=sender_card_number,
            receiver_card_number=receiver_card_number,
            sender_card_expiry=normalized_expiry,
            sender_phone=sender_card.phone,
            receiver_phone=receiver_card.phone,
            sending_amount=amount,
            receiving_amount=receiving_amount,
            currency=currency,
            state=Transfer.State.CREATED,
            otp=otp,
        )

        FakeNotificationService().send_otp(
            phone=sender_card.phone,
            tg_id=getattr(sender_card, "tg_id", "unknown"),
            otp=otp,
        )

        request_logger.info(
            "transfer.create success: ext_id=%s state=%s", ext_id, transfer.state
        )
        return Success({"ext_id": ext_id, "state": transfer.state, "otp_sent": True})

    except Exception:
        error_logger.exception("transfer.create failed: ext_id=%s", ext_id)
        return get_error(ERR_UNKNOWN)


@method(name="transfer.confirm")
@method
@log_transfer_method  # LOGGING CONFIRM
def transfer_confirm(ext_id, otp) -> Result:
    try:
        request_logger.info("transfer.confirm: ext_id=%s", ext_id)

        transfer = get_transfer_by_ext_id(ext_id)
        if transfer is None:
            return get_error(ERR_UNKNOWN)

        if transfer.state != Transfer.State.CREATED:
            return get_error(ERR_OTP_EXPIRED)

        if transfer.try_count >= 3:
            transfer.state = Transfer.State.CANCELLED
            transfer.cancelled_at = timezone.now()
            transfer.save(update_fields=["state", "cancelled_at", "updated_at"])
            return get_error(ERR_TRY_COUNT_REACHED)

        if transfer.otp != str(otp):
            transfer.try_count += 1
            update_fields = ["try_count", "updated_at"]

            if transfer.try_count >= 3:
                transfer.state = Transfer.State.CANCELLED
                transfer.cancelled_at = timezone.now()
                update_fields.extend(["state", "cancelled_at"])
                transfer.save(update_fields=update_fields)
                return get_error(ERR_TRY_COUNT_REACHED)

            transfer.save(update_fields=update_fields)
            left = 3 - transfer.try_count
            return get_error(
                ERR_OTP_WRONG,
                override_message=f"OTP is wrong, left try count is {left}",
            )

        try:
            with transaction.atomic():
                sender_card = Card.objects.select_for_update().get(
                    card_number=transfer.sender_card_number
                )
                receiver_card = Card.objects.select_for_update().get(
                    card_number=transfer.receiver_card_number
                )

                if sender_card.balance < transfer.receiving_amount:
                    return get_error(ERR_BALANCE_NOT_ENOUGH)

                sender_card.balance -= transfer.receiving_amount
                receiver_card.balance += transfer.receiving_amount
                sender_card.save(update_fields=["balance"])
                receiver_card.save(update_fields=["balance"])

                transfer.state = Transfer.State.CONFIRMED
                transfer.confirmed_at = timezone.now()
                transfer.save(update_fields=["state", "confirmed_at", "updated_at"])

        except Card.DoesNotExist:
            return get_error(ERR_UNKNOWN)
        except Exception:
            error_logger.exception(
                "transfer.confirm atomic failed: ext_id=%s", ext_id
            )
            return get_error(ERR_UNKNOWN)

        request_logger.info("transfer.confirm success: ext_id=%s", ext_id)
        return Success({"ext_id": ext_id, "state": transfer.state})

    except Exception:
        error_logger.exception("transfer.confirm failed: ext_id=%s", ext_id)
        return get_error(ERR_UNKNOWN)


@method(name="transfer.cancel")
@method
@log_transfer_method  # LOGGING CANCEL
def transfer_cancel(ext_id) -> Result:
    try:
        request_logger.info("transfer.cancel: ext_id=%s", ext_id)

        transfer = get_transfer_by_ext_id(ext_id)
        if transfer is None:
            return get_error(ERR_UNKNOWN)

        if transfer.state != Transfer.State.CREATED:
            return get_error(
                ERR_UNKNOWN,
                override_message="Transfer cannot be cancelled in current state",
            )

        transfer.state = Transfer.State.CANCELLED
        transfer.cancelled_at = timezone.now()
        transfer.save(update_fields=["state", "cancelled_at", "updated_at"])

        request_logger.info("transfer.cancel success: ext_id=%s", ext_id)
        return Success({"state": transfer.state})

    except Exception:
        error_logger.exception("transfer.cancel failed: ext_id=%s", ext_id)
        return get_error(ERR_UNKNOWN)
    if card_number:
        queryset = queryset.filter(sender_card_number=card_number)
    if status:
        queryset = queryset.filter(state=status)
    if date_from:
        queryset = queryset.filter(created_at__gte=datetime.fromisoformat(date_from))
    if date_to:
        queryset = queryset.filter(created_at__lte=datetime.fromisoformat(date_to))

    data = [{"ext_id": t.ext_id, "amount": str(t.sending_amount), "state": t.state, "date": t.created_at.isoformat()} for t in queryset]
    return Success(data)

@method(name="transfer.state")
def transfer_state(ext_id) -> Result:
    try:
        transfer = get_transfer_by_ext_id(ext_id)
        if transfer is None:
            return get_error(ERR_UNKNOWN)
        return Success({"ext_id": ext_id, "state": transfer.state})
    except Exception:
        error_logger.exception("transfer.state failed: ext_id=%s", ext_id)
        return get_error(ERR_UNKNOWN)


@method(name="transfer.history")
def transfer_history(
    card_number=None,
    start_date=None,
    end_date=None,
    status=None,
) -> Result:
    try:
        queryset = Transfer.objects.all()

        if card_number:
            queryset = queryset.filter(
                Q(sender_card_number=card_number) | Q(receiver_card_number=card_number)
            )
        if status:
            queryset = queryset.filter(state=status)
        if start_date:
            queryset = queryset.filter(
                created_at__date__gte=datetime.strptime(start_date, "%Y-%m-%d").date()
            )
        if end_date:
            queryset = queryset.filter(
                created_at__date__lte=datetime.strptime(end_date, "%Y-%m-%d").date()
            )

        data = [
            {
                "ext_id": t.ext_id,
                "sending_amount": str(t.sending_amount),
                "state": t.state,
                "created_at": t.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            for t in queryset.order_by("-created_at")
        ]
        return Success(data)

    except Exception:
        error_logger.exception("transfer.history failed")
        return get_error(ERR_UNKNOWN)


@csrf_exempt
def json_rpc_view(request):
    if request.method != "POST":
        return JsonResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": 32713, "message": "Method is not allowed"},
            },
            status=405,
        )

    request_data = request.body.decode("utf-8")
    request_logger.info("RPC Request: %s", request_data)

    response = dispatch_to_serializable(request_data)

    request_logger.info("RPC Response: %s", response)

    if response is None:
        return HttpResponse(status=204)

    return JsonResponse(response, safe=False)
@csrf_exempt
def json_rpc_view(request):
    # REQUEST IP MANZILNI ANIQLASH QISMI
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    request_data = request.body.decode("utf-8")
    
    # IP log
    logger.info(f"IP: {ip} | Request: {request_data}")
    
    response = dispatch(request_data)
    
    logger.info(f"Response: {response}")
    return JsonResponse(response, safe=False)
